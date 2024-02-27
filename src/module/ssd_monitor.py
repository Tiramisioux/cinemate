import threading
import logging
import time
import os
import pyinotify
import subprocess

class SSDMonitor:
    def __init__(self):
        self.path = '/media/RAW'
        self.last_space_left = None
        self.space_decreasing_event = threading.Event()
        self.space_stable_event = threading.Event()
        self._monitor_thread_stop_event = threading.Event()
        self._monitor_thread = threading.Thread(target=self._monitor_space, daemon=True)

        # Check if the drive is already mounted at startup
        if os.path.exists(self.path) and self.is_drive_mounted():
            logging.info("Drive is already mounted at startup.")
            self.start_monitoring()
        else:
            logging.info("Drive is not mounted at startup. Waiting for mount event...")

    def start_monitoring(self):
        if not self._monitor_thread.is_alive():
            self._monitor_thread.start()
            logging.info("Started monitoring for space on the SSD.")

    def stop_monitoring(self):
        self._monitor_thread_stop_event.set()
        self._monitor_thread.join()

    def _monitor_space(self):
        while not self._monitor_thread_stop_event.is_set():
            if self.is_drive_mounted():
                current_space = self.get_ssd_space_left()
                if current_space is not None and self.last_space_left is not None:
                    if current_space < self.last_space_left:
                        self.space_decreasing_event.set()
                        #logging.info("Space decreasing on the SSD.")
                    elif current_space > self.last_space_left:
                        self.space_stable_event.set()
                        #logging.info("Space stable on the SSD.")
                self.last_space_left = current_space
            else:
                #logging.info("Drive is not mounted.")
                time.sleep(1)  # Check every 10 seconds

    def get_ssd_space_left(self):
        if self.is_drive_mounted():
            stat = os.statvfs(self.path)
            # Get available space in GB
            space_left = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
            return space_left
        else:
            return None

    def output_ssd_space_left(self):
        space_left = self.get_ssd_space_left()
        if space_left is not None:
            logging.info(f"Space left: {space_left} GB.")
        else:
            logging.warning("SSD not mounted or path does not exist.")

    def unmount_drive(self):
        if self.is_drive_mounted():
            logging.info("Unmounting the drive...")
            subprocess.run(["umount", self.path])
            logging.info("Drive is unmounted.")
        else:
            logging.info("Drive is not mounted.")

    def is_drive_mounted(self):
        """Check if the drive is mounted."""
        return os.path.ismount(self.path)


class EventHandler(pyinotify.ProcessEvent):
    def __init__(self, path, ssd_monitor, notifier):
        self.path = path
        self.ssd_monitor = ssd_monitor
        self.notifier = notifier

    def process_default(self, event):
        if event.pathname.endswith('RAW') and event.mask & pyinotify.IN_CREATE:
            logging.info(f"Drive mounted at: {event.pathname}")
            self.ssd_monitor.start_monitoring()  # Start monitoring after drive is mounted
            self.notifier.stop()
        elif event.pathname == '/media' and event.mask & pyinotify.IN_DELETE:
            logging.info("Drive removed.")
            self.ssd_monitor.stop_monitoring()  # Stop monitoring when drive is removed
            # Check if /media/RAW still exists and remove it if it does
            if os.path.exists(self.ssd_monitor.path):
                # Add a delay before attempting to remove the directory
                time.sleep(1)  # Adjust the delay time as needed
                logging.info("Unmounting the drive...")
                subprocess.run(["umount", self.ssd_monitor.path])
                logging.info("Drive is unmounted.")
                logging.info("Removing /media/RAW directory...")
                os.rmdir(self.ssd_monitor.path)
                logging.info("/media/RAW directory removed.")

        else:
            logging.debug(f"Event: {event.pathname}, Mask: {event.mask}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ssd_monitor = SSDMonitor()
    wm = pyinotify.WatchManager()
    notifier = pyinotify.Notifier(wm, EventHandler(path='/media', ssd_monitor=ssd_monitor, notifier=notifier))

    wm.add_watch('/media', pyinotify.IN_CREATE | pyinotify.IN_DELETE)

    # Block the main thread until termination signal is received
    try:
        notifier.loop()
    except KeyboardInterrupt:
        logging.info("Exiting...")

