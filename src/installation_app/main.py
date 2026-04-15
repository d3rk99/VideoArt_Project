from __future__ import annotations

import argparse
from pathlib import Path

from installation_app.comfy_client import ComfyUIClient
from installation_app.config import ConfigError, load_config
from installation_app.controller import PipelineController
from installation_app.logging_utils import setup_logging
from installation_app.obs_client import OBSClient
from installation_app.remote_client import RemoteBridgeClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive installation pipeline")
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML file")
    parser.add_argument("--test-comfy", action="store_true", help="Test ComfyUI connection and exit")
    parser.add_argument("--test-obs", action="store_true", help="Test OBS connection and exit")
    parser.add_argument("--test-remote-bridge", action="store_true", help="Test remote bridge connectivity and exit")
    parser.add_argument("--run-bridge", action="store_true", help="Run the remote bridge server and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        config = load_config(Path(args.config))
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        return 2

    logger = setup_logging(config.app.debug_logging)

    if args.run_bridge:
        from installation_app.bridge.server import run_bridge_server  # Lazy import to avoid FastAPI dependency on laptop-only installs

        run_bridge_server(config, logger)
        return 0

    if args.test_remote_bridge:
        if not config.remote.enabled:
            print("Remote bridge test skipped: remote.enabled is false")
            return 0
        client = RemoteBridgeClient(config.remote, config.local_paths, logger)
        try:
            client.health_check()
            print("Remote bridge connectivity test: OK")
            return 0
        finally:
            client.close()

    if args.test_comfy:
        client = ComfyUIClient(config.comfyui)
        try:
            client.health_check()
            print("ComfyUI connectivity test: OK")
            return 0
        finally:
            client.shutdown()

    if args.test_obs:
        if not config.obs.enabled:
            print("OBS connectivity test skipped: obs.enabled is false")
            return 0

        client = OBSClient(config.obs)
        client.connect()
        client.health_check()
        print("OBS connectivity test: OK")
        client.disconnect()
        return 0

    controller = PipelineController(config, logger)
    try:
        controller.run()
        return 0
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Unhandled runtime error")
        print(f"Runtime error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
