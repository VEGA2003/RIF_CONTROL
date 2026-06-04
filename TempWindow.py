from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QTabWidget, QWidget, QLabel
import pyqtgraph as pg
import can
from can.interface import Bus
import sys
import threading
import numpy as np

lock = threading.Lock()

class tempGUI(QWidget):
    def __init__(self, mainwindow = None):
        super().__init__()
        self.window = mainwindow
        # self.plot_graph = pg.PlotWidget()

        hour = [1,2,3,4,5,6,7,8,9,10]
        temperature = [30,32,34,32,33,31,29,32,35,45]

        # #Add Background colour to white
        # self.plot_graph.setBackground('w')
        # # Add Title
        # self.plot_graph.setTitle("Your Title Here", color="b", size="30pt")
        # # Add Axis Labels
        # styles = {"color": "#f00", "font-size": "20px"}
        # self.plot_graph.setLabel("left", "Temperature (°C)", **styles)
        # self.plot_graph.setLabel("bottom", "Hour (H)", **styles)
        # #Add legend
        # self.plot_graph.addLegend()
        # #Add grid
        # self.plot_graph.showGrid(x=True, y=True)
        # #Set Range
        # self.plot_graph.setXRange(0, 10, padding=0)
        # self.plot_graph.setYRange(20, 55, padding=0)

        # pen = pg.mkPen(color=(255, 0, 0))
        # self.plot_graph.plot(hour, temperature, name="Sensor 1",  pen=pen, symbol='+', symbolSize=30, symbolBrush=('b'))
        self.fig = pg.PlotWidget()
        self.fig.setBackground("w")

        pen_r = pg.mkPen(color=(255, 0, 0))
        pen_g = pg.mkPen(color=(0, 255, 0))
        pen_b = pg.mkPen(color=(0, 0, 255))
        self.line1 = self.fig.plot(hour, temperature,  pen=pen_b)
        self.line2 = self.fig.plot([], [], pen=pen_r)
        self.line4 = self.fig.plot([], [], pen=pen_g)
        # self.fig.setYRange(1701, 2869)
        self.fig.setXRange(0, 1000)
        # self.ax.tick_params(labelbottom=False)
        # self.ax2 = self.fig.add_subplot(gs[1], sharex=self.ax)
        # self.line3, = self.ax2.plot([], [], "g-")
        # self.ax2.set_ylim(-5, 5.2)
        
        # self.fig.tight_layout()
        # self.plotting = True

        # ----- Main window -----
        # self.root = tk.Tk()
        # self.root.title("LNA Temperature Viewer :)")
        # self.root.geometry("840x500")  # better window size


        # ----- Layout frames -----
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
        # main_frame = tk.Frame(self.root)
        # main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # left_frame = tk.Frame(main_frame)
        # left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # right_frame = tk.Frame(main_frame, width=200)
        # right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10)
        
        # right_frame_up = tk.Frame(right_frame, width=200)
        # right_frame_up.pack(side="top")
        # right_frame_down = tk.Frame(right_frame, width=200)
        # right_frame_down.pack(side="bottom", fill=tk.Y)

        # # ----- Plot area -----
        # self.canvas = FigureCanvasTkAgg(self.fig, master=left_frame)
        # self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # # ----- Utilities -----
        font_name = "Arial"
        size = 14
        self.templabelH = QtWidgets.QLabel(text="Temperature H: -- °C")
        self.right_up.addWidget(self.templabelH)
        self.templabelH.setFont(QtGui.QFont(font_name, size))
        # self.templabelH.pack(pady=10)    
        self.templabelL = QtWidgets.QLabel(text="Temperature L: -- °C")
        self.right_up.addWidget(self.templabelL)
        self.templabelL.setFont(QtGui.QFont(font_name, size))
        # self.templabelL.pack(pady=10)
        self.boardtempLabel = QtWidgets.QLabel(text="Board Temp: -- °C")
        self.right_up.addWidget(self.boardtempLabel)
        self.boardtempLabel.setFont(QtGui.QFont(font_name, size))
        # self.boardtempLabel.pack(pady=10)
        self.outLabel = QtWidgets.QLabel( text="DACoutput: -- ")
        self.right_up.addWidget(self.outLabel)
        self.outLabel.setFont(QtGui.QFont(font_name, size))
        # self.outLabel.pack(pady=5)
        self.outVLabel = QtWidgets.QLabel( text="Output: -- V")
        self.right_up.addWidget(self.outVLabel)
        self.outVLabel.setFont(QtGui.QFont(font_name, size))
        # self.outVLabel.pack(pady=5)

        # self.pausebutton = tk.Button(right_frame_down, text="â€–", command=self.pause, width=10)
        # self.pausebutton.grid(column=0, row=0, pady=10)
        # self.savebutton = tk.Button(right_frame_down, text="SAVE", command=self.save, width=10)
        # self.savebutton.grid(column=1, row=0, pady=10)
        
        # self.textbox = tk.Text(right_frame_down, width=10, height=1)
        # self.textbox.grid(column=0, row=1, pady=10)
        # self.sendbutton = tk.Button(right_frame_down, text= "SEND", command=self.send, width=10)
        # self.sendbutton.grid(column= 1, row=1, pady=10)
    
        # self.bus = Bus(interface="pcan",channel = "PCAN_USBBUS1",bitrate = 500000, can_filters=filters)
        
        # # control
        # self.control = True
        # self.set = tk.Text(right_frame_down, width=10, height=1)
        # self.set.grid(column=1, row=2)
        # set_label = tk.Label(right_frame_down, text="SETPOINT: ", font=("Arial", 10))
        # set_label.grid(column=0, row=2)
        # self.P = tk.Text(right_frame_down, width=10, height=1)
        # self.P.grid(column=1, row=3)
        # P_label = tk.Label(right_frame_down, text="P_GAIN: ", font=("Arial", 10))
        # P_label.grid(column=0, row=3)
        # self.I = tk.Text(right_frame_down, width=10, height=1)
        # self.I.grid(column=1, row=4)
        # I_label = tk.Label(right_frame_down, text="I_GAIN: ", font=("Arial", 10))
        # I_label.grid(column=0, row=4)
        # self.D = tk.Text(right_frame_down, width=10, height=1)
        # self.D.grid(column=1, row=5)
        # D_label = tk.Label(right_frame_down, text="D_GAIN: ", font=("Arial", 10))
        # D_label.grid(column=0, row=5)
        # self.submitbutton = tk.Button(right_frame_down, text= "SUBMIT", command=self.values, width=10)
        # self.submitbutton.grid(column=1, row=6, pady=10)
        
        # self.P_GAIN = 0.0
        # self.I_GAIN = 0.0
        # self.D_GAIN = 0.0
        
        # self.setpoint = 21
        # self.sum_error = 0.0              
        # self.previous_error = 0.0
        
    # def receive(self):
    #     print("receiving.....")
    #     for msg in self.bus:
    #         data = msg.data
    #         if msg.arbitration_id == 0x105:
    #             with lock:
    #                 tempL_buffer.append((data[0] + data[1]*256))
    #                 tempH_buffer.append((data[4] + data[5]*256))
    #                 time_buffer.append(msg.timestamp)
    #         elif msg.arbitration_id == 0x205:
    #             with lock:
    #                 boardTemp_buffer.append((data[4] + data[5]*256))
    #         elif msg.arbitration_id == 0x305:
    #             with lock:
    #                 output_buffer.append((data[0] + data[1]*256)-0x8AFF)
    #                 output_time_buffer.append(msg.timestamp)
        
    def live_plot(self):
        with lock:
            y1data = self.window.tempL_buffer.copy()
            y2data = self.window.tempH_buffer.copy()
            y3data = self.window.output_buffer.copy()
            boardTemp = self.window.boardTemp_buffer.copy()
            
            xdata = np.array(self.window.time_buffer.copy())
            x2data = np.array(self.window.output_time_buffer.copy()) 
        if len(y1data) > 0:
            xdata = xdata - xdata[0]
            self.line1.setData(xdata, y1data)
            # self.line1.set_ydata(y1data)
            # self.line2.set_xdata(xdata)
            # self.line2.set_ydata(y2data)
  #          self.line4.set_xdata(xdata)
  #          self.line4.set_ydata(y4data)
            self.fig.setXRange(xdata[max(0, len(xdata)-600)], max(10, xdata[-1]))
            # self.ax.relim()
            # self.ax.autoscale_view(True, True, True)
            # update label properly:
            # self.templabelL.config(text=f"Temperature L: { self.temp_conv(y1data[-1])} °C")
            # self.templabelH.config(text=f"Temperature H: {self.temp_conv(y2data[-1])} °C")
            self.templabelL.setText(f"Temperature L: {y1data[-1]} °C")
            self.templabelH.setText(f"Temperature H: {y2data[-1]} °C")
            
