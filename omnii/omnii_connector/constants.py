import os


DATA_DIR = "/data"
OPTIONS_PATH = os.path.join(DATA_DIR, "options.json")

CREDENTIALS_PATH = os.path.join(DATA_DIR, "credentials.json")
ENROLLMENT_PATH = os.path.join(DATA_DIR, "enrollment.json")

# Supervisor API configuration
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
SUPERVISOR_URL = "http://supervisor"

# Heartbeat interval (seconds)
HEARTBEAT_INTERVAL_SECONDS = 60

# Update reporting interval (seconds)
UPDATE_REPORT_INTERVAL_SECONDS = 3600
