import json
import os
from typing import Dict, Optional

from .constants import CREDENTIALS_PATH, DATA_DIR, ENROLLMENT_PATH


def ensure_data_dir() -> None:
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, mode=0o755)


def save_enrollment_data(enrollment_data: Dict) -> None:
    """Persist enrollment data to /data (credentials + enrollment metadata)."""
    ensure_data_dir()

    with open(CREDENTIALS_PATH, "w") as f:
        json.dump(
            {
                "instanceId": enrollment_data.get("instanceId"),
                "token": enrollment_data.get("token"),
            },
            f,
        )
    os.chmod(CREDENTIALS_PATH, 0o600)
    print(f"Saved credentials to {CREDENTIALS_PATH}")

    with open(ENROLLMENT_PATH, "w") as f:
        json.dump(
            {
                "instanceId": enrollment_data.get("instanceId"),
                "grpcServerUrl": enrollment_data.get("grpcServerUrl"),
            },
            f,
            indent=2,
        )
    os.chmod(ENROLLMENT_PATH, 0o644)
    print(f"Saved enrollment metadata to {ENROLLMENT_PATH}")


def load_enrollment_data() -> Optional[Dict]:
    """Load enrollment data from /data, or return None if missing/unreadable."""
    try:
        if not os.path.exists(CREDENTIALS_PATH) or not os.path.exists(ENROLLMENT_PATH):
            return None

        with open(ENROLLMENT_PATH, "r") as f:
            enrollment_metadata = json.load(f)
        with open(CREDENTIALS_PATH, "r") as f:
            credentials = json.load(f)

        enrollment_data = {
            **enrollment_metadata,
            "token": credentials.get("token"),
        }
        print(f"Loaded enrollment data for instance: {enrollment_data['instanceId']}")
        return enrollment_data
    except Exception as e:
        print(f"Error loading enrollment data: {e}")
        return None

