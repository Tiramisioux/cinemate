import logging
import subprocess
import threading
import time

class DmesgMonitor(threading.Thread):
    def __init__(self):
        super().__init__()
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

    def run(self):
        self._start_monitoring()

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
        # Main event loop
        while True:
            dmesg_lines = self.read_dmesg_log()
            new_messages = self.parse_dmesg_messages(dmesg_lines)
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
            time.sleep(5)


