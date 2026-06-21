# Edge device hardware monitoring agent

A lightweight Python daemon that collects CPU, GPU, RAM, disk, and
temperature metrics on a Linux edge device and publishes them over MQTT
to AWS IoT Core, with local alerting and a periodic Slack summary on top.
See `design.md` for the architecture and reasoning behind the choices below.

## What's implemented

**Core**
- CPU, GPU, RAM, disk, and CPU/board temperature collection (`psutil` + NVML)
- Runs as a non-blocking periodic loop (`poll_interval_seconds`, configurable)
- Publishes over MQTT, with a local SQLite-backed buffer so metrics survive
  a network outage instead of being lost, and drain automatically once
  connectivity returns
- Tested against both a local Mosquitto broker (development) and a real
  AWS IoT Core endpoint with mutual TLS (production)

**Stretch goals**

Per the brief's guidance to pick 1-2 rather than attempt everything, I
implemented both **Level 1** items:

- **Local alerting thresholds** — logs a warning when CPU/GPU/RAM/disk
  cross a configurable limit (`edge_monitor/alerting.py`)
- **Periodic Slack summary** — posts aggregated stats (avg/max over the
  window) to a Slack channel via incoming webhook on a configurable
  interval (`edge_monitor/slack_notifier.py`)

**Level 3** (integrate with AWS IoT Core or Greengrass) is also covered,
not as separate extra work, but because the core data-transfer
implementation itself targets AWS IoT Core directly — the agent
authenticates with a per-device X.509 certificate over mutual TLS and
publishes real metrics to a live AWS IoT Core endpoint (verified via the
MQTT test client in the AWS console), going beyond "in your design" to
an actual working integration.

Level 2 (status UI, containerization) was deliberately not attempted, in
line with the brief's guidance not to attempt every stretch goal.

## Development environment

This was developed and tested inside **WSL2 running Ubuntu 22.04** on a
Windows machine, rather than native Windows — deliberately, since the
target deployment is Linux, and several things behave differently or
don't exist at all on Windows (`os.getloadavg()`, `psutil.sensors_
temperatures()`, systemd). Developing inside a real Ubuntu environment
meant the code path matched the target device exactly, rather than being
approximated and hoping it translates.

VS Code ran on the Windows side, connected to the WSL2 environment via
the **WSL extension** (Remote-WSL) — all file editing, the integrated
terminal, and the Python virtual environment lived inside Ubuntu, not on
the Windows filesystem. GPU testing used WSL2's NVIDIA GPU passthrough
(`nvidia-smi` and `pynvml` both work through it), which let the GPU
collector be verified against real hardware during development, even
though it's a different GPU than the target device's A4000 — the code
path itself is identical either way.

The one gap worth being upfront about: the systemd service file was
written but not live-tested, since WSL2 has no systemd. It would need
verification on an actual Ubuntu 22.04 install (or the target edge
device itself) before being trusted in production as-is.

## Prerequisites

- Linux (developed and tested on Ubuntu 22.04 via WSL2; target deployment
  is native Ubuntu 22.04 on the edge device)
- Python 3.10+
- NVIDIA driver + `nvidia-smi` for GPU metrics (optional — the agent
  degrades gracefully to `gpu: null` if no GPU/driver is present)

## Install

\`\`\`bash
sudo apt install -y python3 python3-venv python3-pip
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
\`\`\`

## Configure

\`\`\`bash
cp config/config.example.yaml config/config.yaml
\`\`\`

Edit `config/config.yaml` for your environment — at minimum, `device_id`
and the `mqtt` section (see below for local vs. AWS setup).

## Run it locally — no AWS account needed

\`\`\`bash
sudo apt install mosquitto mosquitto-clients
sudo systemctl start mosquitto   # or: mosquitto -d -p 1883

# Point config.yaml at the local broker: mqtt.broker_host: "localhost",
# mqtt.broker_port: 1883, mqtt.use_tls: false

# In one terminal:
mosquitto_sub -h localhost -t 'edge/devices/#' -v

# In another:
python3 main.py --config config/config.yaml
\`\`\`

You should see metrics arrive in the subscriber terminal every
`poll_interval_seconds`. Stop Mosquitto mid-run and the agent keeps
collecting without crashing — metrics queue up in `data/buffer.db` and
drain automatically once the broker comes back.

## Wiring up AWS IoT Core

This is free at prototype scale — AWS IoT Core's 12-month free tier
covers far more messages than a single demo device will use.

1. AWS IoT Core console → **Manage → All devices → Things → Create thing**
   → name it (e.g. `edge-device-001`) → auto-generate a certificate.
2. Attach a policy scoped to least privilege, e.g.:
   \`\`\`json
   {
     "Version": "2012-10-17",
     "Statement": [
       { "Effect": "Allow", "Action": ["iot:Connect"], "Resource": "*" },
       { "Effect": "Allow", "Action": ["iot:Publish"],
         "Resource": "arn:aws:iot:*:*:topic/edge/devices/edge-device-001/metrics" }
     ]
   }
   \`\`\`
3. Download the device certificate, private key, and Amazon Root CA 1
   (the root CA is account-independent — can also be fetched directly:
   `curl -o certs/AmazonRootCA1.pem https://www.amazontrust.com/repository/AmazonRootCA1.pem`).
