import os
import subprocess
import logging
import time
import signal  # Added for SIGTERM signal

class AudioRecorder:

    def __init__(self, usb_monitor, gain=8):
        self.usb_monitor = usb_monitor
        self.directory = "/media/RAW"
        self.process = None
        self.gain = gain  # Set the gain value
        logging.info(f"AudioRecorder instantiated with gain value: {self.gain}")  # Logging message for instantiation
        
    def get_alsa_device(self):
        # Extract the card number from the device path
        device_path = self.usb_monitor.usb_mic.device_path
        card_num = device_path.split('card')[-1]
        # Form the ALSA device string
        return f"plughw:{card_num},0"

    def set_mic_gain(self):
        # Set the gain level using amixer command
        try:
            command = f"amixer -c {self.usb_monitor.usb_mic} sset 'Mic' {self.gain * 10}%"
            subprocess.check_call(command, shell=True)
            logging.info(f"Microphone gain set to: {self.gain * 10}%")
        except subprocess.CalledProcessError:
            logging.error("Failed to set microphone gain.")

    def start_recording(self):
        try:
            #logging.info(f"usb_mic {self.usb_monitor.usb_mic}")
            alsa_device = self.get_alsa_device()
            current_time = time.localtime()
            current_frame = str(current_time.tm_hour % 24).zfill(2)
            file_name = f"CINEPI_{time.strftime('%y-%m-%d_%H%M%S')}{current_frame}_AUDIO_SCRATCH.wav"
            self.file_path = os.path.join(self.directory, file_name)
            command = f"arecord -D {alsa_device} -f cd -c 1 -t wav {self.file_path}"
            self.process = subprocess.Popen(command, shell=True, preexec_fn=os.setsid, stderr=subprocess.DEVNULL)
            logging.info(f"Audio recording started")
        except Exception as e:
            logging.error(f"Failed to start audio recording. Error: {str(e)}")

    def stop_recording(self):
        if self.process:
            try:
                # First, attempt the regular graceful termination using SIGTERM.
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                logging.info(f"Audio recording stopped.")

                # Wait for a short duration to see if the process exits gracefully.
                time.sleep(1)

                # Check if the process is still running and force kill if it is.
                if self.process.poll() is None:  # None means the process is still running
                    os.kill(self.process.pid, signal.SIGKILL)
                    logging.warning(f"Audio recording process was forcefully killed.")

            except ProcessLookupError:
                # This error means the process has already terminated or does not exist.
                logging.warning(f"Process with PID {self.process.pid} not found. It might have already terminated.")
                
            except OSError as e:
                if e.errno == errno.ENODEV:  # No such device
                    logging.info("Microphone was disconnected. Stopping recording.")
                else:
                    raise e
                    
            except Exception as e:
                logging.error(f"Failed to stop recording. Error: {str(e)}")
                
        else:
            pass
            #logging.info("No audio recording to stop.")

