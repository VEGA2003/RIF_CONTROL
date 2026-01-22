import can
import time
import struct
import threading
from enum import Enum, auto
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass

class SDOState(Enum):
    IDLE = auto()
    WAITING_RESPONSE = auto()
    # WAITING = auto()
    COMPLETED = auto()
    ERROR = auto()


@dataclass
class SDORequest:
    node_id: int
    index: int
    subindex: int
    value: int
    size: int
    timeout: float = 0.1
    callback: Optional[Callable[[bool, Optional[int]], None]] = None
    retry_count: int = 0
    max_retries: int = 3


class SDOStateMachine:
    """State machine for handling SDO write operations"""

    def __init__(self, can_bus_manager):
        self.can_bus_manager = can_bus_manager
        self.state = SDOState.IDLE
        self.current_request: Optional[SDORequest] = None
        self.request_queue = []
        self.lock = threading.Lock()
        self.request_start_time = 0

        # Register as CAN message handler
        self.can_bus_manager.add_handler(self)

        # Start processing thread
        self.running = False
        self.process_thread = None

    def start(self):
        """Start the SDO state machine"""
        print("Starting SDO state machine...")
        self.running = True
        self.process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.process_thread.start()
        print("SDO state machine started")

    def stop(self):
        """Stop the SDO state machine"""
        print("Stopping SDO state machine...")
        self.running = False
        if self.process_thread:
            self.process_thread.join(timeout=1.0)
        print("SDO state machine stopped")

    def can_handle_message(self, message: can.Message) -> bool:
        """Check if this is an SDO response message"""
        return 0x580 <= message.arbitration_id <= 0x5FF

    def handle_message(self, message: can.Message):
        """Handle SDO response message"""
        node_id = message.arbitration_id - 0x580
        print(f"SDO received from node {node_id}: ID=0x{message.arbitration_id:03X}, data={message.data.hex()}")

        with self.lock:
            if (self.state == SDOState.WAITING_RESPONSE and
                    self.current_request and
                    node_id == self.current_request.node_id):

                print(f"Processing SDO response for node {node_id} (current state: {self.state})")

                if len(message.data) >= 1:
                    command = message.data[0]
                    if command == 0x60:
                        # Success response
                        print(
                            f"SDO success for node {node_id}, index 0x{self.current_request.index:04X}:{self.current_request.subindex:02X}")
                        self._complete_request(True, None)
                    elif command == 0x80:
                        # Error response
                        error_code = None
                        if len(message.data) >= 8:
                            error_code = struct.unpack('<L', message.data[4:8])[0]
                        print(
                            f"SDO error for node {node_id}, index 0x{self.current_request.index:04X}:{self.current_request.subindex:02X}, error: 0x{error_code:08X}")
                        self._complete_request(False, error_code)
                    else:
                        print(f"Unknown SDO response command: 0x{command:02X}")
                        # Don't complete the request, let it timeout and retry
                else:
                    print("SDO response too short")
            else:
                expected_node = self.current_request.node_id if self.current_request else 'None'
                print(
                    f"SDO message not for current request (state={self.state.name}, current_node={expected_node}, received_node={node_id})")

    def write_sdo(self, node_id: int, index: int, subindex: int, value: int, size: int,
                  timeout: float = 0.1, callback: Optional[Callable[[bool, Optional[int]], None]] = None) -> bool:
        """Queue an SDO write request"""
        request = SDORequest(node_id, index, subindex, value, size, timeout, callback)

        with self.lock:
            self.request_queue.append(request)
            queue_length = len(self.request_queue)

        print(
            f"SDO request queued for node {node_id}, index 0x{index:04X}:{subindex:02X} (queue length: {queue_length})")
        return True

    def _process_loop(self):
        """Main processing loop"""
        while self.running:
            try:
                with self.lock:
                    current_time = time.time()

                    # Check for timeout
                    if (self.state == SDOState.WAITING_RESPONSE and
                            self.current_request and
                            current_time - self.request_start_time > self.current_request.timeout):

                        # Timeout occurred
                        elapsed = current_time - self.request_start_time
                        print(
                            f"SDO timeout for node {self.current_request.node_id}, index 0x{self.current_request.index:04X}:{self.current_request.subindex:02X} after {elapsed:.2f}s")

                        if self.current_request.retry_count < self.current_request.max_retries:
                            # Retry
                            self.current_request.retry_count += 1
                            print(
                                f"Retrying SDO request ({self.current_request.retry_count}/{self.current_request.max_retries})")
                            self._send_current_request()
                        else:
                            # Max retries exceeded
                            print(f"SDO max retries exceeded for node {self.current_request.node_id}")
                            self._complete_request(False, None)

                    # Process next request if idle
                    if self.state == SDOState.IDLE and self.request_queue:
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
                    self.state = SDOState.IDLE

    def _send_current_request(self):
        """Send the current SDO request"""
        if not self.current_request:
            return

        req = self.current_request

        # Build SDO write command
        if req.size == 1:
            cmd = 0x2F  # Expedited transfer, 1 byte
            data = struct.pack('<BBBBB', cmd, req.index & 0xFF, (req.index >> 8) & 0xFF, req.subindex, req.value & 0xFF)
            data += b'\x00\x00\x00'  # Pad to 8 bytes
        elif req.size == 2:
            cmd = 0x2B  # Expedited transfer, 2 bytes
            data = struct.pack('<BBBBH', cmd, req.index & 0xFF, (req.index >> 8) & 0xFF, req.subindex,
                               req.value & 0xFFFF)
            data += b'\x00\x00'  # Pad to 8 bytes
        elif req.size == 4:
            cmd = 0x23  # Expedited transfer, 4 bytes
            data = struct.pack('<BBBBL', cmd, req.index & 0xFF, (req.index >> 8) & 0xFF, req.subindex, req.value)
        else:
            print(f"Unsupported SDO data size: {req.size}")
            self._complete_request(False, None)
            return

        message = can.Message(arbitration_id=0x600 + req.node_id, data=data, is_extended_id=False)

        print(f"SDO sending: ID=0x{message.arbitration_id:03X}, data={message.data.hex()}")
        print(
            f"  Node: {req.node_id}, Index: 0x{req.index:04X}:{req.subindex:02X}, Value: 0x{req.value:X} ({req.value}), Size: {req.size}")

        try:
            self.can_bus_manager.send_message(message)
            self.state = SDOState.WAITING_RESPONSE
            self.request_start_time = time.time()
            print(f"SDO state changed to WAITING_RESPONSE for node {req.node_id}")
        except Exception as e:
            print(f"Failed to send SDO message: {e}")
            self._complete_request(False, None)

    def _complete_request(self, success: bool, error_code: Optional[int]):
        """Complete the current request"""
        if not self.current_request:
            print("Warning: _complete_request called with no current request")
            return

        node_id = self.current_request.node_id
        index = self.current_request.index
        subindex = self.current_request.subindex
        callback = self.current_request.callback

        print(f"SDO completing request for node {node_id}, 0x{index:04X}:{subindex:02X}, success={success}")

        # Clear current request and reset state BEFORE calling callback
        self.current_request = None
        self.state = SDOState.IDLE
        print(f"SDO state changed to IDLE")

        # Call callback after state is reset
        if callback:
            try:
                # Call callback outside of lock to avoid deadlocks
                def call_callback():
                    try:
                        callback(success, error_code)
                    except Exception as e:
                        print(f"SDO callback error: {e}")
                        import traceback
                        traceback.print_exc()

                # Call callback in a separate thread to avoid potential blocking
                threading.Thread(target=call_callback, daemon=True).start()
            except Exception as e:
                print(f"Error starting callback thread: {e}")

        if not success:
            if error_code:
                print(f"SDO error for node {node_id}: 0x{error_code:08X}")
            else:
                print(f"SDO failed for node {node_id} (timeout/retry exceeded)")

    def get_queue_length(self) -> int:
        """Get the number of pending requests"""
        with self.lock:
            return len(self.request_queue)

    def is_busy(self) -> bool:
        """Check if the state machine is busy"""
        with self.lock:
            return self.state != SDOState.IDLE or len(self.request_queue) > 0
        
    