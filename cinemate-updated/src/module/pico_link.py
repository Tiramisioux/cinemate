import json
import logging
import socket
import threading
import time
from typing import Any


class PicoLinkService:
    """UDP beacon + command bridge between Cinemate (Pi) and a Pico node."""

    _METHOD_ALIAS = {
        "safe_shutdown": "shutdown",
        "set_shutter_a_sync_mode": "set shutter a sync",
        "set_shutter_a_sync": "set shutter a sync",
    }

    def __init__(self, redis_controller, settings: dict[str, Any], command_handler=None):
        self.redis = redis_controller
        self.command_handler = command_handler
        cfg = settings.get("pico_link", {})

        self.enabled = bool(cfg.get("enabled", False))
        self.beacon_host = str(cfg.get("beacon_host", "192.168.4.255"))
        self.beacon_port = int(cfg.get("beacon_port", 50020))
        self.bind_host = str(cfg.get("bind_host", "0.0.0.0"))
        self.command_port = int(cfg.get("command_port", 50021))
        self.time_beacon_hz = float(cfg.get("time_beacon_hz", 10.0))
        self.state_broadcast_on_change = bool(cfg.get("state_broadcast_on_change", True))
        self.state_heartbeat_sec = float(cfg.get("state_heartbeat_sec", 2.0))
        self.control_enabled = bool(cfg.get("control_enabled", False))
        self.allowed_commands = set(cfg.get("allowed_commands", []))
        self.allow_cli_commands = bool(cfg.get("allow_cli_commands", True))
        self.allow_method_calls = bool(cfg.get("allow_method_calls", True))
        self.cli_prefix_whitelist = list(cfg.get("cli_prefix_whitelist", []))
        self.state_keys = list(cfg.get("state_keys", ["iso", "shutter_a", "fps", "wb", "is_recording"]))

        self.beacon_addr = (self.beacon_host, self.beacon_port)

        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._seq_beacon = 0
        self._seq_state = 0
        self._last_state: dict[str, str] = {}

        self._tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._tx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        self._rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._rx_sock.bind((self.bind_host, self.command_port))
        self._rx_sock.settimeout(0.2)

    def start(self) -> None:
        if not self.enabled:
            logging.info("PicoLink disabled in settings")
            return

        if self._threads:
            return

        self._stop_event.clear()
        self._threads = [
            threading.Thread(target=self._beacon_loop, daemon=True, name="pico-link-beacon"),
            threading.Thread(target=self._state_loop, daemon=True, name="pico-link-state"),
            threading.Thread(target=self._command_loop, daemon=True, name="pico-link-command"),
        ]
        for t in self._threads:
            t.start()

        logging.info(
            "PicoLink started: beacon=%s:%s command=%s:%s",
            self.beacon_host,
            self.beacon_port,
            self.bind_host,
            self.command_port,
        )

    def stop(self) -> None:
        self._stop_event.set()

    def join(self, timeout: float = 1.0) -> None:
        for t in self._threads:
            if t.is_alive():
                t.join(timeout=timeout)
        self._threads.clear()

        try:
            self._rx_sock.close()
        except OSError:
            pass
        try:
            self._tx_sock.close()
        except OSError:
            pass

    def _send_json(self, payload: dict[str, Any], addr: tuple[str, int] | None = None) -> None:
        target = addr if addr is not None else self.beacon_addr
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._tx_sock.sendto(raw, target)

    def _coerce_float(self, key: str, default: float) -> float:
        val = self.redis.get_value(key)
        if val is None:
            return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def _coerce_int(self, key: str, default: int) -> int:
        val = self.redis.get_value(key)
        if val is None:
            return default
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return default

    def _fps_fraction(self, fps_value: float) -> tuple[int, int]:
        if abs(fps_value - 23.976) < 0.01:
            return (24000, 1001)
        if abs(fps_value - 29.97) < 0.01:
            return (30000, 1001)
        if abs(fps_value - 59.94) < 0.01:
            return (60000, 1001)
        rounded = max(1, int(round(fps_value)))
        return (rounded, 1)

    def _read_time_payload(self, seq: int) -> dict[str, Any]:
        pi_mono_ns = time.monotonic_ns()
        unix_ns = time.time_ns()

        fps_user = self._coerce_float("fps_user", self._coerce_float("fps", 24.0))
        fps_num, fps_den = self._fps_fraction(fps_user)

        tc_frame = self._coerce_int("framecount", 0)
        is_recording = self._coerce_int("is_recording", 0)

        return {
            "v": 1,
            "type": "time_beacon",
            "seq": seq,
            "pi_mono_ns": pi_mono_ns,
            "unix_ns": unix_ns,
            "fps_num": fps_num,
            "fps_den": fps_den,
            "dropframe": False,
            "tc_frame": tc_frame,
            "is_recording": bool(is_recording),
        }

    def _read_state(self) -> dict[str, str]:
        state: dict[str, str] = {}
        for key in self.state_keys:
            val = self.redis.get_value(key)
            if val is not None:
                state[key] = str(val)
        return state

    def _beacon_loop(self) -> None:
        hz = max(1.0, self.time_beacon_hz)
        period = 1.0 / hz

        while not self._stop_event.is_set():
            start = time.monotonic_ns()
            payload = self._read_time_payload(self._seq_beacon)
            self._seq_beacon += 1

            try:
                self._send_json(payload)
            except OSError as e:
                logging.debug("PicoLink beacon send failed: %s", e)

            elapsed = (time.monotonic_ns() - start) / 1e9
            sleep_s = max(0.0, period - elapsed)
            self._stop_event.wait(sleep_s)

    def _state_loop(self) -> None:
        last_heartbeat = 0.0
        while not self._stop_event.is_set():
            now = time.monotonic()
            state = self._read_state()
            changed = state != self._last_state
            due_hb = (now - last_heartbeat) >= self.state_heartbeat_sec

            should_send = due_hb or (self.state_broadcast_on_change and changed)
            if should_send:
                payload = {
                    "v": 1,
                    "type": "state_update",
                    "seq": self._seq_state,
                    "state": state,
                }
                self._seq_state += 1
                try:
                    self._send_json(payload)
                    self._last_state = state
                    last_heartbeat = now
                except OSError as e:
                    logging.debug("PicoLink state send failed: %s", e)

            self._stop_event.wait(0.05)

    def _ack(self, msg_id: str, ok: bool, addr: tuple[str, int], error: str = "") -> None:
        payload = {
            "v": 1,
            "type": "ack",
            "msg_id": msg_id,
            "ok": ok,
            "error": error,
        }
        try:
            self._send_json(payload, addr=addr)
        except OSError as e:
            logging.debug("PicoLink ack send failed: %s", e)

    def _command_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                raw, addr = self._rx_sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                if self._stop_event.is_set():
                    return
                continue

            msg_id = ""
            try:
                msg = json.loads(raw.decode("utf-8"))
                if msg.get("type") != "command":
                    continue

                msg_id = str(msg.get("msg_id", ""))
                cmd = str(msg.get("cmd", ""))
                value = msg.get("value")

                if not self.control_enabled:
                    self._ack(msg_id, False, addr, "control_disabled")
                    continue

                cmd_allowed = cmd in self.allowed_commands
                if cmd == "cli" and self.allow_cli_commands:
                    cmd_allowed = True
                if cmd == "call_method" and self.allow_method_calls:
                    cmd_allowed = True

                if not cmd_allowed:
                    self._ack(msg_id, False, addr, "command_not_allowed")
                    continue

                self._apply_command(cmd, value)
                self._ack(msg_id, True, addr)
            except Exception as e:
                self._ack(msg_id, False, addr, str(e))

    def _apply_command(self, cmd: str, value: Any) -> None:
        if cmd == "set_iso":
            self.redis.set_value("iso", int(value))
            return
        if cmd == "set_shutter_a":
            self.redis.set_value("shutter_a", float(value))
            return
        if cmd == "set_fps":
            self.redis.set_value("fps", float(value))
            return
        if cmd == "set_wb":
            self.redis.set_value("wb", int(value))
            return
        if cmd == "set_rec":
            self.redis.set_value("is_recording", 1 if bool(value) else 0)
            return

        if cmd == "cli":
            self._apply_cli(value)
            return

        if cmd == "call_method":
            if not self.allow_method_calls:
                raise ValueError("method_calls_disabled")
            self._apply_method_call(value)
            return

        raise ValueError("unsupported_command")

    def _apply_cli(self, value: Any) -> None:
        if not self.allow_cli_commands:
            raise ValueError("cli_commands_disabled")
        if self.command_handler is None:
            raise ValueError("command_handler_unavailable")

        if not isinstance(value, str):
            raise ValueError("cli_value_must_be_string")
        cli = value.strip()
        if not cli:
            raise ValueError("empty_cli_command")

        if self.cli_prefix_whitelist:
            if not any(cli == p or cli.startswith(p + " ") for p in self.cli_prefix_whitelist):
                raise ValueError("cli_command_not_whitelisted")

        self.command_handler(cli)

    def _apply_method_call(self, value: Any) -> None:
        if self.command_handler is None:
            raise ValueError("command_handler_unavailable")
        if not isinstance(value, dict):
            raise ValueError("call_method_value_must_be_object")

        method = str(value.get("method", "")).strip().lower()
        args = value.get("args", [])
        if not method:
            raise ValueError("missing_method")
        if args is None:
            args = []
        if not isinstance(args, list):
            raise ValueError("args_must_be_list")

        cli_base = self._method_to_cli(method)
        cli = cli_base if not args else f"{cli_base} {' '.join(str(a) for a in args)}"
        self._apply_cli(cli)

    def _method_to_cli(self, method_name: str) -> str:
        if method_name in self._METHOD_ALIAS:
            return self._METHOD_ALIAS[method_name]
        return method_name.replace("_", " ")
