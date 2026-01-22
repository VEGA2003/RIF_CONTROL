from astropy.coordinates import EarthLocation,SkyCoord
from astropy.time import Time
from astropy import units as u
from astropy.coordinates import AltAz
from datetime import datetime
from system_config import ARS2108System, DriveState, bcolors
from enum import Enum, auto
import threading
import time
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from can_bus_manager import CANBusManager

class TelescopeState(Enum):
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
    
    def __init__(self, telescope_id):    
        # default observing location is the Huygens building :)
        self.telescope_id = telescope_id
        self.observing_location = EarthLocation(lat='51.816694', lon='5.866694', height=20*u.m)  
        self.conversion_factor_alt = 0.001
        self.alt_offset = 0
        self.az_offset = 0
        self.conversion_factor_az = 0.001
        self.revolutions_to_increments = 6553600
        
        self.lock = threading.Lock()
        self.can_bus_manager = CANBusManager()
        self.request_queue = []
        self.drive_az = ARS2108System(self.telescope_id*2 + 1, self.can_bus_manager)
        self.drive_alt = ARS2108System(self.telescope_id*2 + 2, self.can_bus_manager)
        # self.drives = [self.drive_az, self.drive_alt]
        self.drives = [self.drive_az]
        self.state = TelescopeState.IDLE

        
    def start(self):
        for drive in self.drives:
            drive.start()

        self.process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.process_thread.start()
        
    def coord_to_pos(self, ra, dec, observing_time=None):
        if observing_time == None:
            observing_time = Time(datetime.now())
        
        aa = AltAz(location=self.observing_location, obstime=observing_time)
        coord = SkyCoord(ra, dec)
        coordAltAz = coord.transform_to(aa)
        
        posalt = int(((coordAltAz.alt.value - self.alt_offset)*self.conversion_factor_alt)*self.revolutions_to_increments)
        posaz = int(((coordAltAz.az.value - self.az_offset)*self.conversion_factor_az)*self.revolutions_to_increments)
        
        return posalt, posaz
        
    def move_to(self, ra: str , dec: str, pos=None):
        posalt, posaz = self.coord_to_pos(ra, dec)
        self.drive_alt.set_position_sdo(posalt)
        self.drive_az.set_position_sdo(posaz)
        while self.drive_alt.state != DriveState.TARGET_REACHED or self.drive_az.state !=  DriveState.TARGET_REACHED:
            print(self.drive_alt.state, self.drive_az.state)
        self.state = TelescopeState.IDLE
        
    def set_position(self, drive, pos):
        drive.set_position_sdo(pos)
        while drive.state != DriveState.TARGET_REACHED:
            pass
        self.state = TelescopeState.IDLE
        
        
    def wait(self,wait_time):
        print(bcolors.OKBLUE, f"waiting for {wait_time} seconds", bcolors.ENDC)
        time.sleep(wait_time)
        pass
    
    def add_task(self, action, callback: Optional[Callable[[bool, Optional[int]], None]] = None) -> bool:
        """Queue a Telescope Task """
        task = Task(action, callback)

        with self.lock:
            self.request_queue.append(task)
            queue_length = len(self.request_queue)

        print(
            f"Telescope task queued for telelscope {self.telescope_id}, (queue length: {queue_length})")
        return True

    
    def _process_loop(self):
        """Main processing loop"""
        while self.running:
            try:
                with self.lock:
                    current_time = time.time()
                    
                    # Process next request if idle
                    if self.state == TelescopeState.IDLE and self.request_queue:
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
                    self.state = TelescopeState.IDLE

    def _send_current_request(self):
        """Send the current SDO request"""
        if not self.current_request:
            return
        self.state = TelescopeState.BUSY
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
            return self.state != TelescopeState.IDLE or len(self.request_queue) > 0
    

