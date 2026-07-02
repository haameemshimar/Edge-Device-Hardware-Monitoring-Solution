"""
Health check HTTP endpoint.

Design choice: runs in a background daemon thread alongside the agent --
same pattern as paho-mqtt's loop_start(). Gives external systems (load
balancer, monitoring tool) a way to check agent status without touching
the main collection loop.
"""
from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)


def make_handler(agent):
    """
    Returns a handler class that has access to the agent via closure.
    
    Why a factory function? BaseHTTPRequestHandler instances are created
    by HTTPServer internally -- you can't pass extra arguments directly.
    The closure captures 'agent' so do_GET() can access it.
    """
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                # build response from agent's current state
                mqtt_connected = (
                    agent.publisher.connected
                    if agent.publisher
                    else False
                )
                response = {
                    "status": "ok",
                    "device_id": agent.device_id,
                    "mqtt_connected": mqtt_connected,
                    "buffer_size": agent.buffer.size(),
                    "poll_interval_seconds": agent.poll_interval_seconds,
                }
                body = json.dumps(response, indent=2).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            else:
                # any other path -- 404
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            # suppress default HTTP server access logs
            # keeps terminal clean during demo
            pass

    return HealthHandler


def start_health_server(agent, port: int = 8080) -> None:
    handler = make_handler(agent)
    server = HTTPServer(("", port), handler)
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True    # dies automatically when main program exits
    )
    thread.start()
    logger.info("Health check server started on http://localhost:%s/health", port)