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
        # emit the line to all subscribers
        event.emit(line.decode('utf-8'))
    out.close()

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
        # emit the line to all subscribers
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
            
            # Construct the command with the provided arguments
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
            self.initialized = True  # indicate that the instance has been initialized
            logging.info('CinePi instantiated')
