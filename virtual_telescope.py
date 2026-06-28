from can_bus_manager import CANBusManager
import can
import time
from system_config import ControlMode, ControlWord, bcolors, DriveState, StatusWord
from dataclasses import dataclass
import math
import threading
import numpy as np
import math
import struct

revolutions_to_increments = 65536

class VirtualTelescope():
    def __init__(self, num_devices): 
        self.can_bus_manager = CANBusManager(channel="test", interface="virtual")
        self.devices = []
        self.num_devices = num_devices
        # Create 4 simulated drives
        for node_id in range(self.num_devices):
            dev = ARS2108Sim(node_id + 1, self.can_bus_manager)
            self.devices.append(dev)

        
    def start(self):
        for device in self.devices:
            device.start()
        self.can_bus_manager.start()
        print("Virtual telescope running...")


class ARS2108Sim:
    def __init__(self, node_id, can_bus_manager):
        self.control_word = 0
        self.status_word = 0x0040  # Switch on disabled
        self.target_position = 0
        self.position = 0
        self.velocity = 0
        self.control_mode = ControlMode.POSITIONING  # Profile Position
        self.node_id = node_id
        self.can_bus_manager = can_bus_manager
        self.can_bus_manager.add_handler(self)
        self.time = 0
        self.state = DriveState.SWITCHED_ON
        # Control parameters - Keep high rate but make controller gentler
        self.control_rate = 1  # Keep 100 Hz for good tracking

        # PID controllers for each drive - VERY small gains with rate limiting
        self.pid_controller = PIDController(kp=0.1, ki=0.0, kd=0.0, kv=1.0)
        # # Set velocity limits and dead zones for your system
        # self.pid_controller.set_limits(100)  # Moderate max velocity - 100 RPM
        # self.pid_controller.set_dead_zone(200)  # 200 count dead zone
        # self.pid_controller.set_rate_limit(5)  # Critical: Only 5 RPM change per 10ms cycle!

        # Trajectory generators
        self.trajectory_generators = {
            1: TrajectoryGenerator(),
            2: TrajectoryGenerator()
        }

    def start(self):
        # Start control loop
        print(bcolors.OKGREEN,f"drive {self.node_id} has started", bcolors.ENDC)
        self.running = True
        self.control_thread = threading.Thread(target=self._control_loop, daemon=True)
        self.control_thread.start()
        
    def write_object(self, index, subindex, value):
        if index == 0x6040:
            self.control_word = value
            self._update_state_machine()

        elif index == 0x607A:
            self.target_position = value
            self.state = DriveState.MOVING
            self.status_word = 0x0027
            print(f"{self.node_id} has been moved!")
        elif index == 0x6060:
            self.control_mode = ControlMode[value]

    def read_object(self, index, subindex):
        if index == 0x6041:
            return self.status_word

        elif index == 0x6064:
            return self.position

        elif index == 0x6061:
            return self.control_mode

        return 0

    def _update_state_machine(self):
        cw = self.control_word

        if cw & 0x000F == 0x0006:
            self.status_word = 0x0021  # Ready to switch on
        elif cw & 0x000F == 0x0007:
            self.status_word = 0x0023  # Switched on
        elif cw & 0x000F == 0x000F:
            self.status_word = 0x0027  # Operation enabled

            # simulate motion
            # self.actual_position = self.target_position
    
        
    def can_handle_message(self, message: can.Message) -> bool:
        """Check if this message belongs to this drive"""
        cob_id = message.arbitration_id
        
        
        return cob_id % 16 == self.node_id
        
    def handle_message(self, message: can.Message):
        """Handle CAN message for this drive"""
        cob_id = message.arbitration_id
        print(bcolors.OKBLUE, self, self.node_id, message,bcolors.ENDC)
        # # NMT
        # if cob_id == 0x000:
        #     self.handle_nmt(message.data)

        # SDO request
        if 0x600 <= cob_id <= 0x67F:
            self.handle_sdo(message)
            
    def handle_sdo(self, message):
        data = message.data
        cmd = data[0]
        index = data[1] | (data[2] << 8)
        sub = data[3]

        # WRITE request
        if cmd in (0x23, 0x2B, 0x2F):
            value = int.from_bytes(data[4:8], "little", signed=True)
            self.write_object(index, sub, value)

            # send SDO response
            response_data = [0x60, data[1], data[2], sub, 0, 0, 0, 0]
            response = can.Message(arbitration_id=0x580 + self.node_id, data=response_data, is_extended_id=False)
            self.can_bus_manager.send_message(response)

        # READ request
        elif cmd == 0x40:
            value = self.read_object(index, sub)
            response = [0x43, data[1], data[2], sub] + \
                    list(value.to_bytes(4, "little"))
            response = can.Message(arbitration_id=0x580 + self.node_id, data=response_data, is_extended_id=False)
            self.can_bus_manager.send_message(response)
            
    def send_pdo(self):
        message = struct.pack('<Hl', self.status_word, int(self.position))
        pdo = can.Message(arbitration_id=0x380 + self.node_id, data=message, is_extended_id=False)
        self.can_bus_manager.send_message(pdo)
        
    
    def _control_loop(self):
        """Main control loop with multiple control modes"""
        dt = 1.0 / self.control_rate
        next_time = time.time()
        cycle_count = 0 
        

        print(bcolors.OKGREEN,f"Control loop started in {self.control_mode.value} mode", bcolors.ENDC)

        while self.running:
            cycle_count += 1
            # Execute control based on current mode
            if self.control_mode == ControlMode.DISABLED:
                # Send zero velocity to all drives
                for drive in self.devices:
                    drive.set_velocity(0)

            elif self.control_mode == ControlMode.POSITIONING:
                # print(self.target_position, self.actual_position)
                # self._update_positioning_mode(dt)
                error = self.target_position - self.position
                if abs(error) < 2 * revolutions_to_increments:
                    self.velocity = 0
                    self.status_word = 0x0400
                else: 
                    self.velocity = 2 * revolutions_to_increments * math.copysign(1, error)
                    self.status_word = 0x0040
                # print(f"{self.node_id}, {error/revolutions_to_increments},{self.target_position}, {self.position}, {self.velocity/revolutions_to_increments} ")
            
            # elif self.control_mode == ControlMode.TRACKING:
            #     self._update_tracking_mode(dt)
            self.position += self.velocity * dt
            # print(f"node: {self.node_id}", self.position)
            self.time += dt
            self.send_pdo()
            time.sleep(0.01 * dt)
            # print("error:", error)
            # if error <= 300 and self.state == DriveState.MOVING:
            #     print("statuso",self.status_word & 0x0400)
            #     self.status_word = self.status_word | 0x0400
            #     print("statuss",self.status_word & 0x0400)
            #     print("error: ", error)

    def _update_positioning_mode(self, dt: float):
        """Update positioning mode - move to static targets"""
        # PID control
        velocity = self.pid_controller.update(
            desired_position=self.target_position,
            actual_position=self.position,
            actual_velocity=self.velocity,
            desired_velocity=0.0,
            dt=dt
        )
        # Send velocity command
        self.velocity = velocity
        print(velocity)
            



