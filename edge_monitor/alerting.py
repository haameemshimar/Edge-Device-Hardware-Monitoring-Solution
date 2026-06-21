"""
Local alerting thresholds (stretch goal, level 1).


"""
from __future__ import annotations

from edge_monitor.config import Thresholds


def check_thresholds(metrics: dict, thresholds: Thresholds) -> list[str]:
    alerts: list[str] = []

    cpu_percent = metrics["cpu"]["percent"]
    if cpu_percent >= thresholds.cpu_percent:
        alerts.append(f"CPU usage high: {cpu_percent:.1f}% (threshold {thresholds.cpu_percent}%)")

    mem_percent = metrics["memory"]["percent"]
    if mem_percent >= thresholds.memory_percent:
        alerts.append(f"Memory usage high: {mem_percent:.1f}% (threshold {thresholds.memory_percent}%)")

    disk = metrics["disk"]
    if disk and disk["percent"] >= thresholds.disk_percent:
        alerts.append(f"Disk usage high: {disk['percent']:.1f}% (threshold {thresholds.disk_percent}%)")

    gpu = metrics["gpu"]
    if gpu:
        if gpu["utilization_percent"] >= thresholds.gpu_utilization_percent:
            alerts.append(
                f"GPU utilization high: {gpu['utilization_percent']}% "
                f"(threshold {thresholds.gpu_utilization_percent}%)"
            )
        if gpu["temperature_c"] >= thresholds.gpu_temperature_c:
            alerts.append(
                f"GPU temperature high: {gpu['temperature_c']}C "
                f"(threshold {thresholds.gpu_temperature_c}C)"
            )

    return alerts