#!/usr/bin/env python3
"""
Home Assistant Omnii Add-on
Connects Home Assistant to Omnii Server via gRPC
Provides system info and available updates to the server

Entrypoint wrapper:
The implementation lives in the `omnii_connector/` package (copied to /app in the image).
"""

from omnii_connector.main import main


if __name__ == "__main__":
    main()
