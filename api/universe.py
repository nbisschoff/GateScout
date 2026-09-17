"""
ESI calls for system neighbours, kills, and jumps.
All public endpoints — no auth token needed.
"""

import requests
from config import ESI_BASE

_session = requests.Session()
_session.headers.update({"Accept": "application/json"})

_system_cache: dict[int, dict] = {}


def get_system_info(system_id: int) -> dict:
    """Returns system info (cached — security status never changes)."""
    if system_id not in _system_cache:
        r = _session.get(f"{ESI_BASE}/universe/systems/{system_id}/")
        r.raise_for_status()
        _system_cache[system_id] = r.json()
    return _system_cache[system_id]


def get_security_statuses(system_ids: list[int]) -> dict[int, float]:
    return {
        sid: round(get_system_info(sid).get("security_status", 0.0), 1)
        for sid in system_ids
    }


def get_neighbour_ids(system_id: int) -> list[int]:
    """Returns list of system_ids reachable in 1 jump via stargates."""
    info = get_system_info(system_id)
    gate_ids = info.get("stargates", [])
    neighbour_ids = []
    for gate_id in gate_ids:
        r = _session.get(f"{ESI_BASE}/universe/stargates/{gate_id}/")
        r.raise_for_status()
        dest = r.json().get("destination", {})
        dest_system = dest.get("system_id")
        if dest_system:
            neighbour_ids.append(dest_system)
    return neighbour_ids


def get_system_name(system_id: int) -> str:
    info = get_system_info(system_id)
    return info.get("name", str(system_id))


def get_names_bulk(ids: list[int]) -> dict[int, str]:
    """Resolve a list of system IDs to names in one ESI call."""
    if not ids:
        return {}
    r = _session.post(f"{ESI_BASE}/universe/names/", json=ids)
    r.raise_for_status()
    return {entry["id"]: entry["name"] for entry in r.json()}


def get_kills_and_jumps(system_ids: list[int]) -> dict[int, dict]:
    """
    Returns {system_id: {"ship_kills": int, "jumps": int}} for all requested systems.
    Both endpoints return data for all of New Eden, so we fetch once and filter.
    """
    kills_r = _session.get(f"{ESI_BASE}/universe/system_kills/")
    jumps_r = _session.get(f"{ESI_BASE}/universe/system_jumps/")
    kills_r.raise_for_status()
    jumps_r.raise_for_status()

    kills_map = {
        entry["system_id"]: entry.get("ship_kills", 0) + entry.get("pod_kills", 0)
        for entry in kills_r.json()
    }
    jumps_map = {entry["system_id"]: entry.get("ship_jumps", 0) for entry in jumps_r.json()}

    target = set(system_ids)
    return {
        sid: {
            "ship_kills": kills_map.get(sid, 0),
            "jumps": jumps_map.get(sid, 0),
        }
        for sid in target
    }
