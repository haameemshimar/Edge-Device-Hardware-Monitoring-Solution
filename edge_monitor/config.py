"""
Configuration loading.

Design choice: config lives in a YAML file (readable, easy to template per
device) but anything secret (Slack webhook URL, cert paths if non-default)
can be overridden via environment variables so secrets never need to be
committed to git. Env vars win over the YAML file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml


@dataclass
class Thresholds:
    cpu_percent: float = 90.0
    memory_percent: float = 90.0
    gpu_utilization_percent: float = 95.0
    gpu_temperature_c: float = 85.0
    disk_percent: float = 90.0


@dataclass
class MQTTConfig:
    enabled: bool = True
    broker_host: str = "localhost"
    broker_port: int = 1883
    use_tls: bool = False
    ca_cert: str = "certs/AmazonRootCA1.pem"
    client_cert: str = "certs/device-cert.pem.crt"
    client_key: str = "certs/device-private.pem.key"
    # {device_id} is substituted at publish time
    topic: str = "edge/devices/{device_id}/metrics"
    qos: int = 1


@dataclass
class SlackConfig:
    enabled: bool = False
    webhook_url: str = ""
    summary_interval_seconds: int = 300


@dataclass
class AppConfig:
    device_id: str = "edge-device-001"
    poll_interval_seconds: int = 30
    buffer_db_path: str = "./data/buffer.db"
    buffer_max_age_hours: int = 24
    buffer_max_rows: int = 20000
    log_level: str = "INFO"
    log_dir: str = "./logs"
    log_max_bytes: int = 5_000_000
    log_backup_count: int = 3
    thresholds: Thresholds = field(default_factory=Thresholds)
    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)


def _env_override(value, env_var):
    return os.environ.get(env_var, value)


def load_config(path: str = "config/config.yaml") -> AppConfig:
    raw = {}
    if os.path.exists(path):
        with open(path, "r") as f:
            raw = yaml.safe_load(f) or {}

    thresholds = Thresholds(**raw.get("thresholds", {}))
    mqtt_raw = raw.get("mqtt", {})
    mqtt = MQTTConfig(**mqtt_raw)
    slack_raw = raw.get("slack", {})
    slack = SlackConfig(**slack_raw)

    cfg = AppConfig(
        device_id=raw.get("device_id", "edge-device-001"),
        poll_interval_seconds=raw.get("poll_interval_seconds", 30),
        buffer_db_path=raw.get("buffer_db_path", "./data/buffer.db"),
        buffer_max_age_hours=raw.get("buffer_max_age_hours", 24),
        buffer_max_rows=raw.get("buffer_max_rows", 20000),
        log_level=raw.get("log_level", "INFO"),
        log_dir=raw.get("log_dir", "./logs"),
        log_max_bytes=raw.get("log_max_bytes", 5_000_000),
        log_backup_count=raw.get("log_backup_count", 3),
        thresholds=thresholds,
        mqtt=mqtt,
        slack=slack,
    )

    # Secrets / environment-specific values: env wins over file.
    cfg.device_id = _env_override(cfg.device_id, "EDGE_MONITOR_DEVICE_ID")
    cfg.mqtt.broker_host = _env_override(cfg.mqtt.broker_host, "EDGE_MONITOR_MQTT_HOST")
    cfg.slack.webhook_url = _env_override(cfg.slack.webhook_url, "EDGE_MONITOR_SLACK_WEBHOOK")

    return cfg
