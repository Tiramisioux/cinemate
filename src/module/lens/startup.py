"""Starting the lens adapter at boot: what ``main.run_application`` calls.

Split out of ``main.py`` (which imports the whole hardware stack and so cannot
be imported by a test) so the boot behaviour can be tested on a desk: what is
seeded, what is built from ``settings.jsonc``'s ``lens_control`` block, and that
the first probe happens before the thread starts.
"""
from __future__ import annotations

import logging

from module.lens.controller import LensController
from module.lens.database import LensDatabase
from module.redis_controller import ParameterKey

DEFAULT_POLL_HZ = 4.0
POLL_HZ_RANGE = (0.5, 20.0)


def seed_lens_defaults(redis_controller) -> None:
    """Give the two lens keys an operator-visible starting value on a fresh Redis.

    ``lens_control`` 0 (the toggle is off until the operator turns it on) and
    ``iris`` "" (nothing commanded yet: the lens cannot be read back). Only when
    absent -- both persist across restarts on purpose, so a warm Redis keeps the
    toggle and the last commanded f-number. ``af_mode`` is deliberately not
    seeded: ``manual`` written globally would switch off stock Camera Module 3
    autofocus (PLAN D21); only an AF-tuned launch sets it.
    """
    for key, default in ((ParameterKey.LENS_CONTROL, 0), (ParameterKey.IRIS, "")):
        if redis_controller.get_value(key.value) is None:
            redis_controller.set_value(key.value, default)


def start_lens_controller(settings, redis_controller, restart_camera=None, *,
                          backend_factory=None):
    """Build and start the Pinefeat CEF168 lens thread; return ``(controller, database)``.

    Called *before* cinepi-raw is launched: cinepi_multi reads the ``lens_*``
    keys while building each camera's arguments, so the adapter has to have
    answered (or been found absent) by then. One synchronous poll first, thread
    second, makes that true without a sleep. An absent adapter costs one INFO
    line and a slow probe loop, nothing else.

    ``restart_camera(reason)`` is only ever called by the autofocus layer
    (paused, ``lens_control.autofocus`` false), so main.py hands over a late-bound
    callable: the CinePiController does not exist yet. ``backend_factory`` is
    for tests; production leaves it None (see below).
    """
    lens_cfg = settings.get("lens_control") or {}
    database = LensDatabase(lens_cfg.get("database_file"))
    try:
        poll_hz = float(lens_cfg.get("poll_hz", DEFAULT_POLL_HZ))
        if not POLL_HZ_RANGE[0] <= poll_hz <= POLL_HZ_RANGE[1]:
            raise ValueError(poll_hz)
    except (TypeError, ValueError):
        logging.warning("lens_control.poll_hz %r is not between %g and %g; using %g",
                        lens_cfg.get("poll_hz"), *POLL_HZ_RANGE, DEFAULT_POLL_HZ)
        poll_hz = DEFAULT_POLL_HZ
    # No backend_factory: LensController's default is cef168.open_adapter(port,
    # cameras=...). Passing open_adapter itself would raise -- it takes `cameras`
    # as a keyword-only argument and the controller calls factory(port, cameras).
    controller = LensController(
        redis_controller,
        database=database,
        backend_factory=backend_factory,
        poll_hz=poll_hz,
        calibrate_on_selftest=lens_cfg.get("calibrate_on_selftest", True),
        autofocus_enabled=lens_cfg.get("autofocus") in (True, 1),
        request_camera_restart=restart_camera,
    )
    try:
        controller.poll_once()
    except Exception:
        logging.exception("First lens adapter probe failed; the lens thread will retry")
    controller.start()
    return controller, database
