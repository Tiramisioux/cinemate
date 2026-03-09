## CLI relay performance
If runtime logs feel jittery under heavy frame traffic (including per-frame Redis updates such as `framecount`), keep `cli_relay.mode` at `event` (default) or set it to `off`.

Use `frame` mode only when you need per-frame diagnostics, then reduce noise by raising `cli_relay.frame_sample_n` (for example `5` or `10`) and adding targeted `cli_relay.filters` tokens.
