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


def build_summary_text(device_id: str, window: list[dict]) -> str:
    cpu_vals = [m["cpu"]["percent"] for m in window]
    mem_vals = [m["memory"]["percent"] for m in window]

    cpu_avg = statistics.fmean(cpu_vals)
    cpu_max = max(cpu_vals)
    mem_avg = statistics.fmean(mem_vals)
    mem_max = max(mem_vals)

    return (
        f"Device {device_id} -- last {len(window)} samples -- "
        f"CPU avg {cpu_avg:.1f}% (max {cpu_max:.1f}%), "
        f"Memory avg {mem_avg:.1f}% (max {mem_max:.1f}%)"
    )
