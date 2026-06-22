# Design document: Edge Hardware Monitoring Solution

## Architecture Overview

The system is built as a pipeline with one orchestrator and a set of independent modules. A single file, `agent.py`, calls everything in a fixed order, with five separate modules underneath it — each doing one job and unaware of the others. This design means every piece can be built and tested in isolation, without touching the rest of the system (e.g. using print statements to inspect what a specific function returns).

<img width="757" height="651" alt="image" src="https://github.com/user-attachments/assets/c9ff513b-b1f8-4259-9c17-bf05456824e2" />

## Module Breakdown

### `collectors.py` — Hardware Data Collection
Turns hardware state into plain numbers. Five small functions use `psutil` for CPU, RAM, and disk, and NVIDIA's `pynvml` for GPU. Every function is built to fail safely: if a sensor is missing or broken, that function returns `None` rather than crashing the pipeline.

### `config.py` + `config.yaml` — Configuration Layer
Acts as a consulting layer and rulebook. Before anything runs, this layer defines device ID, polling interval, alert thresholds, broker address, and whether Slack is enabled. Every other layer asks this layer "what should I do?" rather than having behaviour hardcoded into it. This is why no Python code needed to change when wiring up AWS.

### `agent.py` + `alerting.py` — Decision Making
Takes the numbers produced by collectors and compares them against the configuration thresholds to decide whether to log a warning, push to Slack, or do nothing.

### `buffer.py` — Local Safety Net
Metrics are never published directly. Every reading is written to a local SQLite buffer first before any network call is attempted. If the next layer becomes unreachable due to a network failure, data sits safely in the buffer instead of being lost — the buffer grows rather than dropping readings. This is where the application is most clearly decoupled to be fault-tolerant.

### `transport.py` — Message Publishing
Takes a reading and publishes it over MQTT, reporting back whether it succeeded. It has no knowledge of what is in the data or where it came from — it just moves bytes securely (TLS, certificates) to wherever the config file specifies.

### `main.py` + `agent.py` — Entry Point and Control Loop
`main.py` runs once at startup: loads config, sets up logging, and hands off control. `agent.py` then loops forever, executing the same fixed order every cycle:


---

## Data Transport: Why MQTT?

Several approaches were considered before choosing MQTT.

**REST API** — Posting metrics via API Gateway works for one device, but at scale every device continuously sends HTTP requests, resulting in higher network overhead, frequent TCP/TLS handshakes, and increased cost per call.

**S3** — Well suited for historical storage, but not real-time monitoring. At a 10-second polling interval, 1,000 devices would generate 6,000 file uploads per minute — a massive number of small files. MQTT can provide immediate delivery while data is still forwarded to S3 for long-term retention.

**Direct Database Writes** — Poor fit at scale due to excessive database connections. Connection pooling helps with connection management but does not solve security concerns on its own.

**Prometheus** — A strong option in controlled environments, but Prometheus recommends being on the same network as its targets. Edge devices at customer locations typically sit behind firewalls on customer building networks. With 100 devices across 100 different customer sites, making Prometheus reach out to each device becomes unrealistic. Its pull-based model requires solving network and firewall routing problems that a push-based MQTT model sidesteps entirely.

**MQTT (chosen approach)** — Native AWS IoT Core support means TLS certificate management is handled securely within the AWS environment at no extra cost. It is a proven protocol capable of handling millions of messages per day, covering the scalability requirement. Its publish/subscribe architecture naturally produces a decoupled, fault-tolerant solution.

Rather than building something new or picking the protocol that sounds most impressive on paper, MQTT was chosen because it plugs straight into a platform that already supports everything this system needs.

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

## Future Extensions

- **AWS Secrets Manager** — The Slack webhook URL is currently exported as part of the session. This can be moved to AWS Secrets Manager to avoid hardcoding sensitive credentials and manage them securely at scale.
- **CloudWatch Integration** — Metrics and logs can be forwarded to AWS CloudWatch for centralised monitoring, dashboards, and alerting across all devices without building custom tooling.
- **S3 Log Storage** — Collected metrics and logs can be pushed to S3 buckets for long-term retention, historical analysis, and potential integration with tools like Athena or QuickSight.
