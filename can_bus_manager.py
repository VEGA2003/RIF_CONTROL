import can
import time
import threading
from typing import List, Protocol
import struct

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

class CANMessageHandler(Protocol):
    """Protocol for CAN message handlers"""
    def can_handle_message(self, message: can.Message) -> bool:
        """Check if this handler can process the message"""
        ...
    
    def handle_message(self, message: can.Message) -> None:
        """Process the CAN message"""
        ...


class CANBusManager:
    """Top-level CAN bus manager that distributes messages to handlers"""
    
    def __init__(self, interface: str = 'pcan', channel: str = "PCAN_USBBUS1", bitrate: int = 1000000):
        self.bus = can.interface.Bus(interface=interface, channel=channel, bitrate=bitrate)
        self.handlers: List[CANMessageHandler] = []
        self.running = False
        self.receive_thread = None
        self.lock = threading.Lock()
        
    def add_handler(self, handler: CANMessageHandler):
        """Add a message handler"""
        with self.lock:
            self.handlers.append(handler)
    
    def remove_handler(self, handler: CANMessageHandler):
        """Remove a message handler"""
        with self.lock:
            if handler in self.handlers:
                self.handlers.remove(handler)
    
    def start(self):
        """Start the CAN bus receiver"""
        print("Starting CAN bus manager...")
        self.running = True
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()
        print(bcolors.OKGREEN + "CAN bus manager started" + bcolors.ENDC)
    
    def stop(self):
        """Stop the CAN bus receiver"""
        print("Stopping CAN bus manager...")
        self.running = False
        if self.receive_thread:
            self.receive_thread.join(timeout=1.0)
        self.bus.shutdown()
        print("CAN bus manager stopped")
    
    def send_message(self, message: can.Message):
        """Send a CAN message"""
        try:
            self.bus.send(message)
        except Exception as e:
            print(f"Failed to send CAN message: {e}")
        
    def _receive_loop(self):
        """Main receive loop"""
        while self.running:
            try:
                message = self.bus.recv(timeout=0.1)
                if message:
                    self._distribute_message(message)
                    # print(bcolors.OKGREEN, message,len(message.data),  bcolors.ENDC)
                    
            except Exception as e:
                if self.running:
                    print(f"CAN receive error: {e}")
    
    def _distribute_message(self, message: can.Message):
        """Distribute message to appropriate handlers"""
        with self.lock:
            handlers_copy = self.handlers.copy()
        
        for handler in handlers_copy:
            try:
                if handler.can_handle_message(message):
                    handler.handle_message(message)
            except Exception as e:
                print(f"Handler error: {e}")


class SyncManager:
    """Manages SYNC messages"""

    def __init__(self, can_bus_manager, sync_rate: float = 100.0):
        self.can_bus_manager = can_bus_manager
        self.sync_rate = sync_rate
        self.running = False
        self.sync_thread = None

    def start(self):
        """Start sending SYNC messages"""
        self.running = True
        self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.sync_thread.start()

    def stop(self):
        """Stop sending SYNC messages"""
        self.running = False
        if self.sync_thread:
            self.sync_thread.join(timeout=1.0)

    def _sync_loop(self):
        """SYNC message loop"""
        dt = 1.0 / self.sync_rate
        next_time = time.time()

        while self.running:
            try:
                # Send SYNC message
                message = can.Message(arbitration_id=0x080, data=b'', is_extended_id=False)
                self.can_bus_manager.send_message(message)

                # Maintain sync rate
                next_time += dt
                sleep_time = next_time - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    next_time = time.time()

            except Exception as e:
                print(f"SYNC loop error: {e}")