@dataclass
class PIDController:
    """Rate-limited PID controller for high-frequency discrete control"""
    kp: float = 0.1  # Very small proportional gain
    ki: float = 0.0  # No integral initially
    kd: float = 0.0  # No derivative initially
    kv: float = 1.0  # Velocity feedforward gain

    # Rate limiting (THE KEY TO STABILITY)
    max_velocity_change: float = 0.5*revolutions_to_increments  

    # Internal state
    integral: float = 0.0
    last_error: float = 0.0
    last_time: float = 0.0
    last_output: float = 0.0

    # Gentle filtering (not too aggressive)
    error_history: list = None
    output_history: list = None
    filter_length: int = 3  # Light filtering

    # Limits
    output_limit: float = 1 * revolutions_to_increments  # 240 RPM in increments/sec
    integral_limit: float = 50000.0

    # Dead zone to prevent hunting
    dead_zone: float = 200.0

    # Anti-windup parameters
    anti_windup_gain: float = 1.0
    enable_anti_windup: bool = True

    # Velocity-based damping
    velocity_damping: float = 0.005  # Very light damping

    def __post_init__(self):
        """Initialize history buffers"""
        if self.error_history is None:
            self.error_history = []
        if self.output_history is None:
            self.output_history = []

    def reset(self):
        """Reset controller state"""
        self.integral = 0.0
        self.last_error = 0.0
        self.last_output = 0.0
        self.last_time = time.time()
        self.error_history.clear()
        self.output_history.clear()

    def update(self, desired_position: float, actual_position: float,
               actual_velocity: float, desired_velocity: float = 0.0, dt: float = 0.01) -> float:
        """
        Update PID with debugging for 10-cycle bug detection
        """

        # Position error
        position_error = desired_position - actual_position
        # print(bcolors.OKGREEN, f"error: {position_error}", bcolors.ENDC)
        # Check for sudden large position error changes
        if hasattr(self, 'last_position_error'):
            error_change = abs(position_error - self.last_position_error)
            # if error_change > 1000000:  # Large position error change
            #     print(f"WARNING: Large position error change: {error_change:.0f} counts")
            #     print(f"  Previous error: {self.last_position_error:.0f}, Current error: {position_error:.0f}")
        self.last_position_error = position_error

        # Dead zone - don't control tiny errors
        if abs(position_error) < self.dead_zone:
            # Gradually decay output to zero when in dead zone
            decay_factor = 0.95  # 5% decay per cycle
            new_output = self.last_output * decay_factor

            # Still apply rate limiting to decay
            velocity_change = new_output - self.last_output
            if abs(velocity_change) > self.max_velocity_change:
                velocity_change = math.copysign(self.max_velocity_change, velocity_change)
                new_output = self.last_output + velocity_change

            self.last_output = new_output
            return new_output

        # Light filtering of error
        self.error_history.append(position_error)
        if len(self.error_history) > self.filter_length:
            self.error_history.pop(0)

        # Use lightly filtered error
        if len(self.error_history) >= self.filter_length:
            filtered_error = sum(self.error_history) / len(self.error_history)
        else:
            filtered_error = position_error

        # Proportional term (use filtered error to reduce noise)
        p_term = self.kp * filtered_error

        # Check for large P term that could cause spikes
        p_term_rpm = p_term / (revolutions_to_increments * 60)
        # if abs(p_term_rpm) > 20:
        #     print(f"WARNING: Large P term: {p_term_rpm:.1f} RPM from error {filtered_error:.0f}")

        # Derivative term (only if Kd > 0 and we have history)
        d_term = 0.0
        if self.kd > 0 and len(self.error_history) >= 2 and dt > 0:
            # Simple derivative with light filtering
            error_derivative = (self.error_history[-1] - self.error_history[-2]) / dt
            d_term = self.kd * error_derivative

            # Check for large D term
            d_term_rpm = d_term / (revolutions_to_increments * 60)
            # if abs(d_term_rpm) > 20:
            #     print(f"WARNING: Large D term: {d_term_rpm:.1f} RPM from derivative {error_derivative:.0f}")

        # Velocity feedforward
        feedforward = self.kv * desired_velocity

        # Very light velocity damping
        damping = -self.velocity_damping * actual_velocity

        # Calculate desired output
        desired_output = p_term + d_term + feedforward + damping

        # Integral term (only if Ki > 0)
        if self.ki > 0:
            # Conservative integration
            if abs(self.last_output) < self.output_limit * 0.8:
                self.integral += filtered_error * dt

            # Apply integral limits
            if self.integral > self.integral_limit:
                self.integral = self.integral_limit
            elif self.integral < -self.integral_limit:
                self.integral = -self.integral_limit

            i_term = self.ki * self.integral
            i_term_rpm = i_term / (revolutions_to_increments * 60)
            # if abs(i_term_rpm) > 20:
            #     print(f"WARNING: Large I term: {i_term_rpm:.1f} RPM from integral {self.integral:.0f}")

            desired_output += i_term

        # CRITICAL: Apply rate limiting - this prevents the velocity spikes!
        velocity_change = desired_output - self.last_output

        # DEBUG: Check if rate limiting is being triggered
        if abs(velocity_change) > self.max_velocity_change:
            change_rpm = velocity_change / (revolutions_to_increments * 60)
            limit_rpm = self.max_velocity_change / (revolutions_to_increments * 60)
            # print(f"RATE LIMITING: Wanted change of {change_rpm:.1f} RPM, limited to {limit_rpm:.1f} RPM")
            velocity_change = math.copysign(self.max_velocity_change, velocity_change)

        # Calculate new output with rate limiting
        velocity_command = self.last_output + velocity_change

        # Light output filtering (optional)
        self.output_history.append(velocity_command)
        if len(self.output_history) > self.filter_length:
            self.output_history.pop(0)

        if len(self.output_history) >= self.filter_length:
            filtered_command = sum(self.output_history) / len(self.output_history)
            # Check if filtering makes a big difference
            filter_diff = abs(filtered_command - velocity_command) / (revolutions_to_increments * 60)
            # if filter_diff > 5:
            #     print(f"OUTPUT FILTERING: Changed command by {filter_diff:.1f} RPM")
            velocity_command = filtered_command

        # Apply absolute output limits
        if velocity_command > self.output_limit:
            # print(
                # f"OUTPUT LIMITING: Command {velocity_command / (revolutions_to_increments * 60):.1f} RPM limited to {self.output_limit / (revolutions_to_increments * 60):.1f} RPM")
            velocity_command = self.output_limit
        elif velocity_command < -self.output_limit:
            # print(
                # f"OUTPUT LIMITING: Command {velocity_command / (revolutions_to_increments * 60):.1f} RPM limited to {-self.output_limit / (revolutions_to_increments * 60):.1f} RPM")
            velocity_command = -self.output_limit

        # Store for next iteration
        self.last_output = velocity_command
        self.last_error = position_error
        # print(self.output_limit, velocity_command)
        return velocity_command

    def set_limits(self, max_velocity_rpm: float):
        """Set velocity limits based on RPM"""
        self.output_limit = max_velocity_rpm * 65536 * 100 / 60

    def set_dead_zone(self, dead_zone: float):
        """Set dead zone for small position errors"""
        self.dead_zone = dead_zone

    def set_rate_limit(self, max_change_rpm: float):
        """Set maximum velocity change per control cycle (THIS IS KEY!)"""
        self.max_velocity_change = max_change_rpm * revolutions_to_increments / 60
        print(f"Rate limit set to {max_change_rpm} RPM per cycle ({self.max_velocity_change:.0f} increments/sec/cycle)")


