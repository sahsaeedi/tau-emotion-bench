#!/usr/bin/env python3
import socket
import subprocess
import sys

from loguru import logger

HOST = "127.0.0.1"
PORT = 8001


def port_in_use(host: str, port: int) -> bool:
    """Return True if something is already listening on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((host, port)) == 0


def main():
    if port_in_use(HOST, PORT):
        logger.error(
            f"Port {PORT} is already in use. Stop the process listening on it "
            "and run `tau-emotion start` again."
        )
        sys.exit(1)

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "tau_emotion.api_service.simulation_service:app",
        "--host",
        HOST,
        "--port",
        str(PORT),
    ]
    logger.info(f"Starting Tau-Emotion server on http://{HOST}:{PORT} ...")
    process = subprocess.Popen(command)
    try:
        process.wait()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    finally:
        # Stop only the server this command started.
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
