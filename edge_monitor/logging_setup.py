"""
Logging setup -- console output plus a size-bounded rotating file.

"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from edge_monitor.config import AppConfig


def setup_logging(config: AppConfig) -> None:
    os.makedirs(config.log_dir, exist_ok=True)
    log_path = os.path.join(config.log_dir, "edge-monitor.log")

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=config.log_max_bytes,
        backupCount=config.log_backup_count,
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)

    logging.info("Logging to console and %s (max %s bytes x %s backups)",
                 log_path, config.log_max_bytes, config.log_backup_count)