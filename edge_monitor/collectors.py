#!/usr/bin/env python3
"""
Filename: collectors.py
Description: Metric collectors (CPU, GPU, RAM Disk usage and temperature metrics)

Author: Haameem Shimar
Date: 2026-06-20
Assessment: Edge Device Hardware Monitoring Solution  

Design choice: every collector is wrapped in its own try/except and degrades
to None on failure rather than raising. A monitoring agent that crashes
because one sensor (e.g. NVML on a non-GPU box, or a flaky thermal zone)
misbehaved is worse than useless -- it stops reporting on everything else
too. Partial data beats no data.
"""
from __future__ import annotations

import logging
import os
import time

import psutil

logger = logging.getLogger(__name__)

try:
    import pynvml

    pynvml.nvmlInit()
    GPU_AVAILABLE = True
except Exception as exc:  #  any NVML failure means "no GPU metrics"
    GPU_AVAILABLE = False
    logger.info("GPU metrics unavailable (%s) -- continuing without them", exc)


def collect_cpu() -> dict:
    load_avg = None
    if hasattr(os, "getloadavg"):
        try:
            load_avg = os.getloadavg()[0]
        except OSError:
            load_avg = None
    return {
        "percent": psutil.cpu_percent(interval=None),
        "load_avg_1m": load_avg,
        "core_count": psutil.cpu_count(logical=True),
    }


def collect_memory() -> dict:
    vm = psutil.virtual_memory()
    return {
        "percent": vm.percent,
        "used_mb": round(vm.used / (1024 ** 2), 1),
        "total_mb": round(vm.total / (1024 ** 2), 1),
    }


def collect_disk(path: str = "/") -> dict | None:
    try:
        du = psutil.disk_usage(path)
        return {
            "percent": du.percent,
            "used_gb": round(du.used / (1024 ** 3), 2),
            "total_gb": round(du.total / (1024 ** 3), 2),
        }
    except OSError as exc:
        logger.warning("Disk metric collection failed: %s", exc)
        return None


def collect_gpu() -> dict | None:
    if not GPU_AVAILABLE:
        return None
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        return {
            "utilization_percent": util.gpu,
            "memory_percent": round(mem.used / mem.total * 100, 1),
            "memory_used_mb": round(mem.used / (1024 ** 2), 1),
            "memory_total_mb": round(mem.total / (1024 ** 2), 1),
            "temperature_c": temp,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("GPU metric collection failed: %s", exc)
        return None


def collect_temperature() -> dict | None:
    try:
        temps = psutil.sensors_temperatures()
    except AttributeError:
        return None  # not supported on this platform
    if not temps:
        return None
    for name, entries in temps.items():
        if entries:
            return {"sensor": name, "temperature_c": entries[0].current}
    return None

def disk_input_output() -> dict | None:
    try:
        counter = psutil.disk_io_counters()
        MB = 1024 ** 3
        return {"read_bytes" : round(counter.read_bytes/MB,1) , "write_bytes" : round(counter.write_bytes/MB,1)}
    except Exception as exc:
        return None


def collect_all(device_id: str) -> dict:
    return {
        "device_id": device_id,
        "timestamp": time.time(),
        "cpu": collect_cpu(),
        "memory": collect_memory(),
        "disk": collect_disk(),
        "gpu": collect_gpu(),
        "temperature": collect_temperature(),
        "read_write_bytes" : disk_input_output(),
    }
