    import RPi.GPIO as GPIO
    import asyncio
    import signal
    import sys
    import logging
    from time import time
    from termcolor import colored

    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    class ColorizedLogger:
        @staticmethod
        def startup(message):
            logging.info(colored(message, 'cyan'))

        @staticmethod
        def press(message):
            logging.info(colored(message, 'green'))

        @staticmethod
        def release(message):
            logging.info(colored(message, 'blue'))

        @staticmethod
        def action(message):
            logging.info(colored(message, 'yellow'))

        @staticmethod
        def warning(message):
            logging.warning(colored(message, 'yellow', attrs=['bold']))

        @staticmethod
        def error(message):
            logging.error(colored(message, 'red'))

        @staticmethod
        def critical(message):
            logging.critical(colored(message, 'red', attrs=['bold']))

    class SmartButton:
        def __init__(self, buttons_config, controller, loop):
            self.buttons_config = buttons_config
            self.controller = controller
            self.press_action_map = {}
            self.release_action_map = {}
            self.hold_action_map = {}
            self.inverted_buttons = {}
            self.button_press_times = {}
            self.click_counts = {}
            self.button_states = {}  # To track the current state of each button
            self.event_queue = asyncio.Queue()
            self.loop = loop
            self.single_click_threshold = 1.0  # 1 second for single click detection
            self.hold_threshold = 1.0  # 1 second for hold action detection
            self.long_hold_threshold = 3.0  # 3 seconds for long hold detection
            self.long_hold_tasks = {}
            self.setup_buttons()

        def setup_buttons(self):
            for config in self.buttons_config:
                pin = config["pin"]
                pull_up = config["pull_up"]
                debounce_time = config["debounce_time"]

                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP if pull_up else GPIO.PUD_DOWN)
                ColorizedLogger.startup(f"Configured GPIO pin {pin} as input with {'PUD_UP' if pull_up else 'PUD_DOWN'} pull")

                initial_state = GPIO.input(pin)
                ColorizedLogger.startup(f"Initial state of pin {pin}: {'HIGH' if initial_state else 'LOW'}")
                self.inverted_buttons[pin] = initial_state == GPIO.HIGH
                if self.inverted_buttons[pin]:
                    ColorizedLogger.warning(f"Inverting logic for button on pin {pin} due to default HIGH state.")

                ColorizedLogger.startup(f"Setting up edge detection for pin {pin}")
                GPIO.add_event_detect(pin, GPIO.BOTH, callback=self.sync_handle_button_event, bouncetime=int(debounce_time * 1000))

                if "press_action" in config:
                    self.press_action_map[pin] = config.get("press_action", "None")
                    ColorizedLogger.startup(f"Mapped press action '{config.get('press_action', 'None')}' to pin {pin}")
                if "release_action" in config:
                    self.release_action_map[pin] = config.get("release_action", "None")
                    ColorizedLogger.startup(f"Mapped release action '{config.get('release_action', 'None')}' to pin {pin}")
                if "hold_action" in config:
                    self.hold_action_map[pin] = config.get("hold_action", "None")
                    ColorizedLogger.startup(f"Mapped hold action '{config.get('hold_action', 'None')}' to pin {pin}")

                self.button_press_times[pin] = None
                self.click_counts[pin] = 0
                self.button_states[pin] = False  # Initialize button state to not pressed

            asyncio.run_coroutine_threadsafe(self.process_events(), self.loop)

        def sync_handle_button_event(self, channel):
            asyncio.run_coroutine_threadsafe(self.handle_button_event(channel), self.loop)


        async def handle_button_event(self, channel):
            try:
                current_state = GPIO.input(channel)
                inverted = self.inverted_buttons.get(channel, False)
                is_pressed = current_state == GPIO.LOW if inverted else current_state == GPIO.HIGH

                if is_pressed:
                    self.button_states[channel] = True
                    ColorizedLogger.press(f"Button press detected on channel {channel}")
                    self.button_press_times[channel] = time()
                    self.click_counts[channel] += 1
                    self.direct_action_execution(channel)

                    if channel in self.long_hold_tasks and not self.long_hold_tasks[channel].done():
                        self.long_hold_tasks[channel].cancel()
                    self.long_hold_tasks[channel] = asyncio.run_coroutine_threadsafe(self.detect_long_hold(channel), self.loop)
                else:
                    self.button_states[channel] = False
                    ColorizedLogger.release(f"Button release detected on channel {channel}")
                    if channel in self.long_hold_tasks and not self.long_hold_tasks[channel].done():
                        self.long_hold_tasks[channel].cancel()
                    await self.event_queue.put((channel, False))
            except Exception as e:
                ColorizedLogger.error(f"Error handling button event on channel {channel}: {str(e)}")


        def direct_action_execution(self, channel):
            action = self.press_action_map.get(channel)
            if action:
                ColorizedLogger.action(f"Executing press action '{action}' for channel {channel}")
                method = getattr(self.controller, action, None)
                if method:
                    method()
                else:
                    ColorizedLogger.warning(f"No method '{action}' found in {self.controller}")

        async def detect_long_hold(self, channel):
            await asyncio.sleep(self.long_hold_threshold)
            if self.button_states[channel]:  # Check if the button is still pressed
                ColorizedLogger.action(f"Detected long hold action on channel {channel}")
                action = self.hold_action_map.get(channel)
                if action and action != "None":
                    method = getattr(self.controller, action, None)
                    if method:
                        method()

        async def process_events(self):
            click_threshold = 0.5  # Time window for detecting multiple clicks

            while True:
                channel, is_pressed = await self.event_queue.get()

                if is_pressed:
                    pass
                else:
                    press_time = self.button_press_times[channel]
                    if press_time is not None:
                        elapsed_time = time() - press_time

                        if elapsed_time < self.hold_threshold:
                            await asyncio.sleep(click_threshold)
                            self.handle_click_event(channel)
                        else:
                            self.handle_release_action(channel)
                        self.click_counts[channel] = 0

        def handle_click_event(self, channel):
            clicks = self.click_counts[channel]
            action = None
            if clicks == 1:
                action = self.press_action_map.get(channel)
                ColorizedLogger.action(f"Executing single click action '{action}' for channel {channel}")
            elif clicks == 2:
                action = self.press_action_map.get(channel)
                ColorizedLogger.action(f"Executing double click action '{action}' for channel {channel}")
            elif clicks == 3:
                action = self.press_action_map.get(channel)
                ColorizedLogger.action(f"Executing triple click action '{action}' for channel {channel}")
            
            if action and action != "None":
                method = getattr(self.controller, action, None)
                if method:
                    method()
                else:
                    ColorizedLogger.warning(f"No method '{action}' found in {self.controller}")

        def handle_release_action(self, channel):
            action = self.release_action_map.get(channel)
            if action and action != "None":
                ColorizedLogger.action(f"Executing release action '{action}' for channel {channel}")
                method = getattr(self.controller, action, None)
                if method:
                    method()
            else:
                ColorizedLogger.info(f"No specific release action defined or action is 'None' for channel {channel}")

        @staticmethod
        def cleanup():
            ColorizedLogger.startup("Cleaning up GPIO settings")
            GPIO.cleanup()

    # Mockup CinePiController class with methods corresponding to button actions
    class CinePiController:
        def rec(self):
            ColorizedLogger.action("Action: Recording started or stopped.")
            # Implement actual recording logic here

        def inc_iso(self):
            ColorizedLogger.action("Action: ISO increased.")
            # Implement ISO increment logic here

        def dec_iso(self):
            ColorizedLogger.action("Action: ISO decreased.")

        def set_fps_double(self):
            ColorizedLogger.action("Action: FPS doubled.")
            # Implement FPS double logic here

        def set_resolution(self):
            ColorizedLogger.action("Action: Resolution set.")
            # Implement resolution setting logic here

        def reboot(self):
            ColorizedLogger.critical("Action: System rebooting...")
            # Implement reboot logic here

        def safe_shutdown(self):
            ColorizedLogger.critical("Action: System shutting down safely...")
            # Implement safe shutdown logic here

        def unmount(self):
            ColorizedLogger.action("Action: Unmounting drives...")
            # Implement drive unmount logic here

        def release(self, channel):
            ColorizedLogger.action(f"Action: Button released on channel {channel}.")
            # Implement release logic here, if necessary

    # Configuration for the buttons (using BCM GPIO numbering)
    buttons_config = [
        {"pin": 4, "pull_up": False, "debounce_time": 0.1, "press_action": "rec", "release_action": "inc_iso", "hold_action": "unmount"},
        {"pin": 5, "pull_up": False, "debounce_time": 0.1, "press_action": "rec", "release_action": "None"},
        {"pin": 17, "pull_up": False, "debounce_time": 0.1, "press_action": "inc_iso", "release_action": "None"},
        {"pin": 14, "pull_up": False, "debounce_time": 0.1, "press_action": "dec_iso", "release_action": "None"},
        {"pin": 12, "pull_up": False, "debounce_time": 0.1, "single_click_action": "set_fps_double", "release_action": "None"},
        {"pin": 24, "pull_up": False, "debounce_time": 0.1, "single_click_action": "set_fps_double", "release_action": "None"},
        {"pin": 26, "pull_up": False, "debounce_time": 0.1, "single_click_action": "set_resolution", "double_click_action": "reboot", "hold_action": "unmount", "release_action": "None"},
    ]

    def signal_handler(sig, frame):
        ColorizedLogger.critical("Received signal for graceful shutdown")
        SmartButton.cleanup()
        sys.exit(0)

    async def main():
        ColorizedLogger.startup("Starting application")

        cinepi_controller = CinePiController()

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        ColorizedLogger.startup("GPIO mode set to BCM")

        smart_button_handler = SmartButton(buttons_config, cinepi_controller, asyncio.get_event_loop())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        ColorizedLogger.startup("Signal handlers registered for SIGINT and SIGTERM")

        while True:
            await asyncio.sleep(1)

    if __name__ == "__main__":
        try:
            ColorizedLogger.startup("Running... Press Ctrl+C to exit.")
            asyncio.run(main())
        except KeyboardInterrupt:
            ColorizedLogger.critical("Keyboard interrupt received, exiting.")
        finally:
            SmartButton.cleanup()
            ColorizedLogger.startup("Cleanup complete. Exiting.")
