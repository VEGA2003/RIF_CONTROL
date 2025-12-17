from system_config import ARS2108System, ControlWord
import can
import time
import struct
import threading
from enum import Enum, auto
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass


system = ARS2108System()

system.start()


system.set_velocity(10000000)
time.sleep(5)
system.set_velocity(0)
time.sleep(1)
system.start_homing()
# system.set_position_sdo(10000000)
time.sleep(30)

system.stop()
