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

from wows_replay_analysis.process.raw_loader import RawMatch

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
    raise NotImplementedError


def received_damage_breakdown(row: dict) -> dict:
    """Return {"total": int, "<category>": int, ...} from one player's row.

    Categories: every non-zero `received_damage_<suffix>` key except the
    parents in RECEIVED_PARENT_KEYS, with the prefix removed (e.g.
    "main_he", "tpd_normal", "bomb_avia", "dbomb_airsupport", "fire").
    total = sum of the categories. Log a warning when a parent is not equal
    to the sum of its sub-types (the parent table would then be wrong).
    Shards, Med_1024: total 19,998.
    """
    raise NotImplementedError


def player_numbers(row: dict) -> dict:
    """Return the summary numbers for one player.

    {"damage": damage, "damage_received": received_damage_breakdown total,
     "spotting_damage": scouting_damage,
     "potential_damage": sum of all agro_* fields (check against the
        report's potential damage for the recording player and report the
        result in COPILOT_NOTES; WoWs Toolkit shows 285,230 for Med_1024),
     "frags": ships_killed, "life_time_s": life_time_sec,
     "distance_km": distance rounded to 0.1 (already km)}.
    """
    raise NotImplementedError
