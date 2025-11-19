import logging
import select
import subprocess
import threading

class DmesgMonitor(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.keywords = {
            "Undervoltage": "Under-voltage detected!",
            "Voltage_normalised": "Voltage normalised",
            "sda": "sda"
        }
        self.last_occurrence = {key: None for key in self.keywords}
        self.undervoltage_flag = False
        self.undervoltage_timer = None
        self.disk_attached = False
        self.disk_detached_event = threading.Event()
        self._stop_event = threading.Event()

    def run(self):
        self._start_monitoring()
        
    def stop(self):
        """Signal the monitoring loop to exit."""
        self._stop_event.set()


    def read_dmesg_log(self):
        try:
            result = subprocess.run(['dmesg'], capture_output=True, text=True)
            return result.stdout.splitlines()
        except Exception as e:
            logging.error(f"Error reading dmesg log: {e}")
            return []

    def parse_dmesg_messages(self, lines):
        parsed_messages = {}
        for line in lines:
            for key, value in self.keywords.items():
                if value in line:
                    parsed_messages[key] = line
        return parsed_messages

    def track_last_occurrence(self, messages):
        new_messages = {}
        for message_type, message in messages.items():
            if self.last_occurrence[message_type] != message:
                new_messages[message_type] = message
                self.last_occurrence[message_type] = message
        return new_messages

    def handle_file_change(self):
        #logging.info("File change detected")
        pass

    def reset_undervoltage_flag(self):
        self.undervoltage_flag = False
        #logging.info("Under voltage flag reset.")

    def _start_monitoring(self):
        process = None
        try:
            process = subprocess.Popen(
                ["dmesg", "--follow", "--human"],
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            while not self._stop_event.is_set():
                ready, _, _ = select.select([process.stdout], [], [], 0.5)
                if self._stop_event.is_set():
                    break

                for stream in ready:
                    line = stream.readline()
                    if not line:
                        if process.poll() is not None:
                            return
                        continue

                    new_messages = self.parse_dmesg_messages([line])
                    new_messages = self.track_last_occurrence(new_messages)
                    if new_messages:
                        for message_type, message in new_messages.items():
                            parts = message.split(":", 4)
                            if len(parts) > 4:
                                message = ":".join(parts[4:])
                                if "Under-voltage" in message:
                                    if not self.undervoltage_flag:
                                        logging.warning("Under-voltage detected!")
                                        self.undervoltage_flag = True
                                elif "Voltage normalised" in message:
                                    logging.info("Voltage normalised")
                                    self.undervoltage_flag = False
                                elif "sda" in message:
                                    if "[sda] Attached SCSI disk" in message:
                                        self.disk_attached = True
                                        logging.info("Disk attached.")
                                    elif "[sda] Synchronize Cache" and "failed" in message:
                                        self.disk_attached = False
                                        logging.info("Disk detached.")
                                        self.disk_detached_event.set()
        except Exception as e:
            logging.error(f"Error monitoring dmesg: {e}")
        finally:
            if process:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()


