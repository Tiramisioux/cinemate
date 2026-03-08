# Recording state-model migration (v1 → v2)

## Scope
This migration introduces a canonical runtime recording state model in Cinemate that is driven by `cp_stats` messages rather than per-frame stdout metadata.

## Signal layers

### Authoritative signals
- `cp_stats` fields from cinepi-raw, including timestamps and frame counters.
- Explicit queue and latency fields (when emitted):
  - `sensorTimestamp`
  - `encode_queue_size`
  - `disk_queue_size`
  - `ram_buffers`
  - `encode_latency_ms`
  - `disk_latency_ms`
  - `stats_seq`

### Derived signals
- GUI and CLI status values such as timecode presentation, buffering indicators, and sync summaries.

## State model feature flag
`settings.json` supports:

```json
"state_model": "v1" | "v2"
```

- `v1` remains the default rollback path during migration validation.
- `v2` enables `RecordingStateAggregator` as canonical state source for live recording state.

## v1 vs v2 behavior
- **v1**: direct ad-hoc `cp_stats` field reads in `RedisListener` and historic fallback patterns.
- **v2**: `RecordingStateAggregator` ingests `cp_stats` and exposes canonical snapshot fields to listener logic.

## Launch policy settings
New settings:

```json
"launch": {
  "rt_mode": "off" | "fifo",
  "rt_priority": 20,
  "cpu_affinity": "1-3"
}
```

- Default migration posture is `rt_mode=off`.
- `rt_mode=fifo` requires explicit opt-in and permissions.

## Recording profile mechanism

```json
"recording_profiles": {
  "active": "B",
  "profiles": {
    "A": {...},
    "B": {...},
    "C": {...},
    "custom": {...}
  }
}
```

Temporary baseline default remains **Profile B**:
- `encode_workers=2`
- `disk_workers=1`
- `encode_affinity=2-3`
- `disk_affinity=1`
- `encode_nice=-6`
- `disk_nice=-12`

## stdout metadata and relay controls
- stdout `DNG written:` parsing remains best-effort and is controlled by:

```json
"stdout_metadata": { "enabled": false }
```

- Raw stdout relay to Cinemate logs is independently controlled by:

```json
"stdout_relay": {
  "enabled": false,
  "level": "debug",
  "filters": []
}
```

- `stdout_metadata` and `stdout_relay` are intentionally independent.
- Core state/control behavior does not depend on per-frame stdout metadata or stdout relay.
- Cinemate can run with cinepi-raw stdout relay disabled; `cp_stats` remains authoritative.

## Analyzer CSV additions
Added columns:
- `cp_stats_seq`
- `cp_stats_seq_gap`
- `cp_stats_timestamp_gap`
- `encode_queue_size`
- `disk_queue_size`
- `ram_buffers`
- `encode_latency_ms`
- `disk_latency_ms`

Summary JSON includes:
- `stats_seq_gap_events`
- `timestamp_gap_events`

## 60-second validation workflow
1. Start runtime with migration baseline settings (`active=B`, `state_model=v2` for v2 validation).
2. Run:
   - `analyze s 60`
3. Check artifacts under `/media/RAW/_analysis/`:
   - `*_analyze.csv`
   - `*_summary.json`
4. Compare criteria:
   - No control regressions in start/stop/restart.
   - Low/acceptable `stats_seq_gap_events` and `timestamp_gap_events`.
   - Stable framecount progression and expected/recorded tolerance.
   - "Cinemate can run with cinepi-raw stdout relay fully disabled."

## Risk matrix (short)
- **Launch policy regression**: misconfigured `fifo` priority or affinity can reduce stability.
- **State-model regression**: v2 mapping gaps can affect derived UI status.
- **Analyzer schema drift**: consumers expecting old CSV headers may need update.

## Rollback checklist
1. Set `"state_model": "v1"`.
2. Set `"launch": {"rt_mode": "off" ...}` (or previous launch policy).
3. Keep `"recording_profiles": {"active": "B"}` for baseline.
4. Restart Cinemate service.
