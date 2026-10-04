"""Pinefeat CEF168 Canon EF lens adapter: iris, focus, calibration, lens database.

Nothing is imported here on purpose. ``database`` is standard library only (the
settings editor imports it with no camera and no Redis), ``cef168`` imports
``smbus2`` lazily, and ``controller`` pulls in the Redis key enum -- an eager
``__init__`` would make the lightest of them pay for the heaviest.

Design record: development/pinefeat-cef168/PLAN.md.
"""
