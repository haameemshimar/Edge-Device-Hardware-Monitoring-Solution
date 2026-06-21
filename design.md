# Design document: edge hardware monitoring agent

## Architecture

A lightweight Python daemon runs alongside the device's computer vision
workload:

## collect (psutil + NVML) -> local SQLite buffer -> MQTT publish -> AWS IoT Core ##

It's a single long-running process (not cron), holding one persistent
MQTT connection rather than reconnecting every cycle. Each cycle: collects
CPU/RAM/disk/GPU/temperature, checks them against local alert thresholds,
appends to a rolling window for periodic Slack summaries, writes the
sample to a local buffer, then attempts to drain that buffer over MQTT.
Network I/O runs on the MQTT client's own background thread, so a slow or
dead connection never blocks the next collection cycle — verified
directly by killing the broker mid-run and confirming the agent kept
collecting without blocking or crashing.

## Why MQTT to AWS IoT Core

These devices are already managed via IoT Core/Greengrass, so per-device
X.509 identity already exists — reusing it means no new credential
management. MQTT is built for constrained, intermittently-connected
devices, unlike polling a REST API. Pub/sub also decouples the device
from any specific consumer: the IoT Rules Engine can fan one stream out
to CloudWatch, S3/Timestream, and Lambda/SNS without touching device
code. This isn't just a design intention — the agent authenticates with
a real per-device certificate over mutual TLS and publishes to a live
AWS IoT Core endpoint, confirmed via the console's MQTT test client.

## Trade-offs considered

- **SQLite buffer vs. in-memory queue**: survives a process restart,
  handles concurrent reads/writes safely with no extra service to run.
  Capped by age and row count so an outage can't fill the disk — logging
  follows the same philosophy via rotation (5MB × 3 backups), since an
  agent watching disk usage shouldn't be the thing that exhausts it.
- **`try/finally` for the loop and MQTT shutdown, `with` everywhere
  else**: finally guarantees the connection/buffer handle releases on
  any exit path; context managers give the same guarantee more concisely
  where the only resource is a lock or file handle.
- **Python vs. Go/Rust**: more memory and interpreter overhead, but
  matches the existing stack and is faster to review. Negligible cost
  next to a GPU-bound inference workload at a 30s poll interval.
- **No alert de-duplication**: every breach logs/notifies rather than
  suppressing repeats — simpler for a prototype; a fleet would want
  hysteresis to avoid alert fatigue.
- **Slack posted directly from the device**: simplest path to a working
  demo. At fleet scale this should move to a Lambda on the Rules Engine
  instead — one webhook credential instead of one per device.

## Scaling to thousands of devices

IoT Core scales the broker; that's not something this project builds.
Per-device topics (`edge/devices/{id}/metrics`) with per-device IoT
policies give least-privilege at scale — each device can publish to its
own topic only, nothing else. Routing logic lives centrally in the Rules
Engine, so firmware stays stable across the fleet; you change *where*
data goes without redeploying to every device. Greengrass's component
model would let the agent itself be versioned and rolled out fleet-wide.
At scale, payload size and frequency become real cost levers (IoT Core
bills per message) — reporting windowed avg/max rather than raw
per-cycle samples is the next optimization, not yet built here. For
local buffering specifically, a production fleet would likely use
Greengrass's built-in Stream Manager component rather than a hand-rolled
SQLite buffer — it solves the same problem with built-in retention and
priority policies, already running on every Greengrass-managed device.

## Security considerations

- **Auth**: per-device X.509 certificate (Greengrass-provisioned in
  production) — no shared secrets or API keys in code or config.
- **Least privilege**: IoT policy scopes each device's `iot:Publish` to
  one exact topic ARN, preventing spoofing or cross-device access.
- **Transport**: TLS for all MQTT traffic (port 8883, mutual TLS).
- **Local privilege**: the agent runs as an unprivileged systemd user —
  it only needs read access to `/proc`, `/sys`, and NVML, never root.
- **Secrets hygiene**: certs and the Slack webhook are excluded from
  version control and loaded from environment variables or an untracked
  config file; the private key's file permissions are locked to
  owner-only (`chmod 600`).
- **Data exposure**: hardware metrics aren't sensitive alone, but
  device ID/location metadata could fingerprint a client site, so
  access to fleet-wide queries downstream should be similarly scoped.