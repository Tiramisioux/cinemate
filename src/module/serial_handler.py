# module/serial_handler.py
import time
import select
import threading
import logging
import queue
import serial
import errno

class SerialHandler(threading.Thread):
    """
    Robust USB-serial reader/writer with:
      • Per-port exponential backoff on open failures (no log spam/races)
      • Graceful handling of EIO (device vanished) with quiet close & flag
      • Safe newline-based decoding; filters NUL and empty lines
      • Debounced message delivery (threshold_time)
      • Accurate serial_connected flag for /dev/ttyACM0
    """
    def __init__(self, callback, baudrate=115200, timeout=0.05, log_queue=None):
        super().__init__(daemon=True)
        self.callback = callback
        self.baudrate = baudrate
        self.timeout = timeout
        self.log_queue = log_queue

        # Prefer ACM, but keep your fallbacks
        self.portlist = ['/dev/ttyACM0', '/dev/serial0', '/dev/ttyS0']

        self.serials = []                # list[serial.Serial]
        self.current_ports = []          # list[str]
        self.last_received_time = {}     # port -> last delivery time (s)
        self.serial_connected = False    # True only when ACM0 is open

        # Backoff state per port
        self._backoff = {}               # port -> seconds
        self._next_try = {}              # port -> epoch seconds
        self._backoff_min = 0.25
        self._backoff_max = 5.0

        self.running = True

    # ───────────────────────── private helpers ──────────────────────────
    def _open_port(self, port):
        """Try to open *port*. Returns serial.Serial or None."""
        try:
            # Use exclusive lock to avoid clashes; disable HW flow control.
            ser = serial.Serial(
                port=port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=0,
                rtscts=False,
                dsrdtr=False,
                exclusive=True
            )
            # Let the kernel/driver settle a moment; then drain junk.
            time.sleep(0.05)
            try:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
            except Exception:
                pass

            # Filter the banner/NUL bursts that can appear on first open
            t_end = time.time() + 0.10
            while time.time() < t_end and ser.in_waiting:
                _ = ser.read(ser.in_waiting)

            logging.info(f"Successfully opened port {port}")
            return ser
        except serial.SerialException as e:
            return None

    def _schedule_retry(self, port, immediate=False):
        b = self._backoff.get(port, self._backoff_min)
        if immediate:
            b = self._backoff_min
        else:
            b = min(self._backoff_max, b * 2 if b > 0 else self._backoff_min)
        self._backoff[port] = b
        self._next_try[port] = time.time() + b

    def _ready_to_try(self, port):
        return time.time() >= self._next_try.get(port, 0)

    def _decode_line(self, raw: bytes) -> str | None:
        if not raw:
            return None
        s = raw.decode('utf-8', 'ignore').strip('\r\n\0').strip()
        if not s:
            return None
        # Ignore explicit "b'\\x00'" string your old code was checking for
        if s == "\\x00" or s == "b'\\x00'":
            return None
        return s

    # ───────────────────────── public API ───────────────────────────────
    def write_to_ports(self, message: str):
        if not message.endswith('\n'):
            message += '\n'
        dead = []
        for ser in self.serials:
            try:
                ser.write(message.encode('utf-8', 'ignore'))
                logging.info(f"Sending on {ser.port} {message.strip()}")
            except (OSError, serial.SerialException) as e:
                logging.warning(f"Write failed on {ser.port}: {e}")
                dead.append(ser)
        for ser in dead:
            try:
                ser.close()
            except Exception:
                pass
            if ser.port == '/dev/ttyACM0':
                self.serial_connected = False
            self.serials.remove(ser)

    def read_from_ports(self):
        responses = []
        threshold_time = 0.10  # 100 ms debounce

        for ser in self.serials[:]:
            try:
                # Read all complete lines currently buffered
                while ser.in_waiting:
                    raw = ser.read_until(b'\n', 256)
                    line = self._decode_line(raw)
                    if line is None:
                        continue

                    now = time.time()
                    last = self.last_received_time.get(ser.port, 0)
                    if (now - last) < threshold_time:
                        # Optional: uncomment if you want to see debounced lines
                        # logging.debug(f"Debounced line on {ser.port}: {line}")
                        continue

                    self.last_received_time[ser.port] = now
                    responses.append((ser.port, line))

            except OSError as e:
                # Treat EIO as device vanished; close quietly and backoff.
                if getattr(e, 'errno', None) == errno.EIO:
                    logging.warning(f"Device vanished on {ser.port} (EIO). Closing and retrying later.")
                else:
                    logging.warning(f"Read failed on {ser.port}: {e}")
                try:
                    ser.close()
                except Exception:
                    pass
                if ser.port == '/dev/ttyACM0':
                    self.serial_connected = False
                self.serials.remove(ser)
                self._schedule_retry(ser.port)
            except serial.SerialException as e:
                logging.warning(f"Serial error on {ser.port}: {e}")
                try:
                    ser.close()
                except Exception:
                    pass
                if ser.port == '/dev/ttyACM0':
                    self.serial_connected = False
                self.serials.remove(ser)
                self._schedule_retry(ser.port)

        # Deliver outside the read loop
        for port, line in responses:
            logging.info(f"Received from {port}: {line}")
            try:
                self.callback(line)  # your CommandExecutor expects raw line
            except Exception as e:
                logging.error(f"Callback error for data '{line}': {e}")

        return responses

    def update_available_ports(self):
        # Cull ports that are no longer desired
        for ser in self.serials[:]:
            if ser.port not in self.portlist or not ser.is_open:
                try:
                    ser.close()
                except Exception:
                    pass
                self.serials.remove(ser)

        self.current_ports = [s.port for s in self.serials]

        # Try to (re)open missing ports, observing backoff
        for port in self.portlist:
            if port in self.current_ports:
                continue
            if not self._ready_to_try(port):
                continue
            ser = self._open_port(port)
            if ser:
                self.serials.append(ser)
                self.current_ports = [s.port for s in self.serials]
                self._backoff[port] = self._backoff_min
                self._next_try[port] = 0
                if port == '/dev/ttyACM0':
                    self.serial_connected = True
            else:
                self._schedule_retry(port)

        # Reconfirm state if ACM0 is not among current ports
        if '/dev/ttyACM0' not in self.current_ports:
            self.serial_connected = False

    def stop(self):
        self.running = False
        for ser in self.serials[:]:
            try:
                ser.close()
            except Exception:
                pass
        self.serials.clear()
        self.current_ports.clear()
        self.serial_connected = False

    def run(self):
        next_port_refresh = 0  # force initial scan

        while self.running:
            now = time.time()

            # Refresh ports either on cadence (when some are open) or when a
            # retry/backoff window has elapsed (when none are available).
            if now >= next_port_refresh:
                self.update_available_ports()
                now = time.time()
                if self.serials:
                    next_port_refresh = now + 0.5
                else:
                    next_retry = min(self._next_try.values(), default=now + 1.0)
                    next_port_refresh = max(now + 0.05, next_retry)

            pollable = [ser for ser in self.serials if ser.is_open]

            # Wait for input (or until the next port refresh) to avoid busy
            # polling when idle/no ports.
            timeout = max(0.0, next_port_refresh - time.time())
            if pollable:
                fd_map = {ser.fileno(): ser for ser in pollable}
                readable, _, _ = select.select(fd_map.keys(), [], [], timeout)
                if readable:
                    self.read_from_ports()
            else:
                time.sleep(timeout if timeout > 0 else 0.05)
