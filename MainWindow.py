import sys
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtCore import QThread, Signal, QTimer, QObject,Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,QGridLayout,QTabWidget, QWidget, QLabel,QPushButton,QSlider,QComboBox
from PySide6.QtCharts import QPolarChart, QValueAxis, QChartView, QScatterSeries
from telescope_control import Telescope
import threading
from can.interface import Bus
from can_bus_manager import CANBusManager
import time
import pyqtgraph as pg
import astropy
import datetime
from astropy.time import Time
import astropy.units as u
import numpy as np
from functions import *


lock = threading.Lock()

telescope_type = "virtual" # real or virtual
sdr_type = "virtual"  # pluto or virtual

class MainWindow(QMainWindow):
    end_of_run = Signal()
    update_data = Signal(float,float,float)
    def __init__(self):
        super().__init__()
        self.setWindowTitle('RIF CONTROL :)')
        self.setGeometry(100, 100, 700, 400)

        self.tempL_buffer = []
        self.tempH_buffer = []
        self.output_buffer = []
        self.time_buffer = []

        self.worker = Worker()
        #load file
        styleFile = QtCore.QFile('style.css')
        #set file mode 
        styleFile.open(QtCore.QFile.OpenModeFlag.ReadOnly)
        #convert QbyteArray to String
        convert = styleFile.readAll().toStdString()
        #set stylesheet
        self.setStyleSheet(convert)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.page_layout = QHBoxLayout(self.central_widget)
        self.main_layout = QVBoxLayout()
        self.page_layout.addLayout(self.main_layout)

        self.tab_widget = QTabWidget()
        self.position_gui = positionGUI()
        self.temp_gui = tempGUI()
        self.signal_gui = signalGUI()


        self.tab_widget.addTab(self.position_gui, "Position")
        self.tab_widget.addTab(self.signal_gui, "Signal")
        self.tab_widget.addTab(self.temp_gui, "Temperature")
        # self.tab_widget.addTab(self.signalpos_gui, "HeatMap")
        self.main_layout.addWidget(self.tab_widget)

        # self.widget = QtWidgets.QWidget()
        # self.widget.setLayout(self.main_layout)
        # self.setCentralWidget(self.widget)
        self.right_layout = QVBoxLayout()
        self.page_layout.addLayout(self.right_layout)

        self.freq = 1420e6
        self.label_HA = QLabel(text="---")
        self.label_DEC = QLabel(text="---")
        self.label_freq = QLabel(text=f"FREQ: {round(self.freq/1e6)} MHz")
        self.label_temp = QLabel(text=f"TEMP: --- °C")

        self.right_layout.addWidget(self.label_freq)
        self.right_layout.addWidget(self.label_temp)
        self.right_layout.addWidget(self.label_HA)
        self.right_layout.addWidget(self.label_DEC)

        def data_callback(ha, dec, temp):
            self.label_HA.setText(f"HA: {round(ha, 1)}")
            self.label_DEC.setText(f"DEC: {round(dec, 1)}")
            self.label_temp.setText(f"TEMP: {temp} °C")

        def end_of_run_callback():
            QTimer.singleShot(0, self.run) # Run worker again immediately
            
        self.end_of_run.connect(end_of_run_callback)
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        self.update_data.connect(data_callback)
        self.temp_gui.update_temp.connect(self.temp_gui.temp_plot)


        def start_button_callback():
            self.worker.measure = not self.worker.measure
            self.signal_gui.start_button_callback(self.worker.measure)
            self.worker.end_of_measure_run.emit()

        self.signal_gui.start_button.clicked.connect(start_button_callback)
        # self.signal_gui.start_button.clicked.connect(self.worker.start_measure)
        self.worker.telescope.receiver.sample_completed.connect(self.signal_gui.freq_plot_callback)
        self.worker.telescope.receiver.sampling.connect(self.signal_gui.time_plot_callback)
        self.position_gui.plot_position.connect(self.position_gui.plot_position_callback)
        self.worker.end_of_measure_run.connect(self.worker.measure_callback)
        self.worker_thread.start()
        self.sdr = self.worker.telescope.receiver.sdr
        self.sdr.rx_lo = self.freq
        self.start_t = 0
        self.run()





    def run(self):
        # Main loop
        position_HA = self.worker.telescope.dish_west.drive_HA.position
        position_DEC = self.worker.telescope.dish_west.drive_DEC.position
        temp_H = self.worker.telescope.dish_west.temp_device.temp_H
        temp_L = self.worker.telescope.dish_west.temp_device.temp_L
        output = self.worker.telescope.dish_west.temp_device.output
        times = time.time()
        self.tempH_buffer.append(temp_H)
        self.tempL_buffer.append(temp_L)
        self.output_buffer.append(output)
        self.time_buffer.append(times)
        self.temp_gui.update_temp.emit(self.time_buffer, self.tempH_buffer, self.tempL_buffer, self.output_buffer)
        # self.position_gui.plot_position.emit(position_HA, position_DEC)
        coord = self.worker.telescope.dish_west.pos_to_coord(position_DEC, position_HA)
        self.update_data.emit(coord.ha.to(u.hourangle).value, coord.dec.to(u.degree).value, temp_H)
        self.end_of_run.emit()


