"""
Kill detail fetching: zKillboard for the kill list, ESI for killmail positions.
"""

import math
import datetime
import requests

from config import ESI_BASE

_ZKB = "https://zkillboard.com/api"
_session = requests.Session()
_session.headers.update({
    "Accept": "application/json",
    "User-Agent": "GateScout/1.0 (EVE overlay; contact via EVE in-game)",
})


def get_kills_for_system(system_id: int) -> list[dict]:
    """
    Returns zKillboard kill stubs for the given system.
    We fetch recent kills without a time filter and let build_kill_rows
    do the hour-window filtering using the authoritative ESI killmail time.
    """
    r = _session.get(f"{_ZKB}/kills/solarSystemID/{system_id}/pastSeconds/7200/")
    r.raise_for_status()
    result = r.json()
    return result if isinstance(result, list) else []


def get_killmail_detail(kill_id: int, kill_hash: str) -> dict:
    r = _session.get(f"{ESI_BASE}/killmails/{kill_id}/{kill_hash}/")
    r.raise_for_status()
    return r.json()


def get_stargate_positions(system_id: int) -> list[dict]:
    """
    Returns [{"destination": "SystemName", "position": (x, y, z)}] for each gate.
    Used to calculate whether a kill happened near a gate.
    """
    from api.universe import get_system_info, get_names_bulk

    info = get_system_info(system_id)
    gate_ids = info.get("stargates", [])
    gates = []
    for gate_id in gate_ids:
        r = _session.get(f"{ESI_BASE}/universe/stargates/{gate_id}/")
        if r.status_code != 200:
            continue
        data = r.json()
        dest_system_id = data.get("destination", {}).get("system_id")
        pos = data.get("position", {})
        gates.append({
            "destination_id": dest_system_id,
            "position": (pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)),
        })

    dest_ids = [g["destination_id"] for g in gates if g["destination_id"]]
    names = get_names_bulk(dest_ids) if dest_ids else {}
    for g in gates:
        g["destination_name"] = names.get(g["destination_id"], "Unknown")

    return gates


def _distance_km(pos_a: tuple, pos_b: tuple) -> float:
    dx = pos_a[0] - pos_b[0]
    dy = pos_a[1] - pos_b[1]
    dz = pos_a[2] - pos_b[2]
    return math.sqrt(dx**2 + dy**2 + dz**2) / 1_000  # metres → km


def nearest_gate_label(kill_pos: tuple, gates: list[dict]) -> str:
    """
    Returns 'Near [System] gate' if within 1000 km of a gate, else 'Deep space'.
    """
    best_label = "Deep space"
    best_dist = float("inf")
    for gate in gates:
        dist = _distance_km(kill_pos, gate["position"])
        if dist < best_dist:
            best_dist = dist
            best_label = gate["destination_name"]
    if best_dist <= 1_000:
        return f"Near {best_label} gate  ({best_dist:.0f} km)"
    return f"Deep space  ({best_dist / 149_597_871:.2f} AU from nearest gate)"


