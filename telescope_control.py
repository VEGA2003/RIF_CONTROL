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
from virtual_telescope import VirtualTelescope

class ComponentState(Enum):
    IDLE = auto()
    WAITING_RESPONSE = auto()
    BUSY = auto()
    # WAITING = auto()
    COMPLETED = auto()
    ERROR = auto()

@dataclass
class Task:
    action: Callable
    args : tuple
    name: str
    callback: Optional[Callable[[bool, Optional[int]], None]] = None


@dataclass
class Observation:
    ra:  float
    dec: float
    duration: int 


class Telescope():
    def __init__(self, virtual=False, bitrate: int = 500000):    
        # default observing location is the Huygens building :)
        self.observing_location = EarthLocation(lat='51.816694', lon='5.866694', height=20*u.m)
        self.revolutions_to_increments = 6553600
        self.earth_speed = 1000000
        self.virtual = virtual
        self.lock = threading.Lock()
        
        if self.virtual:
            self.can_bus_manager = CANBusManager(channel="test", interface="virtual")
            self.virtual_telescope = VirtualTelescope(4)
        else:
            self.can_bus_manager = CANBusManager(bitrate = bitrate)
            
        self.request_queue = []
        # self.drives = [self.drive_HA, self.drive_DEC]
        # self.drives = [self.drive_HA]
        
        self.dish_east = Dish(0, self.can_bus_manager)
        self.dish_west = Dish(1, self.can_bus_manager)
        
        self.dishes = [self.dish_east, self.dish_west]
        self.dishes_in_position = 0
        self.state = ComponentState.IDLE
        
        # Start processing thread
        self.running = False
        self.process_thread = None
        
        try:
            self.receiver = Receiver()
        except Exception as e: 
            print(e)
            self.receiver = None
            "no receiver connected"
        
    def start(self):
        self.running = True
        
        if self.virtual:
            self.virtual_telescope.start()
            
        for dish in self.dishes:
            dish.start()

        self.process_thread = threading.Thread(target=self._process_loop)
        self.process_thread.start()
        
    def add_task(self, action, *args , callback: Optional[Callable[[bool, Optional[int]], None]] = None) -> bool:
        """Queue a Telescope Task """
        task = Task(action, args ,callback)

        with self.lock:
            self.request_queue.append(task)
            queue_length = len(self.request_queue)

        print(
            f"dish task queued for the Telescope, (queue length: {queue_length})")
        return True
    
    def move_to(self, ra: str , dec: str, pos=None):
        self.dishes_in_position = 0
        for dish in self.dishes:
            dish.add_task(dish.move_to, ra, dec, callback=self.move_to_followup)
        
    def move_to_followup(self):
        self.dishes_in_position += 1
        if len(self.dishes) == self.dishes_in_position:
            self.state = ComponentState.IDLE
        
    def add_survey(self, survey, point_duration=30*60):
        """
        Add survey to queue
        """
        for point in survey:
            self.add_task(self.move_to(point.ra, point.dec))
            self.add_task(self.wait(point_duration))
        
    def wait(self,wait_time):
        print(bcolors.OKBLUE, f"waiting for {wait_time} seconds", bcolors.ENDC)
        time.sleep(wait_time)
        pass
    
    def _process_loop(self):
        """Main processing loop"""
        while self.running:
            try:
                with self.lock:
                    current_time = time.time()
                    
                    # Process next request if idle
                    if self.state == ComponentState.IDLE and self.request_queue:
                        self.current_request = self.request_queue.pop(0)
                        print(f"Processing request for telescope")
                        self._send_current_request()

                time.sleep(0.01)  # Small delay to prevent busy waiting

            except Exception as e:
                print(f"Dish error: {e}")
                self.state = ComponentState.IDLE
            #     import traceback
            #     traceback.print_exc()
            #     # Reset state on error
            #     with self.lock:
            #         if self.current_request:
            #             self._complete_request(False, None)
            #         self.state = ComponentState.IDLE    
                    
    def _send_current_request(self):
        """Send the current SDO request"""
        if not self.current_request:
            return
        self.state = ComponentState.BUSY
        self.current_request.action(*self.current_request.args)
        if self.current_request.callback != None:
            self.current_request.callback()
        print("request completed")
        self.state = ComponentState.IDLE
        return True

    def get_queue_length(self) -> int:
        """Get the number of pending requests"""
        with self.lock:
            return len(self.request_queue)

    def is_busy(self) -> bool:
        """Check if the state machine is busy"""
        with self.lock:
            return self.state != ComponentState.IDLE or len(self.request_queue) > 0    
            

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
        
    def sample(self, output_path="output/data.csv", record_all_data= False):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if not os.path.exists(output_path):
            with open(output_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile, delimiter=',')
                if record_all_data:
                    writer.writerow(["time_stamp", "channel_0", "channel_1"])
            
        with open(output_path, 'a', newline='') as csvfile:
            now = str(datetime.datetime.now().time())
            writer = csv.writer(csvfile, delimiter=',')
            row = [now]
            sample = self.sdr.rx()
            if record_all_data:
                row.append(sample[0].tolist())
                row.append(sample[1].tolist())
            writer.writerow(row)
            

        

