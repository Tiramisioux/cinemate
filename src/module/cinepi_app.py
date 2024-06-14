import subprocess
import logging
from queue import Queue
from threading import Thread

class Event:
    def __init__(self):
        self._listeners = []

    def subscribe(self, listener):
        self._listeners.append(listener)

    def emit(self, data=None):
        for listener in self._listeners:
            listener(data)

def enqueue_output(out, queue, event):
    for line in iter(out.readline, b''):
        queue.put(line)
        event.emit(line.decode('utf-8'))
    out.close()

class CinePi:
    _instance = None  # Singleton instance

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, *cinepi_args):
        if not hasattr(self, 'initialized'):  # only initialize once
            self.message = Event()
            self.suppress_output = False
            self.cinepi_args = cinepi_args
            
            self.start_cinepi_process(cinepi_args)
            self.initialized = True  # indicate that the instance has been initialized
            logging.info('CinePi instantiated')

    def start_cinepi_process(self, cinepi_args):
        command = ['cinepi-raw'] + list(cinepi_args)
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        self.out_queue = Queue()
        self.err_queue = Queue()

        self.out_thread = Thread(target=enqueue_output, args=(self.process.stdout, self.out_queue, self.message))
        self.err_thread = Thread(target=enqueue_output, args=(self.process.stderr, self.err_queue, self.message))
        
        self.out_thread.daemon = True
        self.err_thread.daemon = True
        self.out_thread.start()
        self.err_thread.start()

    def shutdown(self):
        """Shut down the CinePi instance."""
        logging.info('Shutting down CinePi instance.')
        self.process.terminate()
        self.process.wait()
        logging.info('CinePi instance shut down.')

    def restart(self, *new_args):
        """Restart the CinePi instance."""
        logging.info('Restarting CinePi instance.')
        self.shutdown()
        
        # Update the args for the new process
        self.cinepi_args = new_args
        
        # Restart the process with new arguments
        self.start_cinepi_process(new_args)
        logging.info('CinePi instance restarted.')