"""
MQTT transport -- publishes metrics to a broker.

"""
from __future__ import annotations

import logging

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTPublisher:
    def __init__(
        self,
        broker_host: str,
        broker_port: int,
        client_id: str,
        use_tls: bool = False,
        ca_cert: str = "",
        client_cert: str = "",
        client_key: str = "",
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.connected = False

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        if use_tls:
            self._client.tls_set(
                ca_certs=ca_cert,
                certfile=client_cert,
                keyfile=client_key,
            )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    def start(self) -> None:
        self._client.connect_async(self.broker_host, self.broker_port, keepalive=60)
        self._client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        #print(f"DEBUG _on_connect fired: reason_code={reason_code}")
        print(f"DEBUG _on_connect fired!")
        print(f"DEBUG broker: {self.broker_host}:{self.broker_port}")
        print(f"DEBUG reason_code: {reason_code}")
        self.connected = (reason_code == 0)
        if self.connected:
            logger.info("MQTT connected to %s:%s", self.broker_host, self.broker_port)
        else:
            logger.warning("MQTT connect failed: %s", reason_code)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self.connected = False
        logger.warning("MQTT disconnected (%s)", reason_code)

    def publish(self, topic: str, payload: dict) -> bool:
        if not self.connected:
            return False
        import json
        result = self._client.publish(topic, json.dumps(payload), qos=1)
        result.wait_for_publish(timeout=5)
        return result.is_published()

    def stop(self) -> None:
        try:
            self._client.disconnect()
        finally:
            self._client.loop_stop()