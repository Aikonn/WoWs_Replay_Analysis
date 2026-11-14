"""Exact post-battle numbers for every player, from the game's public results.

Found 2026-11-14 by comparing a summary with WoWs Toolkit: the timeline's
BattleResultsEvent (results.playersPublicInfo) holds the game's own
post-battle numbers for ALL 24 players, not only the recording player:
damage, received damage per weapon, spotting damage, potential damage,
life time, distance travelled, kills and more. Each value is a list in the
order of replays_unpack's CLIENT_PUBLIC_RESULTS
(replay_unpack/clients/wows/versions/<version>/constants.py; 550 names for
15.10.0, same length as the lists). Every entry has `account_db_id`, `name`
and `team_id`, so it maps to players by name or account id.

Verified on Shards (2026-11-13): every player's damage, spotting damage and
distance match WoWs Toolkit exactly; life_time_sec 694 for the recording
player = his death at 727.08 s recording time minus the battle start at
32.35 s (see combat.battle_start_s).

Received damage: the game stores some categories twice, as a parent key and
as its sub-type keys. Verified on Shards:
    received_damage_bomb   = bomb_avia + bomb_alt + bomb_airsupport
    received_damage_tbomb  = tbomb_avia + tbomb_alt + tbomb_airsupport
    received_damage_adbomb = dbomb_airsupport (ASW airstrike)
Probably also rocket = rocket_*, skip = skip_* (check on a replay with
rockets / skip bombs). replays_unpack sums ALL keys for its `total`, which
double-counts; WoWs Toolkit leaves out bomb and tbomb but still counts
adbomb twice (it shows 25,779 for Med_1024 where the true value is 19,998).
replays_unpack's by-type section also leaves out carrier bombs and
torpedo bombers (bomb_avia, tbomb_avia), so it can't be summed either.

Only complete replays have a BattleResultsEvent. Incomplete ones fall back
to the timeline (combat.py); every function here returns None then.
"""

from __future__ import annotations

import importlib
import logging
import re
from numbers import Real

from wows_replay_analysis.process.raw_loader import RawMatch

logger = logging.getLogger(__name__)

# Parent keys (suffix after "received_damage_") and the sub-type keys they
# duplicate. Leave parents out of every total. Extend when a check below
# finds another parent.
RECEIVED_PARENT_KEYS: dict[str, tuple[str, ...]] = {
    "bomb": ("bomb_avia", "bomb_alt", "bomb_airsupport"),
    "tbomb": ("tbomb_avia", "tbomb_alt", "tbomb_airsupport"),
    "adbomb": ("dbomb_airsupport",),
    "rocket": ("rocket_avia", "rocket_alt", "rocket_airsupport"),
    "skip": ("skip_avia", "skip_alt", "skip_airsupport"),
}


def public_results(raw: RawMatch) -> dict[str, dict] | None:
    """Return {player name: {field name: value}} for all players, or None.

    Read the last BattleResultsEvent of the timeline. Decode each list in
    results.playersPublicInfo with CLIENT_PUBLIC_RESULTS from the
    replays_unpack constants module that replays_unpack itself would pick
    for the game version (it tries "15_10_0_<build>" style names with 4
    parts first, then 3; see replay_unpack/clients/wows/player.py). If the
    list length doesn't match the names, log a warning and return None
    rather than mis-assign fields.
    """
    timeline = raw.timeline
    events = timeline.get("events") if isinstance(timeline, dict) else None
    if not isinstance(events, list):
        return None
    event = next(
        (
            item for item in reversed(events)
            if isinstance(item, dict) and item.get("event_type") == "BattleResultsEvent"
        ),
        None,
    )
    if event is None:
        return None
    results = event.get("results")
    public_info = results.get("playersPublicInfo") if isinstance(results, dict) else None
    if not isinstance(public_info, dict):
        logger.warning("Missing playersPublicInfo in %s BattleResultsEvent", raw.match_id)
        return None

    names = _client_public_results_names(raw)
    if names is None:
        return None
    decoded: dict[str, dict] = {}
    for account_id, values in public_info.items():
        if not isinstance(values, list) or len(values) != len(names):
            value_count = len(values) if isinstance(values, list) else "not a list"
            logger.warning(
                "Could not decode public results for account %s in %s: "
                "expected %d values, got %s",
                account_id,
                raw.match_id,
                len(names),
                value_count,
            )
            return None
        row = dict(zip(names, values))
        name = row.get("name")
        if not isinstance(name, str) or not name:
            logger.warning(
                "Public results for account %s in %s have no player name",
                account_id,
                raw.match_id,
            )
            return None
        decoded[name] = row
    return decoded