class Dish():
    
    def __init__(self, dish_id, can_bus_manager = None):    
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
        if can_bus_manager == None :
            self.can_bus_manager = CANBusManager()
        else:
            self.can_bus_manager = can_bus_manager
            
        self.request_queue = []
        self.drive_HA = ARS2108System(self.dish_id*2 + 1, self.can_bus_manager)
        self.drive_DEC = ARS2108System(self.dish_id*2 + 2, self.can_bus_manager)
        self.drives = [self.drive_HA, self.drive_DEC]
        # self.drives = [self.drive_HA]
        self.state = ComponentState.IDLE
        
        # Start processing thread
        self.running = False
        self.process_thread = None

        
    def start(self):
        for drive in self.drives:
            drive.start()
            
        self.running = True
        self.process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.process_thread.start()
        
    def coord_to_pos(self, ra, dec, observing_time=None):
        if observing_time == None:
            observing_time = Time(datetime.datetime.now())
        
        # aa = AltAz(location=self.observing_location, obstime=observing_time)
        # coordAltAz = coord.transform_to(aa)
        coord = SkyCoord(ra, dec)

        lst = observing_time.sidereal_time('mean', longitude=self.observing_location)
        ha = (lst - coord.ra).wrap_at(12*u.hourangle)
        
        posDEC = int(((coord.dec.value - self.dec_offset)*self.conversion_factor_DEC)*self.revolutions_to_increments)
        posHA = int(((ha.value - self.ha_offset)*self.conversion_factor_HA)*self.revolutions_to_increments)
        
        return posDEC, posHA
        
    def move_to(self, ra: str , dec: str, pos=None):
        print(f"{self.drive_DEC.node_id} and {self.drive_HA.node_id} are moving!")
        posDEC, posHA = self.coord_to_pos(ra, dec)
        self.drive_DEC.set_position_sdo(posDEC)
        self.drive_HA.set_position_sdo(posHA)
        while self.drive_DEC.state != DriveState.TARGET_REACHED or self.drive_HA.state !=  DriveState.TARGET_REACHED:
            print(self.dish_id, self.drive_DEC.state, self.drive_HA.state)
            # pass
        self.state = ComponentState.IDLE
        
    def set_position(self, drive, pos):
        drive.set_position_sdo(pos)
        while drive.state != DriveState.TARGET_REACHED:
            pass
        self.state = ComponentState.IDLE
        
        
    def wait(self,wait_time):
        print(bcolors.OKBLUE, f"waiting for {wait_time} seconds", bcolors.ENDC)
        time.sleep(wait_time)
        pass
    
    def track(self):
        self.drive_HA.set_velocity(self.earth_speed)
    
    def add_task(self, action, *args, callback: Optional[Callable[[bool, Optional[int]], None]] = None) -> bool:
        """Queue a dish Task """
        print(f"task queued for {self.drive_DEC.node_id} and {self.drive_HA.node_id}")
        task = Task(action, args, callback)

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
                    if self.state == ComponentState.IDLE and self.request_queue:
                        self.current_request = self.request_queue.pop(0)
                        print(f"Processing SDO request for dish {self.dish_id}")
                        self._send_current_request()

                time.sleep(0.01)  # Small delay to prevent busy waiting

            except Exception as e:
                print(f"Dish error: {e}")
                self.state = ComponentState.IDLE
            #     import traceback
            #     traceback.print_exc()
            #     # Reset state on error
            #     with self.lock:
            #         if self.current_request:
            #             self._complete_request(False, None)
            #         self.state = ComponentState.IDLE

    def _send_current_request(self):
        """Send the current SDO request"""
        if not self.current_request:
            return
        self.state = ComponentState.BUSY
        self.current_request.action(*self.current_request.args)
        if self.current_request.callback() != None:
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
            return self.state != ComponentState.IDLE or len(self.request_queue) > 0
    