#             fields = ['TIME', 'TEMP_H', 'TEMP_L', 'SETPOINT', 'OUTPUT']
            
            
#             # if self.control:
#             #     self.PIDcontrol(y2data[-1])
        if len(y3data) > 0:
            x2data = x2data - x2data[0]
            v = np.array(y3data) * -0.000149
            self.outLabel.setText("DACoutput: " + f"{int(y3data[-1] + 0x84E7):04x}".upper())
            self.outVLabel.setText(f"Output: {round(v[-1], 3)} V")
            # self.line3.set_xdata(x2data)
            # self.line3.set_ydata(v)
        
#         if len(y3data) > 0 and len(y1data) >0:
#             new_row = {'TIME': xdata[-1] , 'TEMP_H':y2data[-1], 'TEMP_L': y1data[-1], 'SETPOINT' : self.setpoint,'OUTPUT':y3data[-1]}
            
#             with open('temp_data.csv', 'a', newline='') as f:
#                 writer = DictWriter(f, fieldnames=fields)
#                 writer.writerow(new_row)
            
#         if len(boardTemp) >0:
#             self.boardtempLabel.config(text=f"Board Temp: {boardTemp[-1]} °C")
#         self.canvas.draw()
#         if self.plotting:
#             self.root.after(100, self.live_plot)

