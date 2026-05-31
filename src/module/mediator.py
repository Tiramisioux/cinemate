import logging
import threading
import json
import time
from module.redis_controller import ParameterKey

class Mediator:
    def __init__(self, cinepi_app, cinepi_controller, redis_listener, redis_controller, ssd_monitor, gpio_output, stream, usb_monitor):
        self.cinepi_app = cinepi_app
        self.cinepi_controller = cinepi_controller
        self.redis_listener = redis_listener
        self.redis_controller = redis_controller
        self.ssd_monitor = ssd_monitor
        self.gpio_output = gpio_output
        self.stream = stream
        self.usb_monitor = usb_monitor

        # Other event subscriptions
        self.cinepi_app.message.subscribe(self.handle_cinepi_message)
        self.redis_controller.redis_parameter_changed.subscribe(self.handle_redis_event)
        self.redis_controller.redis_parameter_changed.subscribe(self.handle_fps_change)
        self.redis_controller.redis_parameter_changed.subscribe(self.handle_shutter_a_change)

        self.stop_recording_timer = None
        self.stop_recording_timeout = 2

        self._is_recording = False
        self._is_writing = False
        self._storage_preroll_active = False
        self._drop_frame_relay_active = False

        logging.info("Mediator instantiated")
        
    def load_ssd_settings(self, settings_file):
        """Load SSD settings from the specified JSON file."""
        try:
            with open(settings_file, 'r') as file:
                settings = json.load(file)
                return settings.get('recognized_ssds', [])
        except Exception as e:
            logging.error(f"Failed to load SSD settings: {e}")
            return []
    
    def handle_cinepi_message(self, message):
        if hasattr(self.cinepi_controller, "handle_cinepi_raw_message"):
            self.cinepi_controller.handle_cinepi_raw_message(message)

    def handle_ssd_event(self, action, message):
        # Handle SSD events
        logging.info(f"SSDMonitor says: {action} {message}")
        self.ssd_monitor.get_ssd_space_left()
        space_left = self.ssd_monitor.last_space_left
        logging.info(f'Space left: {space_left}')
        
    def handle_ssd_unmount(self):
        logging.info("SSD unmounted.")
        self.recording_stop()

    def recording_stop(self):
        self.redis_controller.set_value(ParameterKey.IS_RECORDING.value, 0)
        self.redis_controller.set_value(ParameterKey.IS_WRITING.value, 0)
        self._is_recording = False
        self._is_writing = False
        self._refresh_gpio_outputs()

    def handle_write_status_change(self, status):
        self.redis_controller.set_value(ParameterKey.IS_WRITING.value, status)

        # Start or reset the timer when recording stops (status = 0)        
        if status == 0:
            if self.stop_recording_timer is None or not self.stop_recording_timer.is_alive():
                self.stop_recording_timer = threading.Timer(self.stop_recording_timeout, self.handle_stop_recording_timeout)
                self.stop_recording_timer.start()
        # Reset the timer when recording starts (status = 1)
        elif status == 1:
            if self.stop_recording_timer and self.stop_recording_timer.is_alive():
                self.stop_recording_timer.cancel()        

    @staticmethod
    def _as_bool(value):
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def _refresh_gpio_outputs(self):
        # REC light follows actual write status.
        self.gpio_output.set_rec_light(self._is_writing)

        # REC sync tone follows record intent, but is muted during storage pre-roll.
        tone_active = self._is_recording and not self._storage_preroll_active
        self.gpio_output.set_rec_tone(tone_active)
        self.gpio_output.relay_drop_frame_on_rec_tone(self._drop_frame_relay_active)

    def handle_redis_event(self, data):
        key = data.get('key')

        if key == ParameterKey.STORAGE_PREROLL_ACTIVE.value:
            self._storage_preroll_active = self._as_bool(data.get('value'))
            self._refresh_gpio_outputs()
            return

        # Start REC tone immediately on REC command edge, but do not use REC
        # as a persistent recording-state source (REC can be edge-triggered).
        if key == ParameterKey.REC.value:
            rec_edge = self._as_bool(data.get('value'))
            if rec_edge and not self._storage_preroll_active:
                self.gpio_output.set_rec_tone(1)
            return

        # IS_RECORDING is the authoritative persistent recording state.
        if key == ParameterKey.IS_RECORDING.value:
            self._is_recording = self._as_bool(data.get('value'))
            if self._is_recording:
                logging.info("Recording started!")
                if not self._storage_preroll_active:
                    # Start the sync tone immediately on record command.
                    self.gpio_output.set_rec_tone(1)

                # Cancel the stop_recording_timer if it's running
                if self.stop_recording_timer is not None and self.stop_recording_timer.is_alive():
                    self.stop_recording_timer.cancel()
            else:
                logging.info("Recording stopped!")
                # REC light / GUI red should reflect real frame writes.
                # Once recording intent is off, clear write-active state.
                self._is_writing = False
                self.redis_controller.set_value(ParameterKey.IS_WRITING.value, 0)
                self._refresh_gpio_outputs()

            return

        # Treat per-frame encoder notifications as proof that frames are
        # landing on storage while recording is active.
        if key in (ParameterKey.LAST_DNG_CAM0.value, ParameterKey.LAST_DNG_CAM1.value):
            if self._is_recording and not self._is_writing:
                self._is_writing = True
                self.redis_controller.set_value(ParameterKey.IS_WRITING.value, 1)
                self._refresh_gpio_outputs()
            return

        if key == ParameterKey.DROP_FRAME_RELAY.value:
            self._drop_frame_relay_active = self._as_bool(data.get('value'))
            self.gpio_output.relay_drop_frame_on_rec_tone(self._drop_frame_relay_active)
            return

        # Handle "is_writing" key changes
        if key == ParameterKey.IS_WRITING.value:
            self._is_writing = self._as_bool(data.get('value'))
            if self._is_writing and hasattr(self.stream, "toggle_background_color"):
                try:
                    self.stream.toggle_background_color()
                except Exception as exc:
                    logging.warning("Failed to toggle stream background color: %s", exc)

            self._refresh_gpio_outputs()

    def handle_stop_recording_timeout(self):
        """Handle the timeout event when recording should be stopped."""
        self.redis_controller.set_value(ParameterKey.IS_WRITING_BUF.value, 0)
        self.redis_controller.set_value(ParameterKey.IS_RECORDING.value, 0)
        self.redis_controller.set_value(ParameterKey.IS_WRITING.value, 0)
        self._is_recording = False
        self._is_writing = False
        self._refresh_gpio_outputs()

        logging.info("Stop recording timeout reached. Stopping recording...")

    def handle_fps_change(self, data):
        # Handle "fps" key changes
            fps_new = self.redis_controller.get_value(ParameterKey.FPS.value)
            
    def handle_shutter_a_change(self, data):
        # Handle "shutter_a" key changes
        if data['key'] == ParameterKey.SHUTTER_A.value:
            shutter_a_new = self.redis_controller.get_value(ParameterKey.SHUTTER_A.value)
