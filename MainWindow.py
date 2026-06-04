import sys
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtCore import QThread 
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QTabWidget, QWidget, QLabel
from TempWindow import tempGUI
from SignalWindow import signalGUI
from PositionWindow import positionGUI
import threading
from can.interface import Bus

# tempL_buffer = []
# tempH_buffer = []
# tempC_buffer = []
# time_buffer = []
# output_time_buffer = []
# output_buffer = []
# boardTemp_buffer = []
lock = threading.Lock()

telescope_type = "virtual"
sdr_type = "virtual"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('RIF CONTROL :)')
        self.setGeometry(100, 100, 700, 400)

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
        self.tab1 = positionGUI(self)
        self.tab2 = tempGUI(self)
        self.tab3 = signalGUI(self,sdr_type=sdr_type)

        self.tab_widget.addTab(self.tab1, "Position")
        self.tab_widget.addTab(self.tab2, "Temperature")
        self.tab_widget.addTab(self.tab3, "Signal")

        self.layout.addWidget(self.tab_widget)

        # self.initTab1()
        # self.initTab2()
        # self.initTab3()
        try:
            self.bus = Bus(interface="pcan",channel = "PCAN_USBBUS1",bitrate = 500000)
        except:
            print("failed to intialize CAN-bus, starting virtual bus")
            self.bus = Bus(interface="virtual",channel = "PCAN_USBBUS1",bitrate = 500000)

        self.tempL_buffer = []
        self.tempH_buffer = []
        self.tempC_buffer = []
        self.time_buffer = []
        self.output_time_buffer = []
        self.output_buffer = []
        self.boardTemp_buffer = []

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

    def receive(self):
        print("receiving.....")
        for msg in self.bus:
            data = msg.data
            if msg.arbitration_id == 0x105:
                with lock:
                    self.tempL_buffer.append((data[0] + data[1]*256))
                    self.tempH_buffer.append((data[4] + data[5]*256))
                    self.time_buffer.append(msg.timestamp)
            elif msg.arbitration_id == 0x205:
                with lock:
                    self.boardTemp_buffer.append((data[4] + data[5]*256))
            elif msg.arbitration_id == 0x305:
                with lock:
                    self.output_buffer.append((data[0] + data[1]*256)-0x84E7)
                    self.output_time_buffer.append(msg.timestamp)
            window.tab2.live_plot()

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
    