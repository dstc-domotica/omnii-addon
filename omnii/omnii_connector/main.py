import time

from .config import load_config
from .constants import SUPERVISOR_TOKEN
from .grpc_client import OmniiGrpcClient


def main() -> None:
    print("Starting Omnii Server Connector add-on (gRPC) ...")

    if SUPERVISOR_TOKEN:
        print("SUPERVISOR_TOKEN is set")
    else:
        print("Warning: SUPERVISOR_TOKEN is not set - supervisor API calls will fail")

    config = load_config()

    client = OmniiGrpcClient(
        server_url=config["server_url"],
        enrollment_code=config["enrollment_code"],
    )

    if client.load_existing_enrollment():
        print("Found existing enrollment data. Skipping enrollment.")
    else:
        print("No existing enrollment found. Enrolling with server via gRPC...")
        if not client.enroll():
            print("Failed to enroll with server. Exiting.")
            raise SystemExit(1)

    if not client.connect_and_handshake():
        print("Failed to connect to gRPC server. Exiting.")
        raise SystemExit(1)

    client.start_heartbeat()

    print("Add-on is running (gRPC). Press Ctrl+C to stop.")
    try:
        while client.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nReceived interrupt signal")
    finally:
        client.stop()
        print("Add-on stopped.")


if __name__ == "__main__":
    main()

