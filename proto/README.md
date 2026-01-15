## Omnii gRPC services

`OmniiService` RPCs:

- `Enroll`: enrolls the add-on with an enrollment code and returns token + instance id.
- `Handshake`: authenticates and returns a session id for future calls.
- `Heartbeat`: keeps the session alive and can include optional system info.
- `ReportUpdates`: sends an update snapshot for supervisor/core/os/add-ons.
- `TriggerUpdate`: asks the add-on to trigger an update via Supervisor API.

Example update report:

```json
{
  "session_id": "abc123",
  "report": {
    "generated_at": 1736899200,
    "components": [
      {
        "component_type": "supervisor",
        "version": "2025.1.0",
        "version_latest": "2025.1.1",
        "update_available": true
      },
      {
        "component_type": "addon",
        "slug": "local_omnii-connector",
        "name": "Omnii Connector",
        "version": "1.0.0",
        "version_latest": "1.1.0",
        "update_available": true
      }
    ]
  }
}
```
