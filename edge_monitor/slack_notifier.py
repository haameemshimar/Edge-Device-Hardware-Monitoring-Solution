"""
Periodic Slack summary notifier (stretch goal, level 1).
"""
from __future__ import annotations

import logging
import statistics

import requests

logger = logging.getLogger(__name__)


def send_slack_message(webhook_url: str, text: str) -> bool:
    if not webhook_url:
        return False
    try:
        resp = requests.post(webhook_url, json={"text": text}, timeout=5)
        return resp.status_code == 200
    except requests.RequestException as exc:
        logger.warning("Slack post failed: %s", exc)
        return False


def send_slack_alert(webhook_url: str, device_id: str, alerts: list[str]) -> bool:
    if not webhook_url or not alerts:
        return False

    alert_lines = "\n".join(f"• {alert}" for alert in alerts)
    text = f"⚠️ ALERT — {device_id}\n{alert_lines}"

    return send_slack_message(webhook_url, text)


def build_summary_text(device_id: str, window: list[dict]) -> str:
    cpu_vals = [m["cpu"]["percent"] for m in window]
    mem_vals = [m["memory"]["percent"] for m in window]
    read_vals = [m["read_write_bytes"]["read_bytes"] for m in window]

    cpu_avg = statistics.fmean(cpu_vals)
    cpu_max = max(cpu_vals)
    mem_avg = statistics.fmean(mem_vals)
    mem_max = max(mem_vals)
    read_avg = statistics.fmean(read_vals)
    read_max = max(read_vals)

    gpu_vals = [m["gpu"]["utilization_percent"] for m in window if m.get("gpu")]
    gpu_part = ""
    if gpu_vals:
        gpu_avg = statistics.fmean(gpu_vals)
        gpu_max = max(gpu_vals)
        gpu_part = f", GPU avg {gpu_avg:.1f}% (max {gpu_max:.1f}%)"

    return (
        f"Device {device_id} -- last {len(window)} samples -- "
        f"CPU avg {cpu_avg:.1f}% (max {cpu_max:.1f}%), "
        f"Memory avg {mem_avg:.1f}% (max {mem_max:.1f}%)"
        f"{gpu_part}"
        f"Read Byte avg {read_avg} (max {read_max})"
    )