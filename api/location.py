"""
Polls the character's current solar system via ESI (authenticated).
"""

import requests
from config import ESI_BASE


def get_current_system(character_id: int, access_token: str) -> int:
    """Returns the solar_system_id the character is currently in."""
    r = requests.get(
        f"{ESI_BASE}/characters/{character_id}/location/",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    r.raise_for_status()
    return r.json()["solar_system_id"]