def _client_public_results_names(raw: RawMatch) -> tuple[str, ...] | None:
    """Load the field names from the constants for the replay's parser version."""
    versions = [
        raw.meta.get("game_version"),
        (
            raw.timeline.get("meta", {}).get("version")
            if isinstance(raw.timeline, dict)
            and isinstance(raw.timeline.get("meta"), dict)
            else None
        ),
    ]
    version = next((value for value in versions if isinstance(value, str)), None)
    parts = re.findall(r"\d+", version) if version is not None else []
    if len(parts) < 3:
        logger.warning("Cannot determine replays_unpack version for %s", raw.match_id)
        return None

    for part_count in (4, 3):
        if len(parts) < part_count:
            continue
        module_name = (
            "replay_unpack.clients.wows.versions."
            f"{'_'.join(parts[:part_count])}.constants"
        )
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name is None or not module_name.startswith(exc.name):
                raise
            continue
        names = getattr(module, "CLIENT_PUBLIC_RESULTS", None)
        if not isinstance(names, (list, tuple)) or not all(
            isinstance(name, str) for name in names
        ):
            logger.warning("No CLIENT_PUBLIC_RESULTS in %s", module_name)
            return None
        return tuple(names)

    logger.warning(
        "No replays_unpack constants found for game version %s in %s",
        version,
        raw.match_id,
    )
    return None


def received_damage_breakdown(row: dict) -> dict:
    """Return {"total": int, "<category>": int, ...} from one player's row.

    Categories: every non-zero `received_damage_<suffix>` key except the
    parents in RECEIVED_PARENT_KEYS, with the prefix removed (e.g.
    "main_he", "tpd_normal", "bomb_avia", "dbomb_airsupport", "fire").
    total = sum of the categories. Log a warning when a parent is not equal
    to the sum of its sub-types (the parent table would then be wrong).
    Shards, Med_1024: total 19,998.
    """
    for parent, subtypes in RECEIVED_PARENT_KEYS.items():
        parent_key = f"received_damage_{parent}"
        parent_value = row.get(parent_key)
        if not isinstance(parent_value, Real) or isinstance(parent_value, bool):
            continue
        subtype_total = sum(
            value
            for suffix in subtypes
            if isinstance(
                (value := row.get(f"received_damage_{suffix}")), Real
            )
            and not isinstance(value, bool)
        )
        if parent_value != subtype_total:
            logger.warning(
                "%s is %s but its sub-types sum to %s",
                parent_key,
                parent_value,
                subtype_total,
            )

    categories = {
        key.removeprefix("received_damage_"): value
        for key, value in row.items()
        if key.startswith("received_damage_")
        and key.removeprefix("received_damage_") not in RECEIVED_PARENT_KEYS
        and isinstance(value, Real)
        and not isinstance(value, bool)
        and value != 0
    }
    return {"total": sum(categories.values()), **categories}


def player_numbers(row: dict) -> dict:
    """Return the summary numbers for one player.

    {"damage": damage, "damage_received": received_damage_breakdown total,
     "spotting_damage": scouting_damage,
     "potential_damage": sum of all agro_* fields (check against the
        report's potential damage for the recording player and report the
        result in COPILOT_NOTES; WoWs Toolkit shows 285,230 for Med_1024),
     "frags": ships_killed, "life_time_s": life_time_sec,
     "distance_km": distance rounded to 0.01 (already km)}.
    """
    potential_damage = sum(
        value
        for key, value in row.items()
        if key.startswith("agro_")
        and isinstance(value, Real)
        and not isinstance(value, bool)
    )
    distance = row.get("distance")
    return {
        "damage": row.get("damage"),
        "damage_received": received_damage_breakdown(row)["total"],
        "spotting_damage": row.get("scouting_damage"),
        "potential_damage": potential_damage,
        "frags": row.get("ships_killed"),
        "life_time_s": row.get("life_time_sec"),
        # Two decimals retain the precision shown by WoWs Toolkit.
        "distance_km": round(distance, 2)
        if isinstance(distance, Real) and not isinstance(distance, bool)
        else None,
    }
