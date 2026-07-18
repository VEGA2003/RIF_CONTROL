import sys
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtCore import QThread, Signal, QTimer, QObject
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,QTabWidget, QWidget, QLabel
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

# tempL_buffer = []
# tempH_buffer = []
# tempC_buffer = []
# time_buffer = []
# output_time_buffer = []
# output_buffer = []
# boardTemp_buffer = []
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

        # if telescope_type == "virtual":
        #     self.can_bus_manager = CANBusManager(channel="test", interface="virtual")
        # else:
        #     self.can_bus_manager = CANBusManager(bitrate = 500000, channel= "PCAN_USBBUS1")

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
        # self.signal_gui = signalGUI(self,sdr_type=sdr_type)


        self.tab_widget.addTab(self.position_gui, "Position")
        self.tab_widget.addTab(self.temp_gui, "Temperature")
        # self.tab_widget.addTab(self.signal_gui, "Signal")
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
        coord = self.worker.telescope.dish_west.pos_to_coord(position_DEC, position_HA)
        self.update_data.emit(coord.ha.to(u.hourangle).value, coord.dec.to(u.degree).value, temp_H)
        self.end_of_run.emit()


class positionGUI(QMainWindow):

    end_of_run = Signal()
    plot_position = Signal(float, float, float)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('RIF CONTROL :)')
        self.setGeometry(100, 100, 700, 400)
        self.id = round(time.time())

        self.worker = Worker()

        self.max_ha =  self.worker.telescope.dish_west.max_ha
        self.max_dec = self.worker.telescope.dish_west.max_dec
        self.min_dec = self.worker.telescope.dish_west.min_dec
        self.min_ha = self.worker.telescope.dish_west.min_ha


        self.fft_size = 4096
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



        self.freq = 1420e6
        self.power = 0
        self.PSD = np.zeros(self.fft_size)
        self.PSD_avg = np.zeros(self.fft_size)
        self.signal = []
        self.runs = 0

        self.main_layout = QHBoxLayout()
        self.left_layout = QVBoxLayout()
        self.widget = QtWidgets.QWidget()
        self.widget.setLayout(self.main_layout)
        self.setCentralWidget(self.widget)
        self.main_layout.addLayout(self.left_layout)
        self.left_layout.addWidget(self.polar_plot)
        


        def end_of_run_callback():
            QTimer.singleShot(0, self.run) # Run worker again immediately

            
        def end_of_measure_run_callback():
            QTimer.singleShot(0, self.measure) # Run worker again immediately


        def plot_position_callback(ha, dec, temp):
            self.polar_scatter.setData([(90-dec)*np.cos(-ha*(2*np.pi/24)+(np.pi/2))], [(90-dec)*np.sin(-ha*(2*np.pi/24)+(np.pi/2))])
    


        self.end_of_run.connect(end_of_run_callback)
        self.plot_position.connect(plot_position_callback)
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        self.worker.end_of_measure_run.connect(end_of_measure_run_callback)
        self.worker.update_position.connect(self.worker.position_callback)
        self.worker_thread.start()
        self.sdr = self.worker.telescope.receiver.sdr
        self.sdr.rx_lo = self.freq
        self.start_t = 0
        self.run()

    def run(self):
        # Main loop
        position_HA = self.worker.telescope.dish_west.drive_HA.position
        position_DEC = self.worker.telescope.dish_west.drive_DEC.position
        temp = self.worker.telescope.dish_west.temp_device.temp_H
        coord = self.worker.telescope.dish_west.pos_to_coord(position_DEC, position_HA)
        self.plot_position.emit(coord.ha.to(u.hourangle).value, coord.dec.to(u.degree).value, temp)
        self.end_of_run.emit()

class tempGUI(QWidget):
    update_temp = Signal(list,list,list, list)

    def __init__(self):
        super().__init__()

        self.fig = pg.PlotWidget()
        self.fig.setBackground("w")

        pen_r = pg.mkPen(color=(255, 0, 0))
        pen_g = pg.mkPen(color=(0, 255, 0))
        pen_b = pg.mkPen(color=(0, 0, 255))
        self.line1 = self.fig.plot([], [],  pen=pen_b)
        self.line2 = self.fig.plot([], [], pen=pen_r)
        self.line4 = self.fig.plot([], [], pen=pen_g)
        # self.fig.setYRange(1701, 2869)
        self.fig.setXRange(0, 1000)

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
        if len(y1data) > 0:
            xdata = xdata - xdata[0]
            self.line1.setData(xdata, y1data)
            self.line2.setData(xdata, y2data)
            self.fig.setXRange(xdata[max(0, len(xdata)-600)], max(10, xdata[-1]))

            self.templabelL.setText(f"Temperature L: {y1data[-1]} °C")
            self.templabelH.setText(f"Temperature H: {y2data[-1]} °C")
            
        if len(y3data) > 0:
            xdata = xdata - xdata[0]
            v = np.array(y3data) * -0.000149
            self.outLabel.setText("DACoutput: " + f"{int(y3data[-1] + 0x84E7):04x}".upper())
            self.outVLabel.setText(f"Output: {round(v[-1], 3)} V")


class Worker(QObject):
    update_position = Signal(float, float)
    end_of_measure_run = Signal()
    def __init__(self):
        super().__init__()
        self.telescope = Telescope(telescope_type,bitrate=500000)
        self.telescope.start(skip_init=True)

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






if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
    