"""A 60 Hz frame budget; request precise Windows timers only during motion."""
from __future__ import annotations

import sys
import time


class MotionTiming:
    def __init__(self):
        self.precise = False

    def start(self):
        if not self.precise and sys.platform == "win32":
            import ctypes
            self.precise = ctypes.windll.winmm.timeBeginPeriod(1) == 0

    def stop(self):
        if self.precise:
            import ctypes
            ctypes.windll.winmm.timeEndPeriod(1)
            self.precise = False

    @staticmethod
    def delay(started):
        return max(1, round(1000*(1/60-(time.perf_counter()-started))))