4. Place all three in `certs/` using the filenames `config.yaml` expects:
   `device-cert.pem.crt`, `device-private.pem.key`, `AmazonRootCA1.pem`.
   Lock down the key: `chmod 600 certs/device-private.pem.key`.
5. Find your account's IoT data endpoint (console → Settings → Domain
   configurations), set it as `mqtt.broker_host` in `config.yaml`, with
   `broker_port: 8883` and `use_tls: true`.
6. Run the agent, and watch messages arrive live in **AWS IoT Core → MQTT
   test client**, subscribed to the device's exact topic (e.g.
   `edge/devices/edge-device-001/metrics`).

**Important:** `device_id` in `config.yaml` must exactly match the thing
name used when creating the IoT policy above — the policy's `iot:Publish`
permission is scoped to one specific topic ARN built from that name. A
mismatch doesn't break the connection itself (TLS auth succeeds
regardless), but every publish gets silently rejected as unauthorized.

## Slack summary setup (optional)

Create a Slack incoming webhook (api.slack.com/apps → your app →
Incoming Webhooks), then:

\`\`\`bash
export EDGE_MONITOR_SLACK_WEBHOOK="https://hooks.slack.com/services/..."
\`\`\`

and set `slack.enabled: true` in `config.yaml`. The URL is deliberately
read from an environment variable, not the config file, so it's never
committed to git.

## Logging

Logs go to both the console and a rotating file at `logs/edge-monitor.log`
(bounded by `log_max_bytes` / `log_backup_count`, default 5MB × 3 backups)
— same disk-bounding philosophy as the SQLite buffer, since this runs on
a disk-constrained edge device.

## Running as a systemd service

\`\`\`ini
[Unit]
Description=Edge device hardware monitoring agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/edge-monitor
ExecStart=/opt/edge-monitor/venv/bin/python3 /opt/edge-monitor/main.py --config /opt/edge-monitor/config/config.yaml
Restart=on-failure
RestartSec=5
User=edge-monitor
Group=edge-monitor
Nice=10

[Install]
WantedBy=multi-user.target
\`\`\`

Save as `/etc/systemd/system/edge-monitor.service` on the target device,
then `sudo systemctl daemon-reload && sudo systemctl enable --now edge-monitor`.
*Note: written but not live-tested in this environment — WSL2 has no
systemd, so this couldn't be exercised end-to-end during development.*

## Running tests / sanity checks

There's no formal test suite given the prototype scope, but each module
is small and pure enough to exercise directly, e.g.:

\`\`\`bash
python3 -c "from edge_monitor import collectors; import json; print(json.dumps(collectors.collect_all('test'), indent=2))"
\`\`\`

## Assumptions made

- Devices already have AWS IoT Core device identity provisioned (via
  Greengrass, in production) — this prototype's cert-loading mirrors that
  workflow rather than re-implementing fleet provisioning.
- A single NVIDIA GPU at index 0 (matches the stated A4000 hardware);
  multi-GPU would need a small extension.
- "Non-blocking" means the agent's own collection loop never blocks on
  network I/O — not full OS-level process isolation (cgroups, etc.).
- Metrics are sent as raw per-cycle samples, not pre-aggregated; the next
  optimization at fleet scale would be reporting windowed min/avg/max to
  cut bandwidth and per-message cost.
- Developed inside WSL2 (Ubuntu 22.04) rather than native Windows, so
  Linux-specific behavior (NVML, `/proc`-based metrics) matches the
  target edge device; some hardware sensors (board temperature) returned
  no data under WSL2's virtualization and would behave differently on
  bare-metal Ubuntu.

## AI assistant disclosure

I used Claude (Sonnet 4.6) throughout development, primarily as a
pair-programming tutor rather than a code generator. This was especially
true for the MQTT connection and publishing logic, where Claude explained
the underlying concepts — why MQTT connections are asynchronous, why
dataclasses need field(default_factory=...) instead of a bare default —
before I wrote the implementation myself. For a few pieces, including the
Slack summary aggregation and the rotating-file logging setup, I asked
for working code directly rather than writing it from scratch.

Everything in this repo was typed into my own environment, run, and
tested by me — every collector, the buffer, the MQTT publisher (against
both a local Mosquitto broker and a real AWS IoT Core endpoint), and the
agent loop were verified with real command output, not assumed working
from the code alone.

Several real issues came up during development that Claude identified
from my terminal output or screenshots — a working-directory mix-up that
scattered project files, an unsaved file that made a module appear empty,
and a GPU metrics key-naming mismatch between collect_gpu() and
downstream alerting code. In each case I understood the explanation,
verified it myself against the actual file/output, and applied the fix.
Separately, a topic-permission mismatch between device_id and the IoT
policy's topic ARN was caught and corrected before it ever caused a
real failure, while setting up AWS IoT Core.

All AWS IoT Core setup (Thing/certificate creation, IoT policy scoping,
endpoint configuration) and the Slack webhook integration were done
firsthand in my own AWS account and Slack workspace, with Claude guiding
the steps and explaining the security reasoning behind each one (e.g.
least-privilege topic scoping, why the root CA download is
account-independent).