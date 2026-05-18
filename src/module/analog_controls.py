import threading
import time
from module.grove_base_hat_adc import ADC
import smbus2
import logging
import traceback
from collections import deque

from module.redis_controller import ParameterKey

class AnalogControls(threading.Thread):
    def __init__(self, cinepi_controller, redis_controller, iso_pot=None, shutter_a_pot=None, fps_pot=None, wb_pot=None, iso_steps=None, shutter_a_steps=None, fps_steps=None, wb_steps=None):
        threading.Thread.__init__(self)

        self.cinepi_controller = cinepi_controller
        self.redis_controller = redis_controller

        self.adc = ADC()

        self.iso_pot = self.convert_to_int_or_none(iso_pot)
        self.shutter_a_pot = self.convert_to_int_or_none(shutter_a_pot)
        self.fps_pot = self.convert_to_int_or_none(fps_pot)
        self.wb_pot = self.convert_to_int_or_none(wb_pot)
        
        self.iso_steps = iso_steps or []
        self.shutter_a_steps = shutter_a_steps or []
        self.fps_steps = fps_steps or []
        self.wb_steps = wb_steps or []

        # Rolling buffers for filtering
        self.buffer_size = 5
        self.iso_buffer = deque(maxlen=self.buffer_size)
        self.shutter_a_buffer = deque(maxlen=self.buffer_size)
        self.fps_buffer = deque(maxlen=self.buffer_size)
        self.wb_buffer = deque(maxlen=self.buffer_size)

        # Last set values for debouncing
        self.last_iso = None
        self.last_shutter_a = None
        self.last_fps = None
        self.last_wb = None
        
        GROVE_BASE_HAT_ADDRESS = 0x08
        I2C_BUS = 1

        try:
            bus = smbus2.SMBus(I2C_BUS)
            bus.read_byte(GROVE_BASE_HAT_ADDRESS)
            self.grove_base_hat_connected = True
            logging.info("Grove Base HAT found!")
            bus.close()
        except OSError:
            self.grove_base_hat_connected = False
            logging.info("Grove Base HAT not found.")
        
        if self.grove_base_hat_connected:
            self.start()

    def convert_to_int_or_none(self, value):
        if value is None or value == 'None':
            return None
        try:
            return int(value)
        except ValueError:
            logging.error(f"Invalid potentiometer value: {value}")
            return None

    def moving_average(self, buffer):
        """Compute moving average for filtering."""
        return sum(buffer) / len(buffer) if buffer else None

    def map_adc_to_steps(self, adc_value, min_adc=0, max_adc=1023, steps=[], dead_zone_ratio=0.1):
        """Map ADC value to given steps with dead zones and hysteresis."""
        if not steps:
            return None

        step_range = len(steps)
        step_size = (max_adc - min_adc) / step_range
        dead_zone_size = step_size * dead_zone_ratio

        # Find the closest step index
        step_index = int((adc_value - min_adc) / step_size)

        # Ensure the value is within bounds
        step_index = max(0, min(step_index, step_range - 1))

        # Calculate center position of each step
        step_center = min_adc + step_size * (step_index + 0.5)

        # Implement dead zone: Only accept values outside the dead zone
        lower_bound = step_center - (dead_zone_size / 2)
        upper_bound = step_center + (dead_zone_size / 2)

        if lower_bound <= adc_value <= upper_bound:
            return None  # Stay on current value
        else:
            return steps[step_index]

 # ───── helper ──────────────────────────────────────────────────────────
    def _get_steps(self, kind: str):
        """
        Return the *current* legal step table for iso / shutter / fps / wb.

        • honours the free-mode flags that the controller may toggle later  
        • honours shutter-sync rules for fps and shutter_a  
        • always uses the controller’s *live* tables – never the cached copies
        """
        c = self.cinepi_controller   # shorthand

        if kind == 'iso':
            return c.iso_steps                      # already rebuilt by update_steps()

        if kind == 'shutter_a':
            if c.shutter_a_free or c.shutter_a_sync_mode == 1:
                return [round(i * 0.1, 1) for i in range(10, 3601)]
            return c.shutter_a_steps_dynamic        # includes flicker-free angles

        if kind == 'fps':
            # NOTE: fps_max is set in CinePiController via int(get_fps_max()),
            # which truncates the raw sensor capability (e.g. 49.97 Hz) to 49.
            # Thus, even in free mode, the range is 1..49, not up to 50.
            if c.fps_free or c.shutter_a_sync_mode == 1:
                return list(range(1, c.fps_max + 2))
            return c.fps_steps                      # snapped list

        if kind == 'wb':
            return c.wb_steps                       # free-mode handled in controller

        return []      # fallback – should never happen



    def update_parameters(self):
        try:
            # ISO
            if self.iso_pot is not None:
                iso_read = self.adc.read(self.iso_pot)
                self.iso_buffer.append(iso_read)
                smoothed_iso = self.moving_average(self.iso_buffer)
                new_iso = self.map_adc_to_steps(smoothed_iso, 
                                                steps=self._get_steps('iso'))

                if new_iso is not None and new_iso != self.last_iso:
                    logging.info(
                        f"ISO changed → ADC raw={iso_read}, smoothed={smoothed_iso}, mapped={new_iso}"
                    )
                    self.cinepi_controller.set_iso(new_iso)
                    self.last_iso = new_iso

            # SHUTTER ANGLE
            if self.shutter_a_pot is not None:
                shutter_a_read   = self.adc.read(self.shutter_a_pot)
                self.shutter_a_buffer.append(shutter_a_read)
                smoothed_shutter = self.moving_average(self.shutter_a_buffer)

                new_shutter_a = self.map_adc_to_steps(
                    smoothed_shutter,
                    steps=self._get_steps('shutter_a')
                )

                # ── debounce: ignore sub-degree jitter, but only in sync / free mode
                MIN_DEG_DELTA = (1.0 if self.cinepi_controller.shutter_a_sync_mode == 1
                                    or self.cinepi_controller.shutter_a_free
                                else 0.1)

                if (new_shutter_a is not None and
                        (self.last_shutter_a is None or
                        abs(new_shutter_a - self.last_shutter_a) >= MIN_DEG_DELTA)):

                    logging.info(
                        f"Shutter Angle changed → "
                        f"ADC raw={shutter_a_read}, smoothed={smoothed_shutter}, "
                        f"mapped={new_shutter_a}"
                    )
                    self.cinepi_controller.set_shutter_a_nom(new_shutter_a)
                    self.last_shutter_a = new_shutter_a

            # FPS
            if self.fps_pot is not None:
                fps_read = self.adc.read(self.fps_pot)
                self.fps_buffer.append(fps_read)
                smoothed_fps = self.moving_average(self.fps_buffer)
                new_fps = self.map_adc_to_steps(smoothed_fps,
                                steps=self._get_steps('fps'))


                if new_fps is not None and new_fps != self.last_fps:
                    logging.info(
                        f"FPS changed → ADC raw={fps_read}, smoothed={smoothed_fps}, mapped={new_fps}"
                    )
                    self.cinepi_controller.set_fps(new_fps)
                    self.last_fps = new_fps

            # WHITE BALANCE
            if self.wb_pot is not None:
                wb_read = self.adc.read(self.wb_pot)
                self.wb_buffer.append(wb_read)
                smoothed_wb = self.moving_average(self.wb_buffer)
                new_wb = self.map_adc_to_steps(smoothed_wb,
                               steps=self._get_steps('wb'))


                if new_wb is not None and new_wb != self.last_wb:
                    logging.info(
                        f"White Balance changed → ADC raw={wb_read}, smoothed={smoothed_wb}, mapped={new_wb}K"
                    )
                    self.redis_controller.set_value(ParameterKey.WB_USER.value, new_wb)
                    self.cinepi_controller.set_wb(new_wb)
                    self.last_wb = new_wb

        except Exception as e:
            logging.error(f"Error occurred while updating parameters: {e}\n{traceback.format_exc()}")

    def run(self):
        try:
            while True:
                if self.grove_base_hat_connected:
                    self.update_parameters()
                    
                time.sleep(0.1)  # Adjust delay as needed
        except Exception as e:
            logging.error(f"Error occurred in AnalogControls run loop: {e}\n{traceback.format_exc()}")