class positionGUI(QWidget):

    end_of_run = Signal()
    plot_position = Signal(float, float)

    def __init__(self):
        super().__init__()

        self.id = round(time.time())

        self.worker = Worker()

        self.max_ha =  self.worker.telescope.dish_west.max_ha
        self.max_dec = self.worker.telescope.dish_west.max_dec
        self.min_dec = self.worker.telescope.dish_west.min_dec
        self.min_ha = self.worker.telescope.dish_west.min_ha

        self.polar_plot = pg.PlotWidget()   
        self.polar_scatter = pg.ScatterPlotItem()
        self.polar_plot.addItem(self.polar_scatter)

        for ring, color in zip([22.5,45,67.5,90,90-self.min_dec], ["#ffffff","#ffffff","#fffb00","#ffffff","#ff4500"]): 
            p_ellipse = QtWidgets.QGraphicsEllipseItem(-(ring), -(ring), ring*2, ring*2)  # x, y, width, height
            p_ellipse.setPen(pg.mkPen(color=color))
            label = QtWidgets.QGraphicsTextItem(str(90-ring))
            label.setPos(ring*np.cos(-self.max_ha*(2*np.pi/24)+(np.pi/2)),ring*np.sin(-self.max_ha*(2*np.pi/24)+(np.pi/2)))
            label.setDefaultTextColor(color)
            font = QtGui.QFont("Helvetica", 5)
            label.setFont(font)
            label.setTransform(QtGui.QTransform.fromScale(1, -1))
            self.polar_plot.addItem(p_ellipse)
            self.polar_plot.addItem(label)
        
        for angle, color in zip([self.min_ha, self.max_ha],["#ff4500","#ff4500"]):
            line1 = QtWidgets.QGraphicsLineItem(0,0,(90-self.min_dec)*np.cos(-angle*(2*np.pi/24)+(np.pi/2)),(90-self.min_dec)*np.sin(-angle*(2*np.pi/24)+(np.pi/2)))
            line1.setPen(pg.mkPen(color=color))
            self.polar_plot.addItem(line1)

        def end_of_run_callback():
            QTimer.singleShot(0, self.run) # Run worker again immediately

        self.main_layout = QHBoxLayout(self)
        self.left_layout = QVBoxLayout()
        self.main_layout.addLayout(self.left_layout)
        self.left_layout.addWidget(self.polar_plot)
        self.end_of_run.connect(end_of_run_callback)
        self.plot_position.connect(self.plot_position_callback)
        self.run()

    def plot_position_callback(self,ha, dec):
        self.polar_scatter.setData([(90-dec)*np.cos(-ha*(2*np.pi/24)+(np.pi/2))], [(90-dec)*np.sin(-ha*(2*np.pi/24)+(np.pi/2))])

    def run(self):
        # Main loop
        position_HA = self.worker.telescope.dish_west.drive_HA.position
        position_DEC = self.worker.telescope.dish_west.drive_DEC.position
        temp = self.worker.telescope.dish_west.temp_device.temp_H
        coord = self.worker.telescope.dish_west.pos_to_coord(position_DEC, position_HA)
        self.plot_position.emit(coord.ha.to(u.hourangle).value, coord.dec.to(u.degree).value)
        self.end_of_run.emit()

