from astropy.coordinates import EarthLocation,SkyCoord
from astropy.time import Time
from astropy import units as u
from astropy.coordinates import AltAz, HADec, Angle
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
from virtual_telescope import VirtualTelescope, VirtualSDR

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
    def __init__(self,telescope_type="real", bitrate: int = 500000, can_bus_manager= None):    
        # default observing location is the Huygens building :)
        self.observing_location = EarthLocation(lat='51.816694', lon='5.866694', height=20*u.m)
        self.revolutions_to_increments = 65536
        if telescope_type == "virtual":
            self.virtual = True
        else:
            self.virtual = False
        self.lock = threading.Lock()
        
        if can_bus_manager == None:
            if self.virtual:
                self.can_bus_manager = CANBusManager(channel="test", interface="virtual")
            else:
                self.can_bus_manager = CANBusManager(bitrate = bitrate, channel= "PCAN_USBBUS1")
        else:
            self.can_bus_manager = can_bus_manager
        
        if self.virtual:
            self.virtual_telescope = VirtualTelescope(4)
            self.receiver = Receiver(virtual=True)
        else:
            try:
                self.receiver = Receiver()
            except Exception as e: 
                print(e)
                self.receiver = None
                "no receiver connected"
                
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
        
        
    def start(self, skip_init=False):
        self.running = True
        
        if self.virtual:
            self.virtual_telescope.start()
            
        for dish in self.dishes:
            dish.start(skip_init)

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
    
    def move_to(self, coord:SkyCoord, follow = True, pos=None):
        self.dishes_in_position = 0
        for dish in self.dishes:
            dish.add_task(dish.move_to, coord, callback=self.move_to_followup)
        
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
    def __init__(self, virtual=False): 
        self.virtual = virtual  
        if virtual:
            self.sdr = VirtualSDR()
        else:
            self.sdr = adi.ad9361('ip:192.168.2.1')
            self.sdr.rx_enabled_channels = [0]
            self.sdr.gain_control_mode_chan0 = 'manual'
            # self.sdr.gain_control_mode_chan1 = 'manual'
            
        self.sdr.rx_hardwaregain_chan0 = 10.0 # dB
        # self.sdr.rx_hardwaregain_chan1 = 10.0 # dB
        self.sdr.rx_lo = int(1420e6) # Hz
        sample_rate = 4e6
        self.sdr.sample_rate = int(sample_rate) # Hz
        self.sdr.rx_rf_bandwidth = int(sample_rate*0.8) # filter width, just set it to the same as sample rate for now
        self.sdr.rx_buffer_size = 4096
        
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
        # self.observing_location = EarthLocation(lat='51.816694', lon='5.866694', height=20*u.m) 
        # self.observing_location = EarthLocation(lat='51.82465', lon='5.86923333', height=20*u.m) #east  
        self.observing_location = EarthLocation(lat='51.82466667', lon='5.86875', height=27*u.m) #west
        self.revolutions_to_increments = 65536
        # self.dec_offset = -76.56 + 0.2
        # self.ha_offset = 827 + 5.91 
        self.dec_offset = -76.56 - 0.9
        self.ha_offset = 827 - 1.75

        self.conversion_factor_HA = -2430/24
        self.conversion_factor_DEC = -870/360
        self.earth_speed = int(self.conversion_factor_HA/3600 * self.revolutions_to_increments)  #increments a second
        
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

        
    def start(self, skip_init=False):
        for drive in self.drives:
            drive.start(skip_init)
            
        self.running = True
        self.process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.process_thread.start()
        
    def coord_to_pos(self, coord,observing_time=None, transform=True):
        if observing_time == None:
            observing_time = Time(datetime.datetime.now())
        
        if transform:
            hadec = HADec(location=self.observing_location, obstime=observing_time)
            coordHADec = coord.transform_to(hadec)
        else:
            coordHADec = coord
        # coord = SkyCoord(ra, dec)

        # lst = observing_time.sidereal_time('mean', longitude=self.observing_location)
        # ha = (lst - coord.ra).wrap_at(12*u.hourangle)
        posDEC = int((coordHADec.dec.value*self.conversion_factor_DEC + self.dec_offset)*self.revolutions_to_increments)
        posHA = int((coordHADec.ha.value*self.conversion_factor_HA + self.ha_offset)*self.revolutions_to_increments)
        
        return posDEC, posHA
    
    def pos_to_coord(self, posDEC,posHA, observing_time=None):
        coordDEC = ((posDEC/self.revolutions_to_increments) - self.dec_offset)/self.conversion_factor_DEC
        coordHA = ((posHA/self.revolutions_to_increments) - self.ha_offset)/self.conversion_factor_HA
        # print(self.drive_DEC.target_position/self.revolutions_to_increments,posDEC/self.revolutions_to_increments, coordDEC)
        hadec = HADec(ha=Angle(coordHA * u.hourangle), dec= Angle(coordDEC * u.degree) ,location=self.observing_location, obstime=observing_time)
        return hadec
        
    def move_to(self, coord: SkyCoord, observing_time=None, follow = False):
        print(f"{self.drive_DEC.node_id} and {self.drive_HA.node_id} are moving!")
        posDEC, posHA = self.coord_to_pos(coord, observing_time, transform=True)
        if follow:
            self.drive_HA.sdo_manager.write_sdo(self.drive_HA.node_id,0x6082, 0x00, self.earth_speed, 4)
        else:
            self.drive_HA.sdo_manager.write_sdo(self.drive_HA.node_id,0x6082, 0x00, 0, 4)
        self.drive_DEC.set_position_sdo(posDEC)
        self.drive_HA.set_position_sdo(posHA)
        while self.drive_DEC.state != DriveState.TARGET_REACHED or self.drive_HA.state !=  DriveState.TARGET_REACHED:
            # print(self.dish_id, self.drive_DEC.state, self.drive_HA.state)
            pass
        self.state = ComponentState.IDLE
        
    def set_position(self, drive, pos):
        drive.set_position_sdo(pos)
        while drive.state != DriveState.TARGET_REACHED:
            pass
        self.state = ComponentState.IDLE
        
    def set_velocity(self, drive, vel):
        drive.set_velocity_sdo(vel)
        while drive.state != DriveState.TARGET_REACHED:
            pass
        self.state = ComponentState.IDLE
        
        
    def wait(self,wait_time):
        print(bcolors.OKBLUE, f"waiting for {wait_time} seconds", bcolors.ENDC)
        time.sleep(wait_time)
        pass
    
    # def track(self, ra: str , dec: str, tracking_time: int):
    #     self.move_to(ra , dec)
    #     self.drive_HA.set_velocity(self.earth_speed)
    #     self.wait(tracking_time)

    def track(self, coord: SkyCoord, tracking_time: int, tracking_func= None):
        elapsed_time = 0
        dt = 10
        while elapsed_time < tracking_time:
            start_time = time.time()
            if tracking_func == None:
                self.drive_HA.sdo_manager.write_sdo(self.drive_HA.node_id,0x6082, 0x00, self.earth_speed, 4)
                self.move_to(coord)
            else:
                observing_time = Time(datetime.datetime.now())
                new_coord = tracking_func(observing_time)
                self.drive_HA.sdo_manager.write_sdo(self.drive_HA.node_id,0x6082, 0x00, self.earth_speed, 4)
                self.move_to(new_coord)
            self.drive_HA.set_velocity(self.earth_speed)
            self.wait(dt)
            end_time = time.time()
            elapsed_time += end_time - start_time
        self.drive_HA.sdo_manager.write_sdo(self.drive_HA.node_id,0x6082, 0x00, 0, 4)
        self.drive_HA.set_velocity(0)
        print(bcolors.OKBLUE, f"Tracking completed", bcolors.ENDC)
    
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
    

