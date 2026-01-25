import json
import os
import sys
from typing import Dict

from .constants import OPTIONS_PATH


def load_config() -> Dict:
    """Load configuration from Home Assistant options."""
    if not os.path.exists(OPTIONS_PATH):
        print(f"Configuration file not found at {OPTIONS_PATH}")
        sys.exit(1)
    try:
        with open(OPTIONS_PATH, "r") as f:
            config = json.load(f)
        required_fields = ["server_url", "enrollment_code"]
        missing_fields = [field for field in required_fields if not config.get(field)]
        if missing_fields:
            print(f"Missing required configuration fields: {', '.join(missing_fields)}")
            sys.exit(1)
        config.setdefault("grpc_tls_skip_verify", False)
        config.setdefault("grpc_tls_ca_cert", "")
        return config
    except Exception as e:
        print(f"Error loading configuration: {e}")
        sys.exit(1)