@dataclass
class TrajectoryPoint:
    """Single point in a trajectory"""
    position: float
    velocity: float
    acceleration: float
    time: float

  
    
    
class TrajectoryGenerator:
    """Generate smooth trajectories between positions"""

    def __init__(self, max_velocity: float = 100000, max_acceleration: float = 50000):
        self.max_velocity = max_velocity
        self.max_acceleration = max_acceleration

    def generate_point_to_point(self, start_pos: float, end_pos: float,
                                current_time: float, move_time: float = 2.0) -> TrajectoryPoint:
        """
        Generate a smooth point-to-point trajectory using S-curve profile

        Args:
            start_pos: Starting position
            end_pos: Target position
            current_time: Current time in the move
            move_time: Total time for the move

        Returns:
            TrajectoryPoint with position, velocity, acceleration
        """
        if current_time <= 0:
            return TrajectoryPoint(start_pos, 0, 0, current_time)
        elif current_time >= move_time:
            return TrajectoryPoint(end_pos, 0, 0, current_time)

        # Normalized time (0 to 1)
        t = current_time / move_time
        distance = end_pos - start_pos

        # S-curve (quintic polynomial) for smooth motion
        # Position profile: s(t) = 10t³ - 15t⁴ + 6t⁵
        s = 10 * t ** 3 - 15 * t ** 4 + 6 * t ** 5
        s_dot = (30 * t ** 2 - 60 * t ** 3 + 30 * t ** 4) / move_time
        s_ddot = (60 * t - 180 * t ** 2 + 120 * t ** 3) / (move_time ** 2)

        position = start_pos + distance * s
        velocity = distance * s_dot
        acceleration = distance * s_ddot

        return TrajectoryPoint(position, velocity, acceleration, current_time)
    

