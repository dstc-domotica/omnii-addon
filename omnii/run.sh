#!/usr/bin/with-contenv bashio

# Run the Python add-on
export PYTHONPATH="/app/grpc_stubs:/app:${PYTHONPATH}"
python3 /omnii_addon.py