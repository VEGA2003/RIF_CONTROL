from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QTabWidget, QWidget, QLabel,QGridLayout,  QSlider, QHBoxLayout, QPushButton, QComboBox
from PySide6.QtCore import QSize, Qt, QThread, Signal, QObject, QTimer
import pyqtgraph as pg
import can
from can.interface import Bus
import sys
import threading
import numpy as np
import signal # lets control-C actually close the app
import time
from virtual_telescope import VirtualSDR

lock = threading.Lock()

# Defaults
fft_size = 4096 # determines buffer size
num_rows = 200
center_freq = 1420e6
sample_rates = [5, 2, 1, 0.5] # MHz
sample_rate = sample_rates[0] * 1e6
time_plot_samples = 500
gain = 10 # 0 to 73 dB. int

sdr_type = "pluto" # "virtual" or "usrp" or "pluto"

# Init SDR

class signalGUI(QWidget,):
    def __init__(self, mainwindow = None, sdr_type="virtual"):
        super().__init__()
        self.window = mainwindow
        self.setWindowTitle("The PySDR Spectrum Analyzer")
        self.setFixedSize(QSize(900, 600)) # window size, starting size should fit on 1920 x 1080
        self.sdr_type = sdr_type

        if sdr_type == "pluto":
            import adi
            self.sdr = adi.Pluto("ip:192.168.2.1")
        else:
            self.sdr = VirtualSDR()
        
        self.sdr.rx_lo = int(center_freq)
        self.sdr.sample_rate = int(sample_rate)
        self.sdr.rx_rf_bandwidth = int(sample_rate*0.8) # antialiasing filter bandwidth
        self.sdr.rx_buffer_size = int(fft_size)
        self.sdr.gain_control_mode_chan0 = 'manual'
        self.sdr.rx_hardwaregain_chan0 = gain # dB
        self.sdr.rx_enabled_channels = [0]

        self.spectrogram_min = 0
        self.spectrogram_max = 0

        layout = QGridLayout(self) # overall layout

        # Initialize worker and thread
        # self.sdr_thread = QThread()
        # self.sdr_thread.setObjectName('SDR_Thread') # so we can see it in htop, note you have to hit F2 -> Display options -> Show custom thread names
        self.worker = SDRWorker(self.sdr_type, self.sdr)
        # worker.moveToThread(self.sdr_thread)

        # Time plot
        time_plot = pg.PlotWidget(labels={'left': 'Amplitude', 'bottom': 'Time [microseconds]'})
        time_plot.setMouseEnabled(x=False, y=True)
        time_plot.setYRange(-1.1, 1.1)
        time_plot_curve_i = time_plot.plot([])
        time_plot_curve_q = time_plot.plot([])
        layout.addWidget(time_plot, 1, 0)

        # Time plot auto range buttons
        time_plot_auto_range_layout = QVBoxLayout()
        layout.addLayout(time_plot_auto_range_layout, 1, 1)
        auto_range_button = QPushButton('Auto Range')
        auto_range_button.clicked.connect(lambda : time_plot.autoRange()) # lambda just means its an unnamed function
        time_plot_auto_range_layout.addWidget(auto_range_button)
        auto_range_button2 = QPushButton('-1 to +1\n(ADC limits)')
        auto_range_button2.clicked.connect(lambda : time_plot.setYRange(-1.1, 1.1))
        time_plot_auto_range_layout.addWidget(auto_range_button2)

        # Freq plot
        freq_plot = pg.PlotWidget(labels={'left': 'PSD', 'bottom': 'Frequency [MHz]'})
        freq_plot.setMouseEnabled(x=False, y=True)
        freq_plot_curve = freq_plot.plot([])
        freq_plot.setXRange(center_freq/1e6 - sample_rate/2e6, center_freq/1e6 + sample_rate/2e6)
        freq_plot.setYRange(-30, 20)
        layout.addWidget(freq_plot, 2, 0)

        # Freq auto range button
        auto_range_button = QPushButton('Auto Range')
        auto_range_button.clicked.connect(lambda : freq_plot.autoRange()) # lambda just means its an unnamed function
        layout.addWidget(auto_range_button, 2, 1)

        # Layout container for waterfall related stuff
        waterfall_layout = QHBoxLayout()
        layout.addLayout(waterfall_layout, 3, 0)

        # Waterfall plot
        
        waterfall = pg.PlotWidget(labels={'left': 'Signal', 'bottom': 'Time [seconds]'})
        waterfall.setMouseEnabled(x=False, y=True)
        # time_plot.setYRange(-1.1, 1.1)
        waterfall_curve = waterfall.plot([])
        waterfall.setXRange(0, 3600)
        waterfall.setYRange(0, 100000)
        waterfall_layout.addWidget(waterfall)
        # waterfall.setMouseEnabled(x=True, y=True)

        # waterfall = pg.PlotWidget(labels={'left': 'Time [s]', 'bottom': 'Frequency [MHz]'})
        # imageitem = pg.ImageItem(axisOrder='col-major') # this arg is purely for performance
        # waterfall.addItem(imageitem)
        # waterfall.setMouseEnabled(x=False, y=False)
        # waterfall_layout.addWidget(waterfall)

        # # Colorbar for waterfall
        # colorbar = pg.HistogramLUTWidget()
        # colorbar.setImageItem(imageitem) # connects the bar to the waterfall imageitem
        # colorbar.item.gradient.loadPreset('viridis') # set the color map, also sets the imageitem
        # imageitem.setLevels((-30, 20)) # needs to come after colorbar is created for some reason
        # waterfall_layout.addWidget(colorbar)

        # Waterfall auto range button
        # auto_range_button = QPushButton('Auto Range\n(-2σ to +2σ)')
        # def update_colormap():
        #     imageitem.setLevels((self.spectrogram_min, self.spectrogram_max))
        #     colorbar.setLevels(self.spectrogram_min, self.spectrogram_max)
        # auto_range_button.clicked.connect(update_colormap)
        # layout.addWidget(auto_range_button, 3, 1)

        # Freq slider with label, all units in kHz
        freq_slider = QSlider(Qt.Orientation.Horizontal)
        freq_slider.setRange(0, int(6e6))
        freq_slider.setValue(int(center_freq/1e3))
        freq_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        freq_slider.setTickInterval(int(1e6))
        freq_slider.sliderMoved.connect(self.worker.update_freq) # there's also a valueChanged option
        freq_label = QLabel()
        def update_freq_label(val):
            freq_label.setText("Frequency [MHz]: " + str(val/1e3))
            freq_plot.autoRange()
        freq_slider.sliderMoved.connect(update_freq_label)
        update_freq_label(freq_slider.value()) # initialize the label
        layout.addWidget(freq_slider, 4, 0)
        layout.addWidget(freq_label, 4, 1)

        # Gain slider with label
        gain_slider = QSlider(Qt.Orientation.Horizontal)
        gain_slider.setRange(0, 73)
        gain_slider.setValue(gain)
        gain_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        gain_slider.setTickInterval(2)
        gain_slider.sliderMoved.connect(self.worker.update_gain)
        gain_label = QLabel()
        def update_gain_label(val):
            gain_label.setText("Gain: " + str(val))
        gain_slider.sliderMoved.connect(update_gain_label)
        update_gain_label(gain_slider.value()) # initialize the label
        layout.addWidget(gain_slider, 5, 0)
        layout.addWidget(gain_label, 5, 1)

        # Sample rate dropdown using QComboBox
        sample_rate_combobox = QComboBox()
        sample_rate_combobox.addItems([str(x) + ' MHz' for x in sample_rates])
        sample_rate_combobox.setCurrentIndex(0) # should match the default at the top
        sample_rate_combobox.currentIndexChanged.connect(self.worker.update_sample_rate)
        sample_rate_label = QLabel()
        def update_sample_rate_label(val):
            sample_rate_label.setText("Sample Rate: " + str(sample_rates[val]) + " MHz")
        sample_rate_combobox.currentIndexChanged.connect(update_sample_rate_label)
        update_sample_rate_label(sample_rate_combobox.currentIndex()) # initialize the label
        layout.addWidget(sample_rate_combobox, 6, 0)
        layout.addWidget(sample_rate_label, 6, 1)



        # Signals and slots stuff
        def time_plot_callback(samples):
            time_plot_curve_i.setData(samples.real)
            time_plot_curve_q.setData(samples.imag)

        def freq_plot_callback(PSD_avg):
            # TODO figure out if there's a way to just change the visual ticks instead of the actual x vals
            f = np.linspace(freq_slider.value()*1e3 - self.worker.sample_rate/2.0, freq_slider.value()*1e3 + self.worker.sample_rate/2.0, fft_size) / 1e6
            freq_plot_curve.setData(f, PSD_avg)
            freq_plot.setXRange(freq_slider.value()*1e3/1e6 - self.worker.sample_rate/2e6, freq_slider.value()*1e3/1e6 + self.worker.sample_rate/2e6)

        # def waterfall_plot_callback(spectrogram):
        #     imageitem.setImage(spectrogram, autoLevels=False)
        #     sigma = np.std(spectrogram)
        #     mean = np.mean(spectrogram)
        #     self.spectrogram_min = mean - 2*sigma # save to window state
        #     self.spectrogram_max = mean + 2*sigma

        def waterfall_plot_callback(PSD_total):
            data = PSD_total
            waterfall_curve.setData(data)

            # self.fig.setXRange(xdata[max(0, len(xdata)-600)], max(10, xdata[-1]))

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

        self.worker.time_plot_update.connect(time_plot_callback) # connect the signal to the callback
        self.worker.freq_plot_update.connect(freq_plot_callback)
        self.worker.waterfall_plot_update.connect(waterfall_plot_callback)
        self.worker.freq_plot_update.connect(save_data)
        self.worker.waterfall_plot_update.connect(save_data2)
        self.worker.sweep_update.connect(self.worker.sweep)

        self.worker.end_of_run.connect(end_of_run_callback)

        self.worker.run()
        # self.sdr_thread.started.connect(self.worker.run) # kicks off the worker when the thread starts
        # self.sdr_thread.start()

