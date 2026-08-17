"""status_broadcast.py — UDP status broadcaster for the Cinemate Web API.

Broadcasts a single plain-text `key=value ...` line to the hotspot subnet
so tally lights and displays need no HTTP connection, no parser, and no
per-device load on the camera. See docs/web-api.md ("UDP broadcast") and
dev_projects/web-api/IMPLEMENTATION-PLAN.md section 4.9.
"""
from __future__ import annotations

import logging
import socket
import struct
import threading
import time

logger = logging.getLogger(__name__)

MAX_PAYLOAD_BYTES = 500
COALESCE_MAX_HZ = 10  # never send faster than this even on a burst of changes


def subnet_broadcast_address(iface: str = "wlan0"):
    """Best-effort subnet broadcast address for *iface* (e.g. 10.42.0.255
    for a 10.42.0.1/24 hotspot). Returns None if the interface has no IPv4
    address yet — the caller still has 255.255.255.255 to fall back on."""
    try:
        import fcntl
        SIOCGIFADDR = 0x8915
        SIOCGIFNETMASK = 0x891B
        ifname = struct.pack('256s', iface[:15].encode())
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            ip_packed = fcntl.ioctl(sock.fileno(), SIOCGIFADDR, ifname)[20:24]
            mask_packed = fcntl.ioctl(sock.fileno(), SIOCGIFNETMASK, ifname)[20:24]
        finally:
            sock.close()
        ip = struct.unpack('!I', ip_packed)[0]
        mask = struct.unpack('!I', mask_packed)[0]
        broadcast = ip | (~mask & 0xFFFFFFFF)
        return socket.inet_ntoa(struct.pack('!I', broadcast))
    except Exception as exc:
        logger.debug("Could not resolve broadcast address for %s: %s", iface, exc)
        return None


def build_payload(get_value, keys) -> bytes:
    """Assemble the `key=value ...` status line. Pure function of a value
    getter and a key list — this is the unit-testable core (plan section 9)."""
    line = " ".join(f"{key}={get_value(key, '')}" for key in keys)
    payload = line.encode("utf-8")
    if len(payload) > MAX_PAYLOAD_BYTES:
        logger.warning(
            "Status broadcast payload %d bytes > %d, truncating",
            len(payload), MAX_PAYLOAD_BYTES,
        )
        payload = payload[:MAX_PAYLOAD_BYTES]
    return payload


class StatusBroadcaster(threading.Thread):
    """Subscribes to RedisController.redis_parameter_changed and pushes a
    coalesced plain-text status line over UDP broadcast."""

    def __init__(self, redis_controller, keys, *, port=8888, hz=5, iface="wlan0"):
        super().__init__(daemon=True)
        self.redis_controller = redis_controller
        self.keys = list(keys)
        self.port = port
        self.hz = hz if hz and hz > 0 else 5
        self.iface = iface
        self.running = True

        self._dirty = threading.Event()
        self._dirty.set()  # send once at startup
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        redis_controller.redis_parameter_changed.subscribe(self._on_change)

    def _on_change(self, data):
        if data and data.get("key") in self.keys:
            self._dirty.set()

    def _destinations(self):
        dests = {"255.255.255.255"}
        subnet_broadcast = subnet_broadcast_address(self.iface)
        if subnet_broadcast:
            dests.add(subnet_broadcast)
        return dests

    def _send(self):
        payload = build_payload(self.redis_controller.get_value, self.keys)
        for dest in self._destinations():
            try:
                self._sock.sendto(payload, (dest, self.port))
            except OSError as exc:
                logger.debug("Status broadcast send to %s failed: %s", dest, exc)

    def run(self):
        min_interval = 1.0 / COALESCE_MAX_HZ
        heartbeat_interval = 1.0 / self.hz
        last_sent = 0.0
        while self.running:
            triggered = self._dirty.wait(timeout=heartbeat_interval)
            if not self.running:
                break
            now = time.monotonic()
            if triggered:
                self._dirty.clear()
                since_last = now - last_sent
                if since_last < min_interval:
                    time.sleep(min_interval - since_last)
            self._send()
            last_sent = time.monotonic()

    def stop(self):
        self.running = False
        self._dirty.set()
        self.redis_controller.redis_parameter_changed.unsubscribe(self._on_change)
        try:
            self._sock.close()
        except OSError:
            pass
