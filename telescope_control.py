from astropy.coordinates import EarthLocation,SkyCoord
from astropy.time import Time
from astropy import units as u
from astropy.coordinates import AltAz
from datetime import datetime
from system_config import ARS2108System, DriveState, bcolors
from enum import Enum, auto
import threading
import time
import datetime
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from can_bus_manager import CANBusManager
import adi
import os
import csv

class DishState(Enum):
    IDLE = auto()
    WAITING_RESPONSE = auto()
    BUSY = auto()
    # WAITING = auto()
    COMPLETED = auto()
    ERROR = auto()

@dataclass
class Task:
    action: Callable
    name: str
    callback: Optional[Callable[[bool, Optional[int]], None]] = None
    


class Telescope():
    def __init__(self):    
        # default observing location is the Huygens building :)
        self.observing_location = EarthLocation(lat='51.816694', lon='5.866694', height=20*u.m)
        self.revolutions_to_increments = 6553600
        self.earth_speed = 1000000
        
        self.lock = threading.Lock()
        self.can_bus_manager = CANBusManager()
        self.request_queue = []
        # self.drives = [self.drive_HA, self.drive_DEC]
        self.drives = [self.drive_HA]
        self.state = DishState.IDLE
        
        self.receiver = Receiver()
        

class Receiver():
    def __init__(self):   
        self.sdr = adi.ad9361('ip:192.168.2.1')
        self.sdr.rx_enabled_channels = [0, 1]
        self.sdr.gain_control_mode_chan0 = 'manual'
        self.sdr.gain_control_mode_chan1 = 'manual'
        self.sdr.rx_hardwaregain_chan0 = 70.0 # dB
        self.sdr.rx_hardwaregain_chan1 = 70.0 # dB
        self.sdr.rx_lo = int(80e6) # Hz
        self.sdr.sample_rate = int(1e6) # Hz
        self.sdr.rx_rf_bandwidth = int(1e6) # filter width, just set it to the same as sample rate for now
        self.sdr.rx_buffer_size = 10000
        
    def sample(self, output_path="output/data.csv"):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if not os.path.exists(output_path):
            with open(output_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile, delimiter=',')
                writer.writerow(["time_stamp", "channel_0", "channel_1"])
            
        with open(output_path, 'a', newline='') as csvfile:
            now = str(datetime.datetime.now().time())
            writer = csv.writer(csvfile, delimiter=',')
            row = [now]
            sample = self.sdr.rx()
            row.append(sample[0].tolist())
            row.append(sample[1].tolist())
            writer.writerow(row)
        
        

class Dish():
    
    def __init__(self, dish_id):    
        # default observing location is the Huygens building :)
        self.dish_id = dish_id
        self.observing_location = EarthLocation(lat='51.816694', lon='5.866694', height=20*u.m)  
        self.dec_offset = 0
        self.ha_offset = 0
        self.conversion_factor_HA = 0.001
        self.conversion_factor_DEC = 0.001
        self.revolutions_to_increments = 6553600
        self.earth_speed = 1000000
        
        self.lock = threading.Lock()
        self.can_bus_manager = CANBusManager()
        self.request_queue = []
        self.drive_HA = ARS2108System(self.dish_id*2 + 1, self.can_bus_manager)
        self.drive_DEC = ARS2108System(self.dish_id*2 + 2, self.can_bus_manager)
        # self.drives = [self.drive_HA, self.drive_DEC]
        self.drives = [self.drive_HA]
        self.state = DishState.IDLE

        
    def start(self):
        for drive in self.drives:
            drive.start()

        self.process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.process_thread.start()
        
    def coord_to_pos(self, ra, dec, observing_time=None):
        if observing_time == None:
            observing_time = Time(datetime.now())
        
        # aa = AltAz(location=self.observing_location, obstime=observing_time)
        # coordAltAz = coord.transform_to(aa)
        coord = SkyCoord(ra, dec)

        lst = t.sidereal_time('mean', longitude=self.observing_location)
        ha = (lst - coord.ra).wrap_at(12*u.hourangle)
        
        posDEC = int(((coord.dec.value - self.dec_offset)*self.conversion_factor_DEC)*self.revolutions_to_increments)
        posHA = int(((ha.value - self.ha_offset)*self.conversion_factor_HA)*self.revolutions_to_increments)
        
        return posDEC, posHA
        
    def move_to(self, ra: str , dec: str, pos=None):
        posDEC, posHA = self.coord_to_pos(ra, dec)
        self.drive_DEC.set_position_sdo(posDEC)
        self.drive_HA.set_position_sdo(posHA)
        while self.drive_DEC.state != DriveState.TARGET_REACHED or self.drive_HA.state !=  DriveState.TARGET_REACHED:
            print(self.drive_DEC.state, self.drive_HA.state)
        self.state = DishState.IDLE
        
    def set_position(self, drive, pos):
        drive.set_position_sdo(pos)
        while drive.state != DriveState.TARGET_REACHED:
            pass
        self.state = DishState.IDLE
        
        
    def wait(self,wait_time):
        print(bcolors.OKBLUE, f"waiting for {wait_time} seconds", bcolors.ENDC)
        time.sleep(wait_time)
        pass
    
    def track(self):
        self.drive_HA.set_velocity(self.earth_speed)
    
    def add_task(self, action, callback: Optional[Callable[[bool, Optional[int]], None]] = None) -> bool:
        """Queue a dish Task """
        task = Task(action, callback)

        with self.lock:
            self.request_queue.append(task)
            queue_length = len(self.request_queue)

        print(
            f"dish task queued for dish {self.dish_id}, (queue length: {queue_length})")
        return True

    
    def _process_loop(self):
        """Main processing loop"""
        while self.running:
            try:
                with self.lock:
                    current_time = time.time()
                    
                    # Process next request if idle
                    if self.state == DishState.IDLE and self.request_queue:
                        self.current_request = self.request_queue.pop(0)
                        print(
                            f"Processing SDO request for node {self.current_request.node_id}, index 0x{self.current_request.index:04X}:{self.current_request.subindex:02X}, value={self.current_request.value}")
                        self._send_current_request()

                time.sleep(0.01)  # Small delay to prevent busy waiting

            except Exception as e:
                print(f"SDO state machine error: {e}")
                import traceback
                traceback.print_exc()
                # Reset state on error
                with self.lock:
                    if self.current_request:
                        self._complete_request(False, None)
                    self.state = DishState.IDLE

    def _send_current_request(self):
        """Send the current SDO request"""
        if not self.current_request:
            return
        self.state = DishState.BUSY
        self.current_request.action()
        self.current_request.callback()
        print("request completed")
        self.IDLE
        return True

    def get_queue_length(self) -> int:
        """Get the number of pending requests"""
        with self.lock:
            return len(self.request_queue)

    def is_busy(self) -> bool:
        """Check if the state machine is busy"""
        with self.lock:
            return self.state != DishState.IDLE or len(self.request_queue) > 0
    

