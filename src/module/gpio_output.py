import importlib
import logging
from module.rpi_gpio_wrapper import RPi


class _ToneOutput:
    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError


class _SoftwarePWMToneOutput(_ToneOutput):
    def __init__(self, pin, frequency_hz, duty_cycle):
        self.pin = pin
        self.frequency_hz = frequency_hz
        self.duty_cycle = duty_cycle
        RPi.GPIO.setup(self.pin, RPi.GPIO.OUT)

    def start(self):
        handle = RPi.GPIO._get_handle()
        # lgpio PWM uses duty-cycle percentage in the range 0..100.
        RPi.GPIO.lgpio.tx_pwm(handle, self.pin, self.frequency_hz, self.duty_cycle)

    def stop(self):
        handle = RPi.GPIO._get_handle()
        RPi.GPIO.lgpio.tx_pwm(handle, self.pin, 0, 0)


class _HardwarePWMToneOutput(_ToneOutput):
    def __init__(self, pin, frequency_hz, duty_cycle):
        self.pin = pin
        self.frequency_hz = frequency_hz
        self.duty_cycle = duty_cycle
        self._pwm = None

        # rpi_hardware_pwm maps: GPIO 18 -> channel 0, GPIO 19 -> channel 1.
        channel = 0 if pin == 18 else 1
        pwm_module = importlib.import_module("rpi_hardware_pwm")
        self._pwm = pwm_module.HardwarePWM(
            pwm_channel=channel,
            hz=self.frequency_hz,
            chip=0,
        )

    def start(self):
        self._pwm.change_frequency(self.frequency_hz)
        self._pwm.start(self.duty_cycle)

    def stop(self):
        self._pwm.stop()

class GPIOOutput:
    HARDWARE_PWM_PINS = {18, 19}

    def __init__(self, rec_out_pins=None, rec_tone_pins=None, rec_tone_frequency_hz=1000, rec_tone_duty_cycle=50, rec_tone_relay_drop_frames=False):
        self.rec_out_pins = rec_out_pins if rec_out_pins is not None else []  # This is the list of pins for recording
        self.rec_tone_pins = self._normalize_pins(rec_tone_pins)
        self.rec_tone_frequency_hz = rec_tone_frequency_hz
        self.rec_tone_duty_cycle = rec_tone_duty_cycle
        self._tone_outputs = []
        self._is_tone_active = False
        self._is_rec_light_active = None
        self.rec_tone_relay_drop_frames = bool(rec_tone_relay_drop_frames)

        # Set up each pin in rec_out_pins as an output if the list is provided
        for pin in self.rec_out_pins:
            RPi.GPIO.setup(pin, RPi.GPIO.OUT)
            logging.info(f"REC light instantiated on pin {pin}")

        for pin in self.rec_tone_pins:
            tone_output = self._create_tone_output(pin)
            self._tone_outputs.append(tone_output)

    def _normalize_pins(self, pins):
        if pins is None:
            return []
        if isinstance(pins, int):
            return [pins]
        return [int(pin) for pin in pins]

    def _create_tone_output(self, pin):
        if pin in self.HARDWARE_PWM_PINS:
            try:
                logging.info(f"REC tone configured for hardware PWM on pin {pin}")
                return _HardwarePWMToneOutput(pin, self.rec_tone_frequency_hz, self.rec_tone_duty_cycle)
            except Exception as exc:
                logging.warning(
                    "Hardware PWM setup failed on pin %s (%s). Falling back to software PWM.",
                    pin,
                    exc,
                )

        logging.info(f"REC tone configured for software PWM on pin {pin}")
        return _SoftwarePWMToneOutput(pin, self.rec_tone_frequency_hz, self.rec_tone_duty_cycle)

    def _set_tone(self, active):
        if active == self._is_tone_active:
            return

        self._is_tone_active = active
        for idx, tone_output in enumerate(list(self._tone_outputs)):
            try:
                if active:
                    logging.info(f"Setting REC tone ON on pin {tone_output.pin}")
                    tone_output.start()
                else:
                    logging.info(f"Setting REC tone OFF on pin {tone_output.pin}")
                    tone_output.stop()
            except Exception as exc:
                # If hardware PWM fails at runtime, fall back to software PWM.
                if active and isinstance(tone_output, _HardwarePWMToneOutput):
                    logging.warning(
                        "Hardware PWM start failed on pin %s (%s). Falling back to software PWM.",
                        tone_output.pin,
                        exc,
                    )
                    try:
                        fallback = _SoftwarePWMToneOutput(
                            tone_output.pin,
                            self.rec_tone_frequency_hz,
                            self.rec_tone_duty_cycle,
                        )
                        self._tone_outputs[idx] = fallback
                        fallback.start()
                        continue
                    except Exception as fallback_exc:
                        logging.warning(
                            "Software PWM fallback failed on pin %s (%s).",
                            tone_output.pin,
                            fallback_exc,
                        )

                logging.warning(f"Failed to {'start' if active else 'stop'} REC tone on pin {tone_output.pin}: {exc}")

    def set_rec_light(self, active):
        is_active = bool(active)
        if self._is_rec_light_active is is_active:
            return

        self._is_rec_light_active = is_active
        for pin in self.rec_out_pins:
            RPi.GPIO.output(pin, RPi.GPIO.HIGH if is_active else RPi.GPIO.LOW)
            logging.info(f"GPIO {pin} set to {'HIGH' if is_active else 'LOW'}")

    def set_rec_tone(self, active):
        self._set_tone(bool(active))


    def relay_drop_frame_on_rec_tone(self, drop_frame_active):
        if not self.rec_tone_relay_drop_frames:
            return

        if not self._is_tone_active:
            return

        for tone_output in self._tone_outputs:
            try:
                if drop_frame_active:
                    tone_output.stop()
                else:
                    tone_output.start()
            except Exception as exc:
                logging.warning(f"Failed to {'stop' if drop_frame_active else 'start'} REC tone for drop-frame relay: {exc}")

    def set_recording(self, status):
        """Set the status of the recording pins based on the given status."""
        is_recording = bool(status)
        for pin in self.rec_out_pins:
            RPi.GPIO.output(pin, RPi.GPIO.HIGH if is_recording else RPi.GPIO.LOW)
            logging.info(f"GPIO {pin} set to {'HIGH' if is_recording else 'LOW'}")

        self._set_tone(is_recording)
