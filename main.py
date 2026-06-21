"""Entrypoint: python main.py [--config config/config.yaml]"""
from __future__ import annotations

import argparse
import logging
import signal
import sys

from edge_monitor.agent import Agent
from edge_monitor.config import load_config
from edge_monitor.logging_setup import setup_logging

def main() -> None:
    parser = argparse.ArgumentParser(description="Edge device hardware monitoring agent")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config YAML")
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(config)

    agent = Agent(config)

    def handle_signal(signum, frame):
        logging.info("Received signal %s -- shutting down", signum)
        agent.stop()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    agent.start()
    sys.exit(0)


if __name__ == "__main__":
    main()