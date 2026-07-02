import sys
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtCore import QThread, Signal, QTimer, QObject
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout,QHBoxLayout, QTabWidget, QWidget, QLabel
from PySide6.QtCharts import QPolarChart, QValueAxis, QChartView, QScatterSeries
from TempWindow import tempGUI
from SignalWindow import signalGUI
from PositionWindow import positionGUI
import threading
from can.interface import Bus
from can_bus_manager import CANBusManager
from telescope_control import Telescope
import pyqtgraph as pg
import time
import numpy as np
from calculate_sun_scan import pattern
import astropy
import datetime
from astropy.time import Time
import astropy.units as u
from functions import *

revolutions_to_increments = 65536
telescope_type = "real" # real or virtual
# sdr_type = "virtual"  # pluto or virtual
observing_time = Time(datetime.datetime.now(datetime.UTC))
# observing_time = Time(datetime.datetime(2026, 6, 16, 9, 0))
freqs =   np.arange(1408, 1442, step=2, dtype=int) * 1e6 # Hz
integration_time = 5
class MainWindow(QMainWindow):

    heatmap_update = Signal(float, int)
    end_of_run = Signal()
    plot_position = Signal(float, float, float)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('RIF CONTROL :)')
        self.setGeometry(100, 100, 700, 400)
        self.id = round(time.time())
        # if telescope_type == "virtual":
        #     self.can_bus_manager = CANBusManager(channel="test", interface="virtual")
        # else:
        #     self.can_bus_manager = CANBusManager(bitrate = 500000, channel= "PCAN_USBBUS1")

        #load file
        styleFile = QtCore.QFile('style.css')
        #set file mode 
        styleFile.open(QtCore.QFile.OpenModeFlag.ReadOnly)
        #convert QbyteArray to String
        convert = styleFile.readAll().toStdString()
        #set stylesheet
        self.setStyleSheet(convert)
        self.freq = int(freqs[0])
        print(f"type: {type(self.freq)}")
        self.heatmap = pg.PlotWidget(labels={'left': 'DEC', 'bottom': 'RA'})
        self.coords = sky_survey(3)
        self.heatmap.setXRange(np.min(self.coords[0]),np.max(self.coords[0]))
        self.heatmap.setYRange(np.min(self.coords[1]),np.max(self.coords[1]))
        self.index_i = 0
        self.index_k = 0
        self.scan = True
        self.imageitem = pg.ScatterPlotItem()
        self.heatmap.addItem(self.imageitem)

        self.fft_size = 4096
        self.polar_plot = pg.PlotWidget()   
        self.polar_scatter = pg.ScatterPlotItem()
        self.polar_plot.addItem(self.polar_scatter)

        for ring in [20,45]: 
            p_ellipse = QtWidgets.QGraphicsEllipseItem(-(ring), -(ring), ring*2, ring*2)  # x, y, width, height
            p_ellipse.setPen(pg.mkPen(color=(255, 255, 255)))
            self.polar_plot.addItem(p_ellipse)
        
        self.label_HA = QLabel(text="---")
        self.label_DEC = QLabel(text="---")
        self.label_freq = QLabel(text=f"FREQ: {round(self.freq/1e6)} MHz")
        self.label_temp = QLabel(text=f"TEMP: --- °C")
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
        self.left_layout.addWidget(self.heatmap)
        self.left_layout.addWidget(self.polar_plot)
        self.right_layout = QVBoxLayout()
        self.main_layout.addLayout(self.right_layout)
        self.right_layout.addWidget(self.label_freq)
        self.right_layout.addWidget(self.label_temp)
        self.right_layout.addWidget(self.label_HA)
        self.right_layout.addWidget(self.label_DEC)
        


        def end_of_run_callback():
            QTimer.singleShot(0, self.run) # Run worker again immediately

            
        def end_of_measure_run_callback():
            QTimer.singleShot(0, self.measure) # Run worker again immediately

        def heatmap_callback(signal, i):
            ra = self.coords[0][:i + 1,0] 
            dec = self.coords[1][:i + 1,0]
            print(ra, dec)
            self.imageitem.setData(ra, dec)
            colormap = pg.colormap.get("plasma")
            color = colormap.map(np.array(self.signal)*(1/20000))
            self.imageitem.setBrush(color)
            # self.image_array[i, j] = signal
            # self.imageitem.setImage(self.image_array, autoLevels=False)

        def plot_position_callback(ha, dec, temp):
            #  print(QThread.currentThread())
            #  data = np.random.randint(0,360, 2)
            # print((data/plotter.increments) % 1)
            #  self.polar_series.append(np.random.randint(0,360), 180)
            self.label_HA.setText(f"HA: {round(ha, 1)}")
            self.label_DEC.setText(f"DEC: {round(dec, 1)}")
            self.label_temp.setText(f"TEMP: {temp} °C")
            # self.polar_series.remove(0)
            # self.polar_series.append(data , 180)
            self.polar_scatter.setData([dec*np.cos(-ha*(2*np.pi/24)+(np.pi/2))], [dec*np.sin(-ha*(2*np.pi/24)+(np.pi/2))])
    


        self.heatmap_update.connect(heatmap_callback)
        self.end_of_run.connect(end_of_run_callback)
        self.plot_position.connect(plot_position_callback)
        self.worker_thread = QThread()
        self.worker = Worker()
        self.worker.moveToThread(self.worker_thread)
        self.worker.end_of_measure_run.connect(end_of_measure_run_callback)
        self.worker.update_position.connect(self.worker.position_callback)
        self.worker_thread.start()
        self.sdr = self.worker.telescope.receiver.sdr
        self.sdr.rx_lo = self.freq
        ra = self.coords[0][0,0] 
        dec = self.coords[1][0,0]
        self.worker.update_position.emit(ra,dec)
        self.start_t = 0
        self.run()



    def run(self):
        # Main loop
        position_HA = self.worker.telescope.dish_east.drive_HA.position
        position_DEC = self.worker.telescope.dish_east.drive_DEC.position
        temp = self.worker.telescope.dish_east.temp_device.temp_H
        coord = self.worker.telescope.dish_east.pos_to_coord(position_DEC, position_HA)
        self.plot_position.emit(coord.ha.to(u.hourangle).value, coord.dec.to(u.degree).value, temp)
        self.end_of_run.emit()

    def measure(self):
        now = time.time()
        sample = self.sdr.rx()
        self.power += np.sum(np.abs(np.array(sample)**2))
        self.runs += 1
        self.PSD += 10.0*np.log10(np.abs(np.fft.fftshift(np.fft.fft(sample)))**2/self.fft_size)
        if now > self.worker.start_t + integration_time:
            ra = self.coords[0][self.index_i,0] * u.radian
            dec = self.coords[1][self.index_i,0] * u.radian
            signal = self.power/self.runs
            self.PSD_avg = self.PSD/self.runs
            self.PSD = np.zeros(self.fft_size)
            with open(f'survey_data_{self.id}.csv', 'a') as f:
                np.savetxt(f, [[self.worker.start_t, ra.to(u.hourangle).value,dec.to(u.degree).value,self.freq,signal,*self.PSD_avg ]], delimiter=',')
            self.runs = 0
            self.power = 0
            self.index_k += 1
            if self.scan:
                if self.index_k == len(freqs):
                    self.signal.append(signal)
                    self.heatmap_update.emit(signal, self.index_i)
                    self.index_i += 1
                    self.index_k = 0
                    self.freq = int(freqs[self.index_k])
                    self.sdr.rx_lo = self.freq
                    self.label_freq.setText(f"FREQ: {round(self.freq/1e6)} MHz")
                    if self.index_i == len(self.coords[0]):
                        self.scan = False
                    if self.scan:
                        # self.position_callback(self.index_i,self.index_j)
                        ra = self.coords[0][self.index_i,0] 
                        dec = self.coords[1][self.index_i,0]
                        self.worker.update_position.emit(ra,dec)
                else:
                    self.freq = int(freqs[self.index_k])
                    self.sdr.rx_lo = self.freq
                    self.label_freq.setText(f"FREQ: {round(self.freq/1e6)} MHz")
                    self.worker.start_t = time.time()
                    self.worker.end_of_measure_run.emit()
        else:
            self.worker.end_of_measure_run.emit()




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
        print(f"change position: RA->{coord.ha} DEC->{coord.ha}")
        self.telescope.dish_east.move_to(coord, transform=False)
        self.telescope
        print("reached position")
        self.start_t = time.time()
        self.end_of_measure_run.emit()

        # print(coord)








if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
    