def time_ago(killmail_time: str) -> str:
    """Converts ESI timestamp to '14m ago' style string."""
    try:
        t = datetime.datetime.strptime(killmail_time, "%Y-%m-%dT%H:%M:%SZ")
        t = t.replace(tzinfo=datetime.timezone.utc)
        delta = datetime.datetime.now(datetime.timezone.utc) - t
        mins = int(delta.total_seconds() // 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins}m ago"
        return f"{mins // 60}h {mins % 60}m ago"
    except Exception:
        return killmail_time


def build_kill_rows(system_id: int) -> list[dict]:
    """
    Full pipeline: fetch kills → fetch each killmail → classify location.
    Returns list of row dicts for the detail window table.
    """
    stubs = get_kills_for_system(system_id)
    if not stubs:
        return []

    gates = get_stargate_positions(system_id)

    # Fetch killmails and keep only those within the last hour.
    # zKillboard lags behind ESI so counts may not match — that's expected.
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
    killmails = []
    for stub in stubs:
        km = get_killmail_detail(stub["killmail_id"], stub["zkb"]["hash"])
        try:
            t = datetime.datetime.strptime(
                km["killmail_time"], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=datetime.timezone.utc)
            if t < cutoff:
                continue
        except Exception:
            pass
        killmails.append((stub, km))

    if not killmails:
        return []

    from api.universe import get_names_bulk

    # Collect all IDs to resolve in one bulk call
    ids_to_resolve = []
    for _, km in killmails:
        ids_to_resolve.append(km["victim"]["ship_type_id"])
        fb = next((a for a in km.get("attackers", []) if a.get("final_blow")), None)
        if fb:
            if fb.get("corporation_id"):
                ids_to_resolve.append(fb["corporation_id"])
            if fb.get("alliance_id"):
                ids_to_resolve.append(fb["alliance_id"])

    names = get_names_bulk(list(set(ids_to_resolve)))

    rows = []
    for stub, km in killmails:
        victim_pos_raw = km["victim"].get("position", {})
        victim_pos = (
            victim_pos_raw.get("x", 0),
            victim_pos_raw.get("y", 0),
            victim_pos_raw.get("z", 0),
        )
        ship_name = names.get(km["victim"]["ship_type_id"], "Unknown ship")
        location = nearest_gate_label(victim_pos, gates) if gates else "Unknown"

        fb = next((a for a in km.get("attackers", []) if a.get("final_blow")), None)
        attacker = "Unknown"
        if fb:
            corp = names.get(fb.get("corporation_id"), "")
            alliance = names.get(fb.get("alliance_id"), "")
            attacker = f"{corp} [{alliance}]" if alliance else corp or "Unknown"

        rows.append({
            "killmail_id": stub["killmail_id"],
            "zkb_hash": stub["zkb"]["hash"],
            "isk_value": stub["zkb"].get("totalValue", 0),
            "ship": ship_name,
            "ship_type_id": km["victim"]["ship_type_id"],
            "attacker": attacker,
            "time": time_ago(km["killmail_time"]),
            "location": location,
        })

    return rows


def format_isk(value: float) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} B ISK"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} M ISK"
    return f"{value / 1_000:.0f} K ISK"


def get_kill_summary_data(killmail_id: int, zkb_hash: str, isk_value: float) -> dict:
    """
    Returns structured data for the kill summary panel.
    Victim info, final blow attacker, and attackers grouped by corp.
    """
    from api.universe import get_names_bulk

    km = get_killmail_detail(killmail_id, zkb_hash)
    victim = km["victim"]
    attackers = km.get("attackers", [])

    # Collect all IDs to resolve in one bulk call
    ids = []
    for field in ("character_id", "corporation_id", "alliance_id"):
        if victim.get(field):
            ids.append(victim[field])

    fb = next((a for a in attackers if a.get("final_blow")), None)
    if fb:
        for field in ("character_id", "corporation_id", "alliance_id"):
            if fb.get(field):
                ids.append(fb[field])

    # Unique corps/alliances from all other attackers (no per-character lookups for fleets)
    for a in attackers:
        if not a.get("final_blow"):
            if a.get("corporation_id"):
                ids.append(a["corporation_id"])
            if a.get("alliance_id"):
                ids.append(a["alliance_id"])

    names = get_names_bulk(list(set(filter(None, ids))))

    victim_info = {
        "character_id": victim.get("character_id"),
        "name":     names.get(victim.get("character_id"), "Unknown Pilot"),
        "corp":     names.get(victim.get("corporation_id"), "Unknown Corp"),
        "alliance": names.get(victim.get("alliance_id"), ""),
        "ship_type_id": victim.get("ship_type_id"),
    }

    fb_info = None
    if fb:
        fb_info = {
            "name":     names.get(fb.get("character_id"), "Unknown"),
            "corp":     names.get(fb.get("corporation_id"), ""),
            "alliance": names.get(fb.get("alliance_id"), ""),
            "damage":   fb.get("damage_done", 0),
        }

    # Group non-final-blow attackers by corp, sorted by pilot count
    corp_map: dict[str, dict] = {}
    for a in attackers:
        if a.get("final_blow"):
            continue
        corp_name = names.get(a.get("corporation_id"), "Unknown")
        if corp_name not in corp_map:
            corp_map[corp_name] = {
                "alliance": names.get(a.get("alliance_id"), ""),
                "count": 0,
            }
        corp_map[corp_name]["count"] += 1

    other_attackers = sorted(
        [{"corp": k, "alliance": v["alliance"], "count": v["count"]}
         for k, v in corp_map.items()],
        key=lambda x: x["count"], reverse=True,
    )[:10]

    return {
        "killmail_id": killmail_id,
        "victim": victim_info,
        "isk_value": format_isk(isk_value),
        "total_attackers": len(attackers),
        "final_blow": fb_info,
        "other_attackers": other_attackers,
    }
