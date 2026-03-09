
## CLI relay performance
If runtime logs feel jittery under heavy frame traffic (including per-frame Redis updates such as frame counters), keep `cli_relay.mode` at `event` (default) or set it to `off`. Use `frame` mode only when you need per-frame diagnostics.
If runtime logs feel jittery under heavy frame traffic, keep `cli_relay.mode` at `event` (default) or set it to `off`. Use `frame` mode only when you need per-frame diagnostics.
