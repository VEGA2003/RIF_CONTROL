from typing import Dict, Optional, Callable, List, Tuple, Any
from dataclasses import dataclass
import can
import struct
from can_bus_manager import CANBusManager, SyncManager
from sdo_state_machine import SDOStateMachine, SDORequest, SDOState
import threading
import time
from enum import Enum, auto


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class ControlWord:
    """DS402 Control Word bit definitions"""
    SWITCH_ON = 0x01
    ENABLE_VOLTAGE = 0x02
    QUICK_STOP = 0x04
    ENABLE_OPERATION = 0x08
    FAULT_RESET = 0x80
    NEW_SET_POINT = 0x10
    CHANGE_SET_IMMEDIATELY = 0x20

class ControlMode(Enum):
    """Control mode enumeration"""
    DISABLED = "disabled"
    HOMING = "homing"
    POSITIONING = "positioning"
    VELOCITY = "velocity"
    TRACKING = "tracking"
    SIMPLE_P = "simple_p"
    PID = "pid"

@dataclass
class InitStep:
    """Initialization step definition"""
    description: str
    action: str  # 'sdo' or 'nmt' or 'delay'
    index: Optional[int] = None
    subindex: Optional[int] = None
    value: Optional[int] = None
    size: Optional[int] = None
    nmt_command: Optional[int] = None
    delay: Optional[float] = None
    
    
class DriveState(Enum):
    """Drive state enumeration based on DS402 state machine"""
    NOT_READY_TO_SWITCH_ON = 0
    SWITCH_ON_DISABLED = 1
    READY_TO_SWITCH_ON = 2
    SWITCHED_ON = 3
    OPERATION_ENABLED = 4
    QUICK_STOP_ACTIVE = 5
    FAULT_REACTION_ACTIVE = 6
    FAULT = 7
    TARGET_REACHED = 8
    MOVING = 9

class StatusWord:
    """DS402 Status Word bit definitions"""
    READY_TO_SWITCH_ON = 0x01
    SWITCHED_ON = 0x02
    OPERATION_ENABLED = 0x04
    FAULT = 0x08
    VOLTAGE_ENABLED = 0x10
    QUICK_STOP = 0x20
    SWITCH_ON_DISABLED = 0x40
    
    
            