class signalGUI(QMainWindow,):
    def __init__(self):
        super().__init__()
        self.fft_size = 4096
        center_freq = 1420e6
        time_plot = pg.PlotWidget(labels={'left': 'Amplitude', 'bottom': 'Time [microseconds]'})
        time_plot.setMouseEnabled(x=False, y=True)
        time_plot.setYRange(-1.1, 1.1)
        self.time_plot_curve_i = time_plot.plot([])
        self.time_plot_curve_q = time_plot.plot([])

        self.main_layout = QGridLayout()
        self.widget = QtWidgets.QWidget()
        self.widget.setLayout(self.main_layout)
        self.setCentralWidget(self.widget) 
        self.main_layout.addWidget(time_plot, 1, 0)

        # Time plot auto range buttons
        time_plot_auto_range_layout = QVBoxLayout()
        self.main_layout.addLayout(time_plot_auto_range_layout, 1, 1)
        auto_range_button = QPushButton('Auto Range')
        auto_range_button.clicked.connect(lambda : time_plot.autoRange()) # lambda just means its an unnamed function
        time_plot_auto_range_layout.addWidget(auto_range_button)
        auto_range_button2 = QPushButton('-1 to +1\n(ADC limits)')
        auto_range_button2.clicked.connect(lambda : time_plot.setYRange(-1.1, 1.1))
        time_plot_auto_range_layout.addWidget(auto_range_button2)

        # Freq plot
        freq_plot = pg.PlotWidget(labels={'left': 'PSD', 'bottom': 'Frequency [MHz]'})
        freq_plot.setMouseEnabled(x=False, y=True)
        self.freq_plot_curve = freq_plot.plot([])
        freq_plot.setXRange(1420 - 2, 1420 + 2)
        freq_plot.setYRange(-30, 20)
        self.main_layout.addWidget(freq_plot, 2, 0)

        # Freq auto range button
        freq_layout = QVBoxLayout()
        self.main_layout.addLayout(freq_layout, 2, 1)
        auto_range_button = QPushButton('Auto Range')
        auto_range_button.clicked.connect(lambda : freq_plot.autoRange()) # lambda just means its an unnamed function
        freq_layout.addWidget(auto_range_button)
        self.start_button = QPushButton('START')
        freq_layout.addWidget(self.start_button)

        # Layout container for waterfall related stuff
        waterfall_layout = QHBoxLayout()
        self.main_layout.addLayout(waterfall_layout, 3, 0)

        # Waterfall plot
        
        waterfall = pg.PlotWidget(labels={'left': 'Signal', 'bottom': 'Time [seconds]'})
        waterfall.setMouseEnabled(x=False, y=True)
        # time_plot.setYRange(-1.1, 1.1)
        self.waterfall_curve = waterfall.plot([])
        waterfall.setXRange(0, 3600)
        waterfall.setYRange(0, 100000)
        waterfall_layout.addWidget(waterfall)

        # Freq slider with label, all units in kHz
        freq_slider = QSlider(Qt.Orientation.Horizontal)
        freq_slider.setRange(0, int(6e6))
        freq_slider.setValue(int(center_freq/1e3))
        freq_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        freq_slider.setTickInterval(int(1e6))
        # freq_slider.sliderMoved.connect(self.worker.update_freq) # there's also a valueChanged option
        freq_label = QLabel()
        def update_freq_label(val):
            freq_label.setText("Frequency [MHz]: " + str(val/1e3))
            freq_plot.autoRange()
        freq_slider.sliderMoved.connect(update_freq_label)
        update_freq_label(freq_slider.value()) # initialize the label
        self.main_layout.addWidget(freq_slider, 4, 0)
        self.main_layout.addWidget(freq_label, 4, 1)

        # Gain slider with label
        gain_slider = QSlider(Qt.Orientation.Horizontal)
        gain_slider.setRange(0, 73)
        gain_slider.setValue(50)
        gain_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        gain_slider.setTickInterval(2)
        # gain_slider.sliderMoved.connect(self.worker.update_gain)
        gain_label = QLabel()
        def update_gain_label(val):
            gain_label.setText("Gain: " + str(val))
        gain_slider.sliderMoved.connect(update_gain_label)
        update_gain_label(gain_slider.value()) # initialize the label
        self.main_layout.addWidget(gain_slider, 5, 0)
        self.main_layout.addWidget(gain_label, 5, 1)


        def save_data(PSD_avg):
            with open('signal_data.csv', 'a') as f:
                # data_index = np.argwhere(np.logical_and(self.worker.freq_range >= 1e6, self.worker.freq_range <= 2e6)).flatten()
                data = PSD_avg.reshape(1, len(PSD_avg))
                np.savetxt(f, data, fmt='%s', delimiter=',')
        def save_data2(PSD_total):
            with open('power_data.csv', 'a') as f:
                # data_index = np.argwhere(np.logical_and(self.worker.freq_range >= 1e6, self.worker.freq_range <= 2e6)).flatten()
                np.savetxt(f, [len(PSD_total), PSD_total[-1]], fmt='%s', delimiter=',')

        def end_of_run_callback():
            QTimer.singleShot(0, self.worker.run) # Run worker again immediately
    
    def start_button_callback(self, measure):
        if measure:
            self.start_button.setText("START")
        else: 
            self.start_button.setText("STOP")



    
    # Signals and slots stuff
    def time_plot_callback(self, samples):
        self.time_plot_curve_i.setData(samples.real)
        self.time_plot_curve_q.setData(samples.imag)

    def freq_plot_callback(self,start_t,sample_rate, freq, signal, PSD_avg):
        f = np.linspace(freq - sample_rate/2.0, freq + sample_rate/2.0, self.fft_size) / 1e6
        self.freq_plot_curve.setData(f, PSD_avg)

    def waterfall_plot_callback(self, PSD_total):
        data = PSD_total
        self.waterfall_curve.setData(data)

        # self.fig.setXRange(xdata[max(0, len(xdata)-600)], max(10, xdata[-1]))