class SDRWorker(QObject):
    def __init__(self, sdr_type, sdr=None):
        super().__init__()
        self.start_t = 0
        self.integrated_PSD = 0
        self.power = 0
        self.runs = 0
        self.gain = gain
        self.sample_rate = sample_rate
        self.freq = 0 # in kHz, to deal with QSlider being ints and with a max of 2 billion
        self.spectrogram = -50*np.ones((fft_size, num_rows))
        self.PSD_avg = -50*np.ones(fft_size)
        self.PSD_total = []
        self.freq_range = np.fft.fftfreq(fft_size, 1/sample_rate)
        self.sdr_type = sdr_type
        if sdr !=None:
            self.sdr = sdr

        self.sweep_start = 1000e6
        self.sweep_stop = 2000e6
        self.sweep_steps = 100
        self.sweep_index = 0
        self.sweep_complete = True

        self.num_samples = self.sdr.rx_buffer_size
        self.num_reads = 1
        self.buffer_clear_reads = 1
        self.delay_time = 0.01

        self.frequencies = np.linspace(self.sweep_start, self.sweep_stop, self.sweep_steps)

    # PyQt Signals
    time_plot_update = Signal(np.ndarray)
    freq_plot_update = Signal(np.ndarray)
    waterfall_plot_update = Signal(np.ndarray)
    sweep_update = Signal()
    end_of_run = Signal() # happens many times a second

    # PyQt Slots
    def update_freq(self, val): # TODO: WE COULD JUST MODIFY THE SDR IN THE GUI THREAD
        print("Updated freq to:", val, 'kHz')
        if self.sdr_type == "pluto":
            self.sdr.rx_lo = int(val*1e3)
        # elif sdr_type == "usrp":
        #     usrp.set_rx_freq(uhd.libpyuhd.types.tune_request(val*1e3), 0)
        #     flush_buffer()

    def update_gain(self, val):
        print("Updated gain to:", val, 'dB')
        self.gain = val
        if self.sdr_type == "pluto":
            self.sdr.rx_hardwaregain_chan0 = val
        # elif sdr_type == "usrp":
        #     usrp.set_rx_gain(val, 0)
        #     flush_buffer()

    def update_sample_rate(self, val):
        print("Updated sample rate to:", sample_rates[val], 'MHz')
        if self.sdr_type == "pluto":
            self.sdr.sample_rate = int(sample_rates[val] * 1e6)
            self.sdr.freq_range = np.fft.fftfreq(fft_size, 1/sample_rates[val])
            self.sdr.rx_rf_bandwidth = int(sample_rates[val] * 1e6 * 0.8)
        # elif sdr_type == "usrp":
        #     usrp.set_rx_rate(sample_rates[val] * 1e6, 0)
        #     flush_buffer()

    def sweep(self):
        # Sweep in progress
        if not self.sweep_complete and self.sweep_index < len(self.frequencies):
            freq = self.frequencies[self.sweep_index]
            self.sdr.rx_lo = int(freq)
            time.sleep(self.delay_time)
            # self.freq_label.setText(f"Current Frequency: {freq/1e9:.2f} GHz")
            # Clear RX buffer
            # for _ in range(self.buffer_clear_reads):
            #     self.sdr.rx()
            # Accumulate signals
            # accumulated_signal = np.zeros(self.num_samples * self.num_reads, dtype=np.complex64)
            # for j in range(self.num_reads):
            #     rx_signal = self.sdr.rx()[0]
            #     # Arbitrary scaling factor
            #     accumulated_signal[j*self.num_samples:(j+1)*self.num_samples] = (rx_signal / 2**12) * 5.5

            # Compute amplitude (dB)
            # amp_lin = self.extract_amplitude(accumulated_signal)
            # amp_db = 20 * np.log10(amp_lin)
            # freq_ghz = freq / 1e9

            # self.freq_list.append(freq_ghz)
            # self.amp_list.append(amp_db)

            self.sweep_index += 1
            # self.status.showMessage(f"Sweeping: {freq_ghz:.2f} GHz, Amplitude: {amp_db:.1f} dB")
            # print(f"Freq: {freq/1e6:.2f} MHz, Amp: {amp_db:.2f} dB")

        # Sweep just finished
        elif not self.sweep_complete:
            self.sweep_complete = True

    # Main loop
    def run(self):
        now = time.time()
        sample = self.sdr.rx()
        self.time_plot_update.emit(sample[0:time_plot_samples])
        PSD = 10.0*np.log10(np.abs(np.fft.fftshift(np.fft.fft(sample)))**2/fft_size)
        # self.PSD_avg = self.PSD_avg * 0.99 + PSD * 0.01
        self.power += np.sum(np.abs(np.array(sample)**2))
        self.integrated_PSD += PSD
        self.runs += 1
        if now > self.start_t +1:
            self.start_t = now
            self.PSD_avg = self.integrated_PSD/self.runs
            self.freq_plot_update.emit(self.PSD_avg)
            self.PSD_total.append(self.power/self.runs)
            self.waterfall_plot_update.emit(self.PSD_total)

            self.runs = 0
            self.integrated_PSD = 0
            self.power = 0
        # if self.sdr_type == "pluto":
        #     samples = self.sdr.rx()/2**11 # Receive samples
        # elif self.sdr_type == "virtual":
        #     tone = np.exp(2j*np.pi*self.sample_rate*0.1*np.arange(fft_size)/self.sample_rate)
        #     noise = np.random.randn(fft_size) + 1j*np.random.randn(fft_size)
        #     samples = self.gain*tone*0.02 + 0.1*noise
        #     # Truncate to -1 to +1 to simulate ADC bit limits
        #     np.clip(samples.real, -1, 1, out=samples.real)
        #     np.clip(samples.imag, -1, 1, out=samples.imag)

        self.spectrogram[:] = np.roll(self.spectrogram, 1, axis=1) # shifts waterfall 1 row
        self.spectrogram[:,0] = PSD # fill last row with new fft results
        # self.waterfall_plot_update.emit(self.spectrogram)
        # PSD_tot =  np.trapezoid(np.abs(np.fft.fftshift(np.fft.fft(samples)))**2/fft_size, dx = self.sample_rate/fft_size)

        if not self.sweep_complete:
            self.sweep_update.emit()

        self.end_of_run.emit() # emit the signal to keep the loop going


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = signalGUI(sdr_type=sdr_type)
    window.show()
    signal.signal(signal.SIGINT, signal.SIG_DFL) # this lets control-C actually close the app
    sys.exit(app.exec())
    