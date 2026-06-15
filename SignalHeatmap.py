import sys
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QTabWidget, QWidget, QLabel
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


telescope_type = "virtual" # real or virtual
# sdr_type = "virtual"  # pluto or virtual

class MainWindow(QMainWindow):

    heatmap_update = Signal(int)
    end_of_run = Signal()
    update_position = Signal(int, int)
    plot_position = Signal(int, int)

    def position_callback(self, i, j):
        print("change position")
        ra = self.coords[i, j, 0] * u.radian
        dec = self.coords[i, j, 1] * u.radian
        coord = astropy.coordinates.SkyCoord(ra=ra.to(u.hourangle), dec=dec.to(u.degree))
        self.telescope.dish_east.move_to(coord)
        # print(coord)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('RIF CONTROL :)')
        self.setGeometry(100, 100, 700, 400)

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
        
        self.heatmap = pg.PlotWidget(labels={'left': 'DEC', 'bottom': 'RA'})
        observing_time = Time(datetime.datetime.now())
        sun_coords = astropy.coordinates.get_sun(observing_time)
        _, self.coords = pattern(sun_coords)
        image_array = np.zeros_like(self.coords)
        self.image_array = image_array[:, :, 0]
        self.index_i = 0
        self.index_j = 0
        self.scan = True
        self.imageitem = pg.ImageItem(self.image_array,axisOrder='row-major') # this arg is purely for performance
        self.heatmap.addItem(self.imageitem)
        self.heatmap.getViewBox().invertY(True)

        self.polar_plot = pg.PlotWidget()
        self.polar_scatter = pg.ScatterPlotItem()
        self.polar_plot.addItem(self.polar_scatter)

        for ring in [45,90]: 
            p_ellipse = QtWidgets.QGraphicsEllipseItem(-(ring/2), -(ring/2), ring, ring)  # x, y, width, height
            p_ellipse.setPen(pg.mkPen(color=(255, 255, 255)))
            self.polar_plot.addItem(p_ellipse)
        
        self.label_HA = QLabel(text="---")
        self.label_DEC = QLabel(text="---")

        self.power = 0
        self.runs = 0

        self.main_layout = QVBoxLayout()
        self.widget = QtWidgets.QWidget()
        self.widget.setLayout(self.main_layout)
        self.setCentralWidget(self.widget)
        self.main_layout.addWidget(self.heatmap)
        self.main_layout.addWidget(self.polar_plot)

        self.telescope = Telescope(telescope_type,bitrate=500000)
        self.sdr = self.telescope.receiver.sdr

        def end_of_run_callback():
            QTimer.singleShot(0, self.run) # Run worker again immediately

        def heatmap_callback(signal):
            print(self.index_i, self.index_j)
            self.image_array[self.index_i, self.index_j] = signal
            self.imageitem.setImage(self.image_array, autoLevels=False)

        def plot_position_callback(ha, dec):
            #  print(QThread.currentThread())
            #  data = np.random.randint(0,360, 2)
            # print((data/plotter.increments) % 1)
            #  self.polar_series.append(np.random.randint(0,360), 180)
            self.label_HA.setText(str(ha))
            self.label_DEC.setText(str(dec))
            # self.polar_series.remove(0)
            # self.polar_series.append(data , 180)
            self.polar_scatter.setData([dec*np.cos(ha)], [dec*np.sin(ha)])
    


        self.heatmap_update.connect(heatmap_callback)
        self.end_of_run.connect(end_of_run_callback)
        self.plot_position.connect(plot_position_callback)
        self.update_position.connect(self.position_callback)
        self.telescope.start(skip_init=True)
        # self.position_callback(0,0)
        self.start_t = 0

        # First pass 
        # self.update_position.emit(0,0)
        self.run()



    def run(self):
        # Main loop
        print("loop")
        now = time.time()
        sample = self.sdr.rx()
        self.power += np.sum(np.abs(np.array(sample)**2))
        self.runs += 1
        position_HA = self.telescope.dish_east.drive_HA.position
        position_DEC = self.telescope.dish_east.drive_DEC.position
        coord = self.telescope.dish_east.pos_to_coord(position_HA, position_DEC)
        self.plot_position.emit(position_HA, position_DEC)
        if now > self.start_t + 10:
            self.heatmap_update.emit(self.power)
            self.runs = 0
            self.power = 0
            if self.scan:
                self.index_j +=1
                if self.index_i == len(self.coords[0]):
                    self.index_i += 1
                    if self.index_i == len(self.coords[0]):
                        self.scan = False
                        with open('heatmap_data.csv', 'a') as f:
                            np.savetxt(f, self.image_array, delimiter=',')

                if self.scan:
                    # self.position_callback(self.index_i,self.index_j)
                    self.update_position.emit(self.index_i,self.index_j)
                    self.start_t = time.time()


        self.end_of_run.emit()











if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
    