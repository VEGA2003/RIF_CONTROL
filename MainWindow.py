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
    def __init__(self):
        super().__init__()
        self.setWindowTitle('RIF CONTROL :)')
        self.setGeometry(100, 100, 700, 400)

        if telescope_type == "virtual":
            self.can_bus_manager = CANBusManager(channel="test", interface="virtual")
        else:
            self.can_bus_manager = CANBusManager(bitrate = 500000, channel= "PCAN_USBBUS1")

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

        self.layout = QVBoxLayout(self.central_widget)

        self.tab_widget = QTabWidget()
        self.position_gui = positionGUI(self, telescope_type=telescope_type, can_bus_manager=self.can_bus_manager)
        self.temp_gui = tempGUI(self, self.can_bus_manager)
        self.signal_gui = signalGUI(self,sdr_type=sdr_type)
        self.signalpos_gui = signalposGUI(self, self.signal_gui, self.position_gui)

        self.tab_widget.addTab(self.position_gui, "Position")
        self.tab_widget.addTab(self.temp_gui, "Temperature")
        self.tab_widget.addTab(self.signal_gui, "Signal")
        self.tab_widget.addTab(self.signalpos_gui, "HeatMap")
        self.layout.addWidget(self.tab_widget)

        # self.initTab1()
        # self.initTab2()
        # self.initTab3()
        # try:
        #     self.bus = Bus(interface="pcan",channel = "PCAN_USBBUS1",bitrate = 500000)
        # except:
        #     print("failed to intialize CAN-bus, starting virtual bus")
        #     self.bus = Bus(interface="virtual",channel = "PCAN_USBBUS1",bitrate = 500000)

        self.tempL_buffer = []
        self.tempH_buffer = []
        self.tempC_buffer = []
        self.time_buffer = []
        self.output_time_buffer = []
        self.output_buffer = []
        self.boardTemp_buffer = []

        self.position_gui.start()

    def initTab1(self):
        layout = QVBoxLayout(self.tab1)
        label = QLabel("Content of Tab 1")
        layout.addWidget(label)

    def initTab2(self):
        layout = QVBoxLayout(self.tab2)
        label = QLabel("Content of Tab 2")
        layout.addWidget(label)

    def initTab3(self):
        layout = QVBoxLayout(self.tab3)
        label = QLabel("Content of Tab 3")
        layout.addWidget(label)

    # def receive(self):
    #     print("receiving.....")
    #     for msg in self.bus:
    #         data = msg.data
    #         if msg.arbitration_id == 0x105:
    #             with lock:
    #                 self.tempL_buffer.append((data[0] + data[1]*256))
    #                 self.tempH_buffer.append((data[4] + data[5]*256))
    #                 self.time_buffer.append(msg.timestamp)
    #         elif msg.arbitration_id == 0x205:
    #             with lock:
    #                 self.boardTemp_buffer.append((data[4] + data[5]*256))
    #         elif msg.arbitration_id == 0x305:
    #             with lock:
    #                 self.output_buffer.append((data[0] + data[1]*256)-0x84E7)
    #                 self.output_time_buffer.append(msg.timestamp)
    #         window.tab2.live_plot()


class signalposGUI(QWidget,):
    update_plot = Signal(int)
    end_of_run = Signal()
    def __init__(self, mainwindow, signalGUI, positionGUI):
        super().__init__()
        self.increments = positionGUI.plotter.increments
        self.drive = positionGUI.plotter.worker.telescope.dish_east.drive_HA
        self.sdr_worker = signalGUI.worker
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


        def update_plot_callback():
            position = self.drive.position
            psd_average = self.sdr_worker.PSD_avg
            data = ((position/self.increments) % 1)*180 
            self.polar_series.append(data, 180)
            print(psd_average)

        def end_of_run_callback():
            QTimer.singleShot(0, self.run) # Run worker again immediately



        def run(self):
            self.update_plot.emit()
            self.end_of_run.emit() # emit the signal to keep the loop going

        self.update_plot.connect(update_plot_callback)
        self.end_of_run.connect(end_of_run_callback)






if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()

    # receive_thread = QThread()
    # receive_thread.setObjectName('receive_thread')
    # t1 = threading.Thread(target=window.receive, daemon=True)
    # t1.start()

    # t2 = threading.Thread(target=tabWidgetApp.tab2.live_plot, daemon=True)
    # t2.start()

    window.show()
    sys.exit(app.exec())
    