#     def pause(self):
#         self.plotting = not self.plotting
#         if self.plotting:
#             self.pausebutton.config(text="â€–")
#             self.root.after(100, self.live_plot)
#         else:
#             self.pausebutton.config(text="â–¶ï¸Ž")
        
#     def temp_conv(self, x):
#         a = 1.712 * (10**-2)
#         b = -1.912 * 10
#         return np.round(a*x + b,1)
    
#     def send(self):
#         text = self.textbox.get("1.0", "end-1c")
#         msg = can.Message(arbitration_id=0x115,is_extended_id=False ,data=[int(text[:2], 16), int(text[2:4], 16), 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
#         self.bus.send(msg)
#         print(text, msg)
        
#     def values(self):
#         self.setpoint = self.set.get("1.0", "end-1c")
#         self.P_GAIN = self.P.get("1.0", "end-1c")
#         self.I_GAIN = self.I.get("1.0", "end-1c")
#         self.D_GAIN = self.D.get("1.0", "end-1c")
        
#         s = f'{int(self.setpoint):04x}'
#         p = f'{int(self.P_GAIN):04x}'
#         i = f'{int(self.I_GAIN):04x}'
#         d = f'{int(self.D_GAIN):04x}'
        
#         msg = can.Message(arbitration_id=0x215,is_extended_id=False ,data=[int(s[:2], 16), int(s[2:4], 16), int(p[:2], 16), int(p[2:4], 16), int(i[:2], 16), int(i[2:4], 16), int(d[:2], 16), int(d[2:4], 16)])
#         self.bus.send(msg)
        
#     def save(self):
#         x = self.line1.get_xdata()
#         y1 = self.line1.get_ydata()
#         y2 = self.line2.get_ydata()
#         y3 = self.line3.get_ydata()

#         data = np.stack((x,y1,y2,y3), axis = 1)
#         np.savetxt("temp_data_extra.csv", data , delimiter=",")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = tempGUI()
    window.show()
    sys.exit(app.exec())
    