"""
Agent loop -- ties collectors, buffer, and transport together
"""
from __future__ import annotations

import logging
import threading
import time

from edge_monitor import collectors
from edge_monitor.buffer import LocalBuffer
from edge_monitor.config import AppConfig
from edge_monitor.transport import MQTTPublisher
from edge_monitor.alerting import check_thresholds
from edge_monitor.slack_notifier import build_summary_text, send_slack_message
logger = logging.getLogger(__name__)


class Agent:
    def __init__(self, config: AppConfig):
        self.device_id = config.device_id
        self.poll_interval_seconds = config.poll_interval_seconds
        self.mqtt_topic = config.mqtt.topic.format(device_id=config.device_id)
        self.buffer = LocalBuffer(config.buffer_db_path)
        self.publisher = MQTTPublisher(
            config.mqtt.broker_host,
            config.mqtt.broker_port,
            client_id=config.device_id,
            use_tls=config.mqtt.use_tls,
            ca_cert=config.mqtt.ca_cert,
            client_cert=config.mqtt.client_cert,
            client_key=config.mqtt.client_key,
        )
        self._stop_event = threading.Event()
        self.thresholds = config.thresholds
        self.slack = config.slack
        self._slack_window: list[dict] = []
        self._last_slack_time = time.time()

    def run_cycle(self) -> None:
        metrics = collectors.collect_all(self.device_id)
        disk = metrics.get("disk")
        temp = metrics.get("temperature")
        disk_info = f" disk={disk['percent']:.1f}%" if disk else " disk=N/A"
        temp_info = f" temp={temp['temperature_c']:.1f}°C" if temp else " temp=N/A"
        logger.info(
            "Collected: cpu=%.1f%% mem=%.1f%%%s%s",
            metrics["cpu"]["percent"],
            metrics["memory"]["percent"],
            disk_info,
            temp_info,
        )

        self._slack_window.append(metrics)
        self._maybe_send_slack_summary()

        for alert in check_thresholds(metrics, self.thresholds):
            logger.warning("[ALERT] %s", alert)

        self.buffer.push(metrics)
        self._drain_buffer()

    def _drain_buffer(self, limit: int = 20) -> None:
        if not self.publisher.connected:
            logger.info("Not connected -- leaving %d row(s) buffered", self.buffer.size())
            return
        for row_id, payload in self.buffer.pop_batch(limit=limit):
            if self.publisher.publish(self.mqtt_topic, payload):
                self.buffer.delete([row_id])
            else:
                logger.warning(
                    "Publish failed for row %d -- stopping drain, will retry next cycle",
                    row_id,
                )
                break

    def start(self) -> None:
        self.publisher.start()
        logger.info(
            "Agent starting for device_id=%s, poll_interval=%ss",
            self.device_id,
            self.poll_interval_seconds,
        )
        try:
            while not self._stop_event.is_set():
                cycle_start = time.time()
                try:
                    self.run_cycle()
                except Exception:
                    logger.exception("Unhandled error in cycle -- continuing")
                elapsed = time.time() - cycle_start
                sleep_for = max(0.0, self.poll_interval_seconds - elapsed)
                self._stop_event.wait(sleep_for)
        finally:
            self.publisher.stop()
            self.buffer.close()
            logger.info("Agent stopped, resources released")

    def _maybe_send_slack_summary(self) -> None:
        if not self.slack.enabled:
            return
        elapsed = time.time() - self._last_slack_time
        if elapsed < self.slack.summary_interval_seconds:
            return
        if not self._slack_window:
            return

        text = build_summary_text(self.device_id, self._slack_window)
        if send_slack_message(self.slack.webhook_url, text):
            logger.info("Slack summary sent")
        else:
            logger.warning("Slack summary failed to send")

        self._slack_window = []
        self._last_slack_time = time.time()

    def stop(self) -> None:
        self._stop_event.set()