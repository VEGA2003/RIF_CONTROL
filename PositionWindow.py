from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QTabWidget, QWidget, QLabel,QGridLayout,  QSlider, QHBoxLayout, QPushButton, QComboBox
from PySide6.QtCore import QSize, Qt, QThread, Signal, QObject, QTimer
from PySide6.QtCharts import QPolarChart, QValueAxis, QChartView, QScatterSeries
import sys
import signal
import numpy as np
from virtual_telescope import VirtualTelescope
from telescope_control import Telescope
from sun_calibration import observing_program

class positionGUI(QWidget):
    def __init__(self, mainwindow = None, telescope_type="real", can_bus_manager=None):
        super().__init__()
        self.window = mainwindow
        # self.plot_graph = pg.PlotWidget()
        self.polar = QPolarChart()      
        chartView = QChartView(self.polar)
        
        layout = QVBoxLayout()
        layout.addWidget(chartView)
        
        #Let's create container widget for our chart, for example QFrame
        #Instead the MainWindow you should to substitute your own Widget or Main Form
        
        self.MyFrame = QtWidgets.QFrame(self)
        self.MyFrame.setGeometry(QtCore.QRect(0, 0, 600, 600))
        self.MyFrame.setLayout(layout)
        
        # setting axis
        y_axis = QValueAxis()
        x_axis = QValueAxis()
    
        y_axis.setRange(0,360)
        y_axis.setTickCount(4)
        self.polar.addAxis(y_axis, QPolarChart.PolarOrientationRadial)
                    
        x_axis.setRange(0,360)
        x_axis.setTickCount(5)
        self.polar.addAxis(x_axis, QPolarChart.PolarOrientationAngular)
        
        #Let's draw scatter series
        self.polar_series = QScatterSeries()
        self.polar_series.setMarkerSize(5.0)        
        
        self.polar_series.append(0, 0)
        self.polar_series.append(180, 300)
        
        # for i in range(0,360,10): 
        #     self.polar_series.append(i, i)
            
        self.polar.addSeries(self.polar_series)


        def update_position_callback(data):
            #  print(QThread.currentThread())
            #  data = np.random.randint(0,360, 2)
            # print((data/plotter.increments) % 1)
            #  self.polar_series.append(np.random.randint(0,360), 180)
            self.polar_series.remove(0)
            self.polar_series.append(((data/self.plotter.increments) % 1)*180 , 180)


        def end_of_run_callback():
            QTimer.singleShot(0, self.plotter.run) # Run worker again immediately


        self.plotter = TelescopePlotter(telescope_type, can_bus_manager)
        self.plotter.update_plot.connect(update_position_callback)
        self.plotter.end_of_run.connect(end_of_run_callback)


        self.plotter.run()
        

    def start(self):
        self.plotter.worker.run()

class TelescopePlotter(QObject):
        def __init__(self, telescope_type, can_bus_manager=None):
            super().__init__()

            # Initialize worker and thread
            self.thread = QThread()
            self.worker = TelescopeWorker(telescope_type, can_bus_manager)
            self.worker.moveToThread(self.thread)
            self.increments = self.worker.telescope.revolutions_to_increments
        
        update_plot = Signal(int)
        end_of_run = Signal()

        def run(self):
            self.update_plot.emit(self.worker.drive.position)
            self.end_of_run.emit() # emit the signal to keep the loop going

class TelescopeWorker(QObject):
        def __init__(self, telescope_type, can_bus_manager):
            super().__init__()
            self.telescope = Telescope(telescope_type, can_bus_manager=can_bus_manager)
            self.drive = self.telescope.dish_east.drive_HA

        def run(self):
            self.telescope.start()
            observing_program(self.telescope)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = positionGUI(telescope_type="real")
    window.show()
    window.start()
    signal.signal(signal.SIGINT, signal.SIG_DFL) # this lets control-C actually close the app
    sys.exit(app.exec())