class VirtualSDR():
    def __init__(self):
        self.rx_hardwaregain_chan0 = 70.0 # dB
        self.rx_hardwaregain_chan1 = 70.0 # dB
        self.rx_lo = int(80e6) # Hz
        self.sample_rate = int(1e6) # Hz
        self.rx_rf_bandwidth = int(1e6) # filter width
        self.rx_buffer_size = 10000
        self.rx_enabled_channels = [0, 1]
        self.gain_control_mode_chan0 = 'manual'
        self.rx_rf_bandwidth = int(self.sample_rate*0.8)

    def rx(self):
        samples = []
        phi = 20
        for i in self.rx_enabled_channels:
            tone = np.exp(i*phi)*np.exp(2j*np.pi*self.sample_rate*0.1*np.arange(self.rx_buffer_size)/self.sample_rate)
            noise = np.random.randn(self.rx_buffer_size) + 1j*np.random.randn(self.rx_buffer_size)
            sample = self.rx_hardwaregain_chan0*tone*0.02 + 0.1*noise
            # Truncate to -1 to +1 to simulate ADC bit limits
            np.clip(sample.real, -1, 1, out=sample.real)
            np.clip(sample.imag, -1, 1, out=sample.imag)
            samples.append(sample)
        return np.squeeze(samples)
    

if __name__ == '__main__':
    tele = VirtualTelescope(1)
    tele.devices[0].running = True
    control_thread = threading.Thread(target=tele.devices[0]._control_loop, daemon=False)
    tele.can_bus_manager.start()
    control_thread.start()
    tele.devices[0].target_position = 100 * revolutions_to_increments