class ARS2108System():
    """Main system controller for ARS2108 servo drives with multiple control modes"""

    def __init__(self, node_id, can_bus_manager=None ,position_calc_func: Optional[Callable] = None):
        self.velocity = 0

        self.node_id = node_id
        self.init_steps = self.set_init_steps()
        # Initialize CAN bus and managers
        # self.state
        self.lock = threading.Lock()
        if can_bus_manager == None:
            self.can_bus_manager = CANBusManager()
            
        else: 
            self.can_bus_manager = can_bus_manager

        self.can_bus_manager.add_handler(self)
        self.sdo_manager = SDOStateMachine(self.can_bus_manager)
        # self.sync_manager = SyncManager(self.can_bus_manager)
        
        self.current_velocity = 0
        self.control_mode = ControlMode.DISABLED
        
        self.state = DriveState.SWITCHED_ON
    
    def start(self):
        self.can_bus_manager.start()
        self.sdo_manager.start()
        self.initialize()
        
    def stop(self):
        """Stop the complete system"""
        print("Stopping ARS2108 system...")

        # # Stop control loop
        # self.running = False
        # if self.control_thread:
        #     self.control_thread.join(timeout=1.0)

        # # Disable drives
        # for drive in self.drives.values():
        #     drive.disable()

        # time.sleep(0.5)  # Give drives time to stop

        # Stop managers
        self.sdo_manager.stop()
        self.can_bus_manager.stop()

        print("ARS2108 system stopped")
                 
    def set_init_steps(self) -> List[InitStep]:
        """Define the initialization sequence"""
        return [
            InitStep("NMT Reset Communication", "nmt", nmt_command=0x82),
            # InitStep("Delay after reset", "delay", delay=0.1),
            InitStep("NMT Reset Node", "nmt", nmt_command=0x80),
            # InitStep("Delay after reset", "delay", delay=0.1),

            InitStep("Disable RPDO1", "sdo", 0x1400, 0x01, 0x80000200 + self.node_id, 4),
            InitStep("Disable RPDO2", "sdo", 0x1401, 0x01, 0x80000300 + self.node_id, 4),
            InitStep("Disable TPDO1", "sdo", 0x1800, 0x01, 0x80000180 + self.node_id, 4),
            InitStep("Disable TPDO2", "sdo", 0x1801, 0x01, 0x80000280 + self.node_id, 4),

            InitStep("Clear RPDO1 mapping", "sdo", 0x1600, 0x00, 0, 1),
            InitStep("Map RPDO1 Control Word", "sdo", 0x1600, 0x01, 0x60400010, 4),
            InitStep("Map RPDO1 Target Velocity", "sdo", 0x1600, 0x02, 0x60FF0020, 4),
            InitStep("Enable RPDO1 mapping", "sdo", 0x1600, 0x00, 2, 1),
            
            InitStep("Clear RPDO2 mapping", "sdo", 0x1601, 0x00, 0, 1),
            InitStep("Map RPDO2 Control Word", "sdo", 0x1601, 0x01, 0x60400010, 4),
            InitStep("Map RPDO2 Target Position", "sdo", 0x1601, 0x02, 0x607A0020, 4),
            InitStep("Enable RPDO2 mapping", "sdo", 0x1601, 0x00, 2, 1),

            InitStep("Clear TPDO1 mapping", "sdo", 0x1A00, 0x00, 0, 1),
            InitStep("Map TPDO1 Status Word", "sdo", 0x1A00, 0x01, 0x60410010, 4),
            InitStep("Map TPDO1 Position Actual", "sdo", 0x1A00, 0x02, 0x60640020, 4),
            InitStep("Enable TPDO1 mapping", "sdo", 0x1A00, 0x00, 2, 1),

            InitStep("Clear TPDO2 mapping", "sdo", 0x1A01, 0x00, 0, 1),
            InitStep("Map TPDO2 Velocity Actual", "sdo", 0x1A01, 0x01, 0x606C0020, 4),
            InitStep("Map TPDO2 Torque Actual", "sdo", 0x1A01, 0x02, 0x60770010, 4),
            InitStep("Enable TPDO2 mapping", "sdo", 0x1A01, 0x00, 2, 1),

            InitStep("Set TPDO1 transmission type", "sdo", 0x1800, 0x02, 1, 1),
            InitStep("Set TPDO2 transmission type", "sdo", 0x1801, 0x02, 1, 1),

            InitStep("Enable TPDO1", "sdo", 0x1800, 0x01, 0x180 + self.node_id, 4),
            InitStep("Enable TPDO2", "sdo", 0x1801, 0x01, 0x280 + self.node_id, 4),
            InitStep("Enable RPDO1", "sdo", 0x1400, 0x01, 0x200 + self.node_id, 4),
            InitStep("Enable RPDO2", "sdo", 0x1401, 0x01, 0x300 + self.node_id, 4),

            InitStep("Start Remote Node", "nmt", nmt_command=0x01),
            InitStep("Final delay", "delay", delay=0.1),
        ]
        
    def initialize(self, callback: Optional[Callable[[bool], None]] = None):
        """Initialize the drive"""
        print(f"Initializing drive {self.node_id}...")
        self.initialization_step = 0
        self.init_callback = callback
        self.initialized = False
        self._execute_next_init_step()
        
        time.sleep(1.0)
        self.enable()

    def _execute_next_init_step(self):
        """Execute the next initialization step"""
        if self.initialization_step >= len(self.init_steps):
            # Initialization complete
            self.initialized = True
            print(f"Drive {self.node_id} initialized successfully")
            if self.init_callback:
                self.init_callback(True)
            return

        step = self.init_steps[self.initialization_step]
        print(f"Drive {self.node_id} step {self.initialization_step}: {step.description}")

        if step.action == "sdo":
            # SDO write operation
            def sdo_callback(success: bool, error_code: Optional[int]):
                if success:
                    print(f"Drive {self.node_id} step {self.initialization_step} completed successfully")
                    self.initialization_step += 1
                    self._execute_next_init_step()
                else:
                    print(
                        f"Drive {self.node_id} initialization failed at step {self.initialization_step}: {step.description}")
                    if error_code:
                        print(f"  Error code: 0x{error_code:08X}")
                    if self.init_callback:
                        self.init_callback(False)

            self.sdo_manager.write_sdo(
                self.node_id,
                step.index,
                step.subindex,
                step.value,
                step.size,
                callback=sdo_callback
            )

        elif step.action == "nmt":
            # NMT command
            self._send_nmt(step.nmt_command)
            self.initialization_step += 1
            # Continue immediately for NMT commands
            self._execute_next_init_step()

        elif step.action == "delay":
            # Delay
            def delayed_continue():
                time.sleep(step.delay)
                self.initialization_step += 1
                self._execute_next_init_step()
            # Execute delay in a separate thread to avoid blocking
            threading.Thread(target=delayed_continue, daemon=True).start()
            
        else:
            print(f"Unknown initialization action: {step.action}")
            if self.init_callback:
                self.init_callback(False)
                
    def enable(self, drive_id=None):
        if drive_id == None:
            drive_id = self.node_id
        """Enable the drive through DS402 state machine"""
        print(f"Enabling drive {drive_id}...")

        # State machine sequence
        control_words = [
            (ControlWord.ENABLE_VOLTAGE | ControlWord.QUICK_STOP | ControlWord.FAULT_RESET, "Fault reset"),
            (ControlWord.ENABLE_VOLTAGE | ControlWord.QUICK_STOP, "Switch on disabled -> Ready to switch on"),
            (ControlWord.ENABLE_VOLTAGE | ControlWord.QUICK_STOP | ControlWord.SWITCH_ON, "Ready -> Switched on"),
            (ControlWord.ENABLE_VOLTAGE | ControlWord.QUICK_STOP | ControlWord.SWITCH_ON | ControlWord.ENABLE_OPERATION,
             "Operation enabled")
        ]

        for control_word, description in control_words:
            self._send_control_word(control_word)
            time.sleep(0.1)
    
    def _send_control_word(self, control_word: int):
        """Send control word via RPDO"""
        current_vel = self.current_velocity
        data = struct.pack('<Hl', control_word, int(current_vel))
        message = can.Message(arbitration_id=0x200 + self.node_id, data=data, is_extended_id=False)
        self.can_bus_manager.send_message(message)
                
    def _send_nmt(self, command: int):
        """Send NMT command"""
        data = bytes([command, self.node_id])
        message = can.Message(arbitration_id=0x000, data=data, is_extended_id=False)
        self.can_bus_manager.send_message(message)

    def can_handle_message(self, message: can.Message) -> bool:
        """Check if this message belongs to this drive"""
        cob_id = message.arbitration_id
        # TPDO1 (0x180 + node_id) or TPDO2 (0x280 + node_id)
        # return (cob_id == 0x180 + self.node_id or
        #         cob_id == 0x280 + self.node_id)
        return cob_id in [0x180 + self.node_id, 0x280 + self.node_id, 0x380 + self.node_id]
        
    def handle_message(self, message: can.Message):
        """Handle CAN message for this drive"""
        cob_id = message.arbitration_id

        if cob_id == 0x180 + self.node_id:
            # TPDO1: Status + Position
            self._process_tpdo1(message.data)
        elif cob_id == 0x280 + self.node_id:
            # TPDO2: Velocity + Torque
            self._process_tpdo2(message.data)
        elif cob_id == 0x380 + self.node_id:
            # TPDO2: Velocity + Torque
            self._process_tpdo3(message.data)
            
    def _process_tpdo1(self, data: bytes):
        """Process TPDO1 data (Status + Position)"""
        if len(data) >= 6:
            status_word, position = struct.unpack('<Hl', data[:6])
            with self.lock:
                self.status_word = status_word
                self.position = position    
            
                
    def _process_tpdo2(self, data: bytes):
        """Process TPDO2 data (Velocity + Torque)"""
        if len(data) >= 6:
            velocity, torque = struct.unpack('<lH', data[:6])
            with self.lock:
                self.velocity = velocity
                self.torque = torque
        
    def _process_tpdo3(self, data: bytes):
        """Process TPDO2 data (Velocity + Torque)"""
        if len(data) >= 6:
            status_word, position = struct.unpack('<Hl', data[:6])
            with self.lock:
                self.status_word = status_word
                self.position = position    
                self.get_status()
            # print(bcolors.OKGREEN, format(status_word, 'b'), bcolors.ENDC)
    def get_status(self):
        if self.control_mode == ControlMode.POSITIONING:
            if self.status_word & 0x1000 :
                print(bcolors.OKGREEN, "setpoint acknowledged", bcolors.ENDC)
            if self.status_word & 0x0400 :
                if self.state == DriveState.MOVING:
                    print(bcolors.OKGREEN, "target reached", bcolors.ENDC)
                    self.state = DriveState.TARGET_REACHED

    def set_control_mode(self, mode: ControlMode):
        """Set control mode with proper state transitions"""
        if isinstance(mode, str):
            mode_map = {
                "disabled": ControlMode.DISABLED,
                "velocity": ControlMode.DISABLED,
                "homing": ControlMode.HOMING,
                "positioning": ControlMode.POSITIONING,
                "tracking": ControlMode.TRACKING
            }
            mode = mode_map.get(mode, ControlMode.DISABLED)

        self.previous_mode = self.control_mode

        print(f"Control mode changing from {self.previous_mode.value} to {mode.value}")

        # Handle special case: stopping homing operation
        # if (self.previous_mode == ControlMode.HOMING and
        #         mode != ControlMode.HOMING and
        #         any(hc.is_homing() for hc in self.homing_controllers.values())):
        #     print("Interrupting active homing operations...")
        #     self._stop_homing_operations()
        
        self.control_mode = mode

        if mode == ControlMode.HOMING:
            self.sdo_manager.write_sdo(self.node_id, 0x6040, 0x00, 0x00, 2),  # Disable all
            self.sdo_manager.write_sdo(self.node_id, 0x6060, 0x00, 1, 1),  # Mode 1 = position mode
            self.sdo_manager.write_sdo(self.node_id, 0x6040, 0x00, 0x06, 2),  # Enable voltage only
            self.sdo_manager.write_sdo(self.node_id, 0x6040, 0x00, 0x00, 2),  # Disable for mode change

            # Configure homing parameters
            # self.sdo_manager.write_sdo(self.node_id, 0x6098, 0x00, self.config.homing_method, 1),
            # self.sdo_manager.write_sdo(self.node_id, 0x6099, 0x01, self.config.switch_search_velocity, 4),
            # self.sdo_manager.write_sdo(self.node_id, 0x6099, 0x02, self.config.zero_search_velocity, 4),
            # self.sdo_manager.write_sdo(self.node_id, 0x609A, 0x00, self.config.homing_acceleration, 4),
            # self.sdo_manager.write_sdo(self.node_id, 0x607C, 0x00, self.config.home_offset, 4),
            
            self.sdo_manager.write_sdo(self.node_id, 0x6060, 0x00, 6, 1) # Mode 6 = homing
            # self.sdo_manager.write_sdo(self.node_id, 0x6040, 0x00, 0x1F, 2)
            self.sdo_manager.write_sdo(self.node_id, 0x6040, 0x00, 0x06, 2)  # Enable voltage
            self.sdo_manager.write_sdo(self.node_id,0x6040, 0x00, 0x07, 2)  # Switch on
                

            self.sdo_manager.write_sdo(self.node_id,0x6040, 0x00, 0x0F, 2)  # Enable operation
            time.sleep(1)
            self.sdo_manager.write_sdo(self.node_id, 0x6040, 0x00, 0x1F, 2)

        # Mode-specific initialization
        if mode == ControlMode.DISABLED:
            # Stop all drives immediately
            print("Disabling all drives...")

            self.set_velocity(0)

            # Also send disable command via SDO
            def disable_callback(success: bool, error_code: Optional[int]):
                if not success:
                    print(f"Warning: Failed to disable drive {self.node_id} via SDO")

            self.sdo_manager.write_sdo(self.node_id, 0x6040, 0x00, 0x00, 2, callback=disable_callback)
            
                
        if mode == ControlMode.VELOCITY:
            self.sdo_manager.write_sdo(self.node_id, 0x6060, 0x00, 3, 1)  # Velocity mode
        
        if mode == ControlMode.POSITIONING:
            self.sdo_manager.write_sdo(self.node_id, 0x6060, 0x00, 1, 1)  # Positioning mode
            self.sdo_manager.write_sdo(self.node_id,0x6081, 0x00, 10000000, 4)
            # self.sdo_manager.write_sdo(self.node_id, 0x6083, 0x00, 120000, 1)
            # self.sdo_manager.write_sdo(self.node_id, 0x6083, 0x00, 120000, 1)

        
        print(bcolors.OKCYAN + f"Control mode set to {self.control_mode}" + bcolors.ENDC)
    
    def set_velocity(self, velocity):
        self.velocity = velocity
        if self.control_mode != ControlMode.VELOCITY: 
            self.set_control_mode(ControlMode.VELOCITY)
        control_word = (ControlWord.ENABLE_VOLTAGE | ControlWord.QUICK_STOP |
                ControlWord.SWITCH_ON | ControlWord.ENABLE_OPERATION)
        data = struct.pack('<Hi', control_word, self.velocity)
        message = can.Message(arbitration_id=0x200 + 1, data=data, is_extended_id=False)
        self.can_bus_manager.send_message(message)
        print(bcolors.OKBLUE + f"velocity set to {self.velocity}" + bcolors.ENDC)
        
    def set_position(self, position):
        if self.control_mode != ControlMode.POSITIONING: 
            self.set_control_mode(ControlMode.POSITIONING)

        self.state = DriveState.MOVING
        control_word = (ControlWord.ENABLE_VOLTAGE | ControlWord.QUICK_STOP |ControlWord.SWITCH_ON | ControlWord.ENABLE_OPERATION | ControlWord.NEW_SET_POINT)
        data = struct.pack('<Hl', control_word, position)
        message = can.Message(arbitration_id=0x300 + 1, data=data, is_extended_id=False)
        
        control_word = (ControlWord.ENABLE_VOLTAGE | ControlWord.QUICK_STOP |ControlWord.SWITCH_ON | ControlWord.ENABLE_OPERATION | ControlWord.NEW_SET_POINT)
        data = struct.pack('<Hl', control_word, position)
        message = can.Message(arbitration_id=0x300 + 1, data=data, is_extended_id=False)
        
        control_word = (ControlWord.ENABLE_VOLTAGE | ControlWord.QUICK_STOP |ControlWord.SWITCH_ON | ControlWord.ENABLE_OPERATION )
        data = struct.pack('<Hl', control_word, position)
        message = can.Message(arbitration_id=0x300 + 1, data=data, is_extended_id=False)
        
        self.can_bus_manager.send_message(message)
        
        print(bcolors.OKBLUE + f"position set to {position}" + bcolors.ENDC)
        
    def set_position_sdo(self, position, now = False, wait=None):
        if self.control_mode != ControlMode.POSITIONING: 
            self.set_control_mode(ControlMode.POSITIONING)
        
        if now:
            controlword = ControlWord.CHANGE_SET_IMMEDIATELY | ControlWord.NEW_SET_POINT
        else:
            controlword = ControlWord.NEW_SET_POINT
        
        self.sdo_manager.write_sdo(self.node_id, 0x607A, 0x00, position, 4) 
        # Trigger with controlword via SDO
        self.sdo_manager.write_sdo(self.node_id, 0x6040, 0x00, 0x0F | controlword, 2)
        time.sleep(0.05)
        self.sdo_manager.write_sdo(self.node_id, 0x6040, 0x00, 0x0F, 2, callback=self.moving)
        print(bcolors.OKBLUE + f"position set to {position}" + bcolors.ENDC)
        
    def set_max_acceleration(self, max_accel):
        self.sdo_manager.write_sdo(self.node_id, 0x6083, 0x00, max_accel, 4) 
        
    def moving(self, succes, error):
        if succes:
            self.state = DriveState.MOVING 
        
    def start_homing(self):
        self.set_control_mode(ControlMode.HOMING)
        
    def reset_drive(self):
        self.sdo_manager.write_sdo(self.node_id, 0x6040, 0x00, 0x0F | ControlWord.FAULT_RESET, 2)


