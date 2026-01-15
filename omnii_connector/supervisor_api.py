from typing import Dict, List, Optional

import requests

from .constants import SUPERVISOR_TOKEN, SUPERVISOR_URL


class SupervisorClient:
    def __init__(self):
        self._token = SUPERVISOR_TOKEN

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _get_data(self, path: str) -> Optional[Dict]:
        if not self._token:
            print("Warning: SUPERVISOR_TOKEN not set, skipping supervisor API call")
            return None

        try:
            response = requests.get(
                f"{SUPERVISOR_URL}{path}",
                headers=self._headers(),
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("result") == "ok":
                return data.get("data", {})

            print(f"Supervisor API error for {path}: {data.get('message', 'Unknown error')}")
            return None
        except requests.RequestException as e:
            print(f"Failed to fetch {path} from supervisor: {e}")
            return None

    def get_info(self) -> Optional[Dict]:
        """Fetch system info from Supervisor /info API."""
        return self._get_data("/info")

    def get_available_updates(self) -> List[Dict]:
        """Fetch available updates from Supervisor /available_updates API."""
        if not self._token:
            print("Warning: SUPERVISOR_TOKEN not set, skipping available updates")
            return []

        try:
            response = requests.get(
                f"{SUPERVISOR_URL}/available_updates",
                headers=self._headers(),
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("result") == "ok":
                return data.get("data", {}).get("available_updates", [])

            print(f"Available updates error: {data.get('message', 'Unknown error')}")
            return []
        except requests.RequestException as e:
            print(f"Failed to fetch available updates: {e}")
            return []

    def get_core_info(self) -> Optional[Dict]:
        """Fetch Home Assistant Core info from Supervisor /core/info API."""
        return self._get_data("/core/info")

    def get_os_info(self) -> Optional[Dict]:
        """Fetch OS info from Supervisor /os/info API."""
        return self._get_data("/os/info")

    def get_addons(self) -> List[Dict]:
        """Fetch add-on list from Supervisor /addons API."""
        data = self._get_data("/addons")
        if not data:
            return []
        return data.get("addons", [])

    def get_update_components(self) -> List[Dict]:
        """Fetch update status for core, supervisor, OS, and add-ons."""
        components: List[Dict] = []

        supervisor_info = self._get_data("/supervisor/info")
        if supervisor_info:
            components.append(
                {
                    "component_type": "supervisor",
                    "slug": "",
                    "name": "Supervisor",
                    "version": supervisor_info.get("version", ""),
                    "version_latest": supervisor_info.get("version_latest", ""),
                    "update_available": bool(supervisor_info.get("update_available")),
                }
            )

        core_info = self.get_core_info()
        if core_info:
            components.append(
                {
                    "component_type": "core",
                    "slug": "",
                    "name": "Home Assistant Core",
                    "version": core_info.get("version", ""),
                    "version_latest": core_info.get("version_latest", ""),
                    "update_available": bool(core_info.get("update_available")),
                }
            )

        os_info = self.get_os_info()
        if os_info:
            components.append(
                {
                    "component_type": "os",
                    "slug": "",
                    "name": "Home Assistant OS",
                    "version": os_info.get("version", ""),
                    "version_latest": os_info.get("version_latest", ""),
                    "update_available": bool(os_info.get("update_available")),
                }
            )

        for addon in self.get_addons():
            components.append(
                {
                    "component_type": "addon",
                    "slug": addon.get("slug", ""),
                    "name": addon.get("name", ""),
                    "version": addon.get("version", ""),
                    "version_latest": addon.get("version_latest", ""),
                    "update_available": bool(addon.get("update_available")),
                }
            )

        return components

    def reload_updates(self) -> bool:
        """Trigger reload of update information via Supervisor /reload_updates API."""
        if not self._token:
            print("Warning: SUPERVISOR_TOKEN not set, cannot reload updates")
            return False

        try:
            response = requests.post(
                f"{SUPERVISOR_URL}/reload_updates",
                headers=self._headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("result") == "ok"
        except requests.RequestException as e:
            print(f"Failed to reload updates: {e}")
            return False

    def trigger_update(self, update_type: str, addon_slug: str = "") -> Dict:
        """Trigger an update via Supervisor API.

        Args:
            update_type: One of 'core', 'os', 'supervisor', 'addon'
            addon_slug: Required if update_type is 'addon'

        Returns:
            Dict with 'success', 'error', and 'message' keys
        """
        if not self._token:
            return {
                "success": False,
                "error": "SUPERVISOR_TOKEN not set",
                "message": "",
            }

        try:
            if update_type == "core":
                url = f"{SUPERVISOR_URL}/core/update"
            elif update_type == "os":
                url = f"{SUPERVISOR_URL}/os/update"
            elif update_type == "supervisor":
                url = f"{SUPERVISOR_URL}/supervisor/update"
            elif update_type == "addon":
                if not addon_slug:
                    return {
                        "success": False,
                        "error": "addon_slug required for addon updates",
                        "message": "",
                    }
                url = f"{SUPERVISOR_URL}/addons/{addon_slug}/update"
            else:
                return {
                    "success": False,
                    "error": f"Unknown update type: {update_type}",
                    "message": "",
                }

            print(f"Triggering update: {update_type} (slug: {addon_slug or 'N/A'})")
            response = requests.post(
                url,
                headers=self._headers(),
                timeout=60,  # Updates can take a while
            )
            response.raise_for_status()
            data = response.json()

            if data.get("result") == "ok":
                return {
                    "success": True,
                    "error": "",
                    "message": f"Update triggered for {update_type}",
                }
            return {
                "success": False,
                "error": data.get("message", "Unknown error"),
                "message": "",
            }
        except requests.RequestException as e:
            return {"success": False, "error": str(e), "message": ""}