class tempGUI(QWidget):
    update_temp = Signal(list,list,list, list)

    def __init__(self):
        super().__init__()

        self.fig = pg.PlotWidget()
        self.fig.setBackground("w")

        # self.output_plot = pg.PlotWidget()
        # self.output_plot.setBackground("w")

        pen_r = pg.mkPen(color=(255, 0, 0))
        pen_g = pg.mkPen(color=(0, 255, 0))
        pen_b = pg.mkPen(color=(0, 0, 255))
        self.line1 = self.fig.plot([], [],  pen=pen_b)
        self.line2 = self.fig.plot([], [], pen=pen_r)
        # self.line3 = self.output_plot.plot([], [], pen=pen_g)
        # self.fig.setYRange(1701, 2869)
        self.fig.setXRange(0, 1000)
        # self.output_plot.setXRange(0, 1000)

        self.main_frame = QtWidgets.QHBoxLayout(self)
        self.left_frame = QtWidgets.QVBoxLayout()
        self.right_frame = QtWidgets.QVBoxLayout()
        self.right_up = QtWidgets.QVBoxLayout()
        self.right_down = QtWidgets.QGridLayout()

        self.main_frame.addLayout(self.left_frame)
        self.main_frame.addLayout(self.right_frame)
        self.right_frame.addLayout(self.right_up)
        self.right_frame.addLayout(self.right_down)
        self.left_frame.addWidget(self.fig)
        # self.left_frame.addWidget(self.output_plot)

        verticalSpacer = QtWidgets.QSpacerItem(20, 20, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.right_down.addItem(verticalSpacer)

        font_name = "Helvetica"
        size = 10
        self.templabelH = QtWidgets.QLabel(text="Temperature H: -- °C")
        self.right_up.addWidget(self.templabelH)
        # self.templabelH.setFont(QtGui.QFont(font_name, size))
        self.templabelL = QtWidgets.QLabel(text="Temperature L: -- °C")
        self.right_up.addWidget(self.templabelL)
        # self.templabelL.setFont(QtGui.QFont(font_name, size))
        self.boardtempLabel = QtWidgets.QLabel(text="Board Temp: -- °C")
        self.right_up.addWidget(self.boardtempLabel)
        # self.boardtempLabel.setFont(QtGui.QFont(font_name, size))
        self.outLabel = QtWidgets.QLabel( text="DACoutput: -- ")
        self.right_up.addWidget(self.outLabel)
        # self.outLabel.setFont(QtGui.QFont(font_name, size))
        self.outVLabel = QtWidgets.QLabel( text="Output: -- V")
        self.right_up.addWidget(self.outVLabel)
        # self.outVLabel.setFont(QtGui.QFont(font_name, size))

    def temp_plot(self,times, temp_H, temp_L, output):
        y1data = temp_L
        y2data = temp_H
        y3data = output
        
        xdata = np.array(times)
        xdata = xdata - xdata[0]
        self.line1.setData(xdata, y1data)
        self.line2.setData(xdata, y2data)
        self.fig.setXRange(xdata[max(0, len(xdata)-600)], max(10, xdata[-1]))
        # self.output_plot.setXRange(xdata[max(0, len(xdata)-600)], max(10, xdata[-1]))

        self.templabelL.setText(f"Temperature L: {y1data[-1]} °C")
        self.templabelH.setText(f"Temperature H: {y2data[-1]} °C")


        # self.line3.setData(xdata, y3data)
        self.outLabel.setText("DACoutput: " + f"{adc_conv(y3data[-1])}".upper())
        self.outVLabel.setText(f"Output: {round(y3data[-1], 3)} V")


class Worker(QObject):
    update_position = Signal(float, float)
    end_of_measure_run = Signal()
    def __init__(self):
        super().__init__()
        self.telescope = Telescope(telescope_type,bitrate=500000)
        self.telescope.start(skip_init=True)
        self.measure = False
        print("telescope started")

    def position_callback(self, ra, dec):
        ra_rad = ra* u.radian
        dec_rad = dec* u.radian
        coord = astropy.coordinates.HADec(ha=ra_rad, dec=dec_rad)
        print(f"change position: HA->{coord.ha} DEC->{coord.ha}")
        self.telescope.dish_west.move_to(coord, transform=False)
        self.telescope
        print("reached position")
        self.start_t = time.time()
        self.end_of_measure_run.emit()

    def start_measure(self):
        print("hey", self.measure)
        self.measure = not self.measure


    def measure_callback(self):
        if self.measure:
            self.telescope.receiver.sample()
            self.end_of_measure_run.emit()
    


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
    