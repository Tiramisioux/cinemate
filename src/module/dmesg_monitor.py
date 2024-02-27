import logging
import subprocess
import inotify.adapters
import threading
import time

class DmesgMonitor(threading.Thread):
    def __init__(self, dmesg_file):
        super().__init__()
        self.dmesg_file = dmesg_file
        self.keywords = {
            "Undervoltage": "Undervoltage detected!",
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
            with open(self.dmesg_file, "r") as f:
                return f.readlines()
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
        # Initialize inotify
        i = inotify.adapters.Inotify()

        try:
            # Add the file to watch for changes
            i.add_watch(self.dmesg_file)

            # Main event loop
            for event in i.event_gen(yield_nones=False):
                (_, type_names, path, filename) = event

                if "IN_MODIFY" in type_names:
                    #logging.info("File modified")
                    dmesg_lines = self.read_dmesg_log()
                    new_messages = self.parse_dmesg_messages(dmesg_lines)
                    new_messages = self.track_last_occurrence(new_messages)
                    if new_messages:
                        #logging.info("New messages:")
                        for message_type, message in new_messages.items():
                            # Split by the third occurrence of ":"
                            parts = message.split(":", 4)
                            if len(parts) > 4:
                                message = ":".join(parts[4:])
                                if "Undervoltage" in message:
                                    if not self.undervoltage_flag:
                                        logging.warning("Undervoltage detected!")
                                        self.undervoltage_flag = True
                                        # Set a timer to reset the flag after 3 seconds
                                        # self.undervoltage_timer = threading.Timer(5, self.reset_undervoltage_flag)
                                        # self.undervoltage_timer.start()
                                elif "Voltage_normalised" in message:
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
                elif "IN_DELETE_SELF" in type_names:
                    self.logger.info("File deleted")
                    break
        finally:
            i.remove_watch(self.dmesg_file)
            i.close()


# import logging
# import subprocess
# import inotify.adapters
# import threading
# import time

# class DmesgMonitor(threading.Thread):
#     def __init__(self, dmesg_file):
#         super().__init__()
#         self.dmesg_file = dmesg_file
#         self.keywords = {
#             "Undervoltage": "Undervoltage detected!",
#             "Voltage_normalised": "Voltage normalised",
#             "sda": "sda"
#         }
#         self.last_occurrence = {key: None for key in self.keywords}
#         self.undervoltage_flag = False
#         self.undervoltage_timer = None
        
#     def run(self):
#         self._start_monitoring()

#     def read_dmesg_log(self):
#         try:
#             with open(self.dmesg_file, "r") as f:
#                 return f.readlines()
#         except Exception as e:
#             logging.error(f"Error reading dmesg log: {e}")
#             return []

#     def parse_dmesg_messages(self, lines):
#         parsed_messages = {}
#         for line in lines:
#             for key, value in self.keywords.items():
#                 if value in line:
#                     parsed_messages[key] = line
#         return parsed_messages

#     def track_last_occurrence(self, messages):
#         new_messages = {}
#         for message_type, message in messages.items():
#             if self.last_occurrence[message_type] != message:
#                 new_messages[message_type] = message
#                 self.last_occurrence[message_type] = message
#         return new_messages

#     def handle_file_change(self):
#         #logging.info("File change detected")
#         pass

#     def reset_undervoltage_flag(self):
#         self.undervoltage_flag = False
#         #logging.info("Under voltage flag reset.")

#     def _start_monitoring(self):
#         # Initialize inotify
#         i = inotify.adapters.Inotify()

#         try:
#             # Add the file to watch for changes
#             i.add_watch(self.dmesg_file)

#             # Main event loop
#             for event in i.event_gen(yield_nones=False):
#                 (_, type_names, path, filename) = event

#                 if "IN_MODIFY" in type_names:
#                     #logging.info("File modified")
#                     dmesg_lines = self.read_dmesg_log()
#                     new_messages = self.parse_dmesg_messages(dmesg_lines)
#                     new_messages = self.track_last_occurrence(new_messages)
#                     if new_messages:
#                         #logging.info("New messages:")
#                         for message_type, message in new_messages.items():
#                             # Split by the third occurrence of ":"
#                             parts = message.split(":", 4)
#                             if len(parts) > 4:
#                                 message = ":".join(parts[4:])
#                                 if "Undervoltage" in message:
#                                     if not self.undervoltage_flag:
#                                         logging.warning("Undervoltage detected!")
#                                         self.undervoltage_flag = True
#                                         # Set a timer to reset the flag after 3 seconds
#                                         # self.undervoltage_timer = threading.Timer(5, self.reset_undervoltage_flag)
#                                         # self.undervoltage_timer.start()
#                                 elif "Voltage_normalised" in message:
#                                     logging.info("Voltage normalised")
#                                     self.undervoltage_flag = False
#                                 elif "sda" in message:
#                                     logging.info(message)
#                                     self.undervoltage_flag = False
#                 elif "IN_DELETE_SELF" in type_names:
#                     self.logger.info("File deleted")
#                     break
#         finally:
#             i.remove_watch(self.dmesg_file)
#             i.close()
