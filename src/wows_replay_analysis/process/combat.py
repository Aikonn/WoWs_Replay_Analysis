"""Combat facts from the timeline: HP track, damage, healing, kills, distances.

Shared by match_summary.py (events, timeline samples) and stats.py
(timeline fallbacks for incomplete replays). Added 2026-11-14 after the first
AI discussion of a real summary (Shards, K type, processor_version 2) found
wrong numbers. Root causes, verified on that replay (times in this
docstring are recording time; battle time = recording time - 32.35 s):

1. damage_received.total was 5,781 too high. replays_unpack computes the
   section's `total` as the sum of ALL `received_damage_*` keys, and the game
   stores some damage twice (parent and sub-type keys, here `adbomb` and
   `dbomb_airsupport`, 5781 each). Fix: process/public_results.py, which
   leaves the parent keys out. (Damage dealt is fine: the parser takes the
   game's own `damage` value there.)
2. Damage windows missed 881.4 HP. The killing blow has no DamageEvent at
   all; the game sends only the death. The same is true for every kill, so
   all DamageEvent sums (mine dealt, others' damage_timeline) are too low by
   the victims' last HP. Fix: take my damage taken from the HP track (the
   own ship's `health` PropertyUpdateEvents, which do drop to 0 at death),
   and add killing_blows() to DamageEvent sums for damage dealt.
3. Healing: `health` rises in steps (15 x 66.5 HP from 612.6 s to 627.2 s
   = 997.5) and the own ship's `regeneratedHealth` property is the running
   healed total (ends at 997.5). DamageEvents never show heals.
4. Duplicate kills: the parser emits a DeathEvent for both
   Avatar.receiveVehicleDeath (entity_id = the recording player's avatar,
   real death_reason) and Vehicle.kill (entity_id = victim_id,
   death_reason 0). The second only exists when the victim's ship entity is
   loaded on the client, which is why far-away kills appear once.
5. Positions are BigWorld world units. 1 unit = 30 m (GameParams use the
   same unit, e.g. torpedo maxDist x 30 = metres; Shards positions span
   about +-600 units = 36 km). Report distances in km.
6. Times: timeline timestamps count from the start of the recording, which
   includes the 30 s countdown. The battle starts at 32.35 s on Shards
   (battle_start_s). The game's life_time_sec and WoWs Toolkit use battle
   time, so all times in summaries are battle time (battle_time()).

Verified per-hit reconciliation for that replay (DamageEvents to me plus the
killing blow, against the report's by-type numbers): MB HE 4192.65 (one
event per salvo), secondary HE 264 + 468.5 + 297 + 297 + 264 = 1590.5,
torpedoes 2501.73 + 832.13 = 3333.86, depth charges 2450 + 2450 + 881.37
(killing blow) = 5781.37, fire 20 x 180.5 = 3610, flood 25 x 59.565 = 1489.1.
DamageEvents carry the attacker but no weapon (damage_type "", ammo_id 0).
"""

from __future__ import annotations

import logging
import math
import re
from numbers import Real

logger = logging.getLogger(__name__)

# BigWorld world unit in metres (see point 5 above). Use world_to_km() for
# every distance in a summary; never print raw world-unit distances.
WORLD_UNIT_M = 30.0

# A tolerance in HP for the consistency checks (float rounding in events).
HP_TOLERANCE = 2.0


def world_to_km(units: float) -> float:
    """Convert a world-unit distance to km, rounded to 0.1 km."""
    distance_km = units * WORLD_UNIT_M / 1000
    return math.floor(distance_km * 10 + 0.5) / 10


def battle_start_s(timeline: dict | None) -> float | None:
    """Return the recording time when the battle starts (end of countdown).

    The BattleLogic entity's `timeLeft` property counts the 30 s countdown
    down to 0, then jumps to the battle length (1200) and `battleStage`
    becomes 0; that event's timestamp is the start (Shards: 32.35 s).
    None when not found.
    """
    if not isinstance(timeline, dict):
        return None
    events = timeline.get("events")
    if not isinstance(events, list):
        return None

    countdown_reached_zero = False
    for event in events:
        if not isinstance(event, dict) or event.get("entity_type") != "BattleLogic":
            continue
        value = event.get("value")
        if (
            event.get("property_name") == "timeLeft"
            and isinstance(value, Real)
            and not isinstance(value, bool)
            and value == 0
        ):
            countdown_reached_zero = True
        elif (
            countdown_reached_zero
            and event.get("property_name") == "timeLeft"
            and isinstance(value, Real)
            and not isinstance(value, bool)
            and value > 0
        ):
            timestamp = event.get("timestamp")
            if isinstance(timestamp, Real) and not isinstance(timestamp, bool):
                return float(timestamp)
        elif (
            countdown_reached_zero
            and event.get("property_name") == "battleStage"
            and event.get("value") == 0
        ):
            timestamp = event.get("timestamp")
            if isinstance(timestamp, Real) and not isinstance(timestamp, bool):
                return float(timestamp)
    return None


def battle_time(recording_s: float, start_s: float | None) -> float:
    """Convert a recording time to battle time (seconds since battle start),
    rounded to 0.1. Negative during the countdown; unchanged when start_s is
    None."""
    if start_s is None:
        return recording_s
    return round(recording_s - start_s, 1)


def health_track(timeline: dict | None, ship_id: int) -> list[tuple[float, float]]:
    """Return [(recording_time_s, hp)] from one ship's health updates.

    Start with (0.0, max_health) from timeline.players when the first update
    is later. Keep the order of the events; drop exact repeats of the same
    value. Empty list if the timeline has no health updates for the ship.
    """
    if not isinstance(timeline, dict):
        return []
    events = timeline.get("events")
    if not isinstance(events, list):
        return []

    max_health = None
    players = timeline.get("players")
    if isinstance(players, list):
        player = next(
            (
                item for item in players
                if isinstance(item, dict)
                and _integer_id(item.get("entity_id")) == ship_id
            ),
            None,
        )
        if player is not None:
            max_health = _number(player.get("max_health"))

    track: list[tuple[float, float]] = []
    for event in events:
        if (
            not isinstance(event, dict)
            or event.get("event_type") != "PropertyUpdateEvent"
            or _integer_id(event.get("entity_id")) != ship_id
            or event.get("property_name") != "health"
        ):
            continue
        timestamp = _number(event.get("timestamp"))
        health = _number(event.get("value"))
        if timestamp is None or health is None:
            continue
        if not track and timestamp > 0 and max_health is not None:
            track.append((0.0, max_health))
        if not track or track[-1][1] != health:
            track.append((timestamp, health))
    return track


def deduplicate_deaths(events: list[dict]) -> list[dict]:
    """Return the DeathEvents with exactly one per victim_id.

    When a victim has two events (see point 4 above), keep the one whose
    entity_id differs from victim_id (the Avatar one, with the real
    death_reason). Keep the original order. Use this everywhere deaths are
    read: kill events, frags, time of death, alive checks.
    """
    if not isinstance(events, list):
        return []
    result: list[dict] = []
    positions: dict[int, int] = {}
    for event in events:
        if not isinstance(event, dict) or event.get("event_type") != "DeathEvent":
            continue
        victim_id = _death_victim_id(event)
        if victim_id is None:
            continue
        position = positions.get(victim_id)
        if position is None:
            positions[victim_id] = len(result)
            result.append(event)
            continue

        current = result[position]
        current_entity = _integer_id(current.get("entity_id"))
        candidate_entity = _integer_id(event.get("entity_id"))
        current_is_avatar = current_entity is not None and current_entity != victim_id
        candidate_is_avatar = (
            candidate_entity is not None and candidate_entity != victim_id
        )
        if candidate_is_avatar and not current_is_avatar:
            result[position] = event
    return result


def killing_blows(timeline: dict | None) -> list[dict]:
    """Return the damage of every killing blow, which has no DamageEvent.

    For each deduplicated death: {"time_s", "victim_id", "killer_id",
    "damage"}. The fatal hit and hits in the same instant have no
    DamageEvent, and DamageEvents don't line up one-to-one with HP drops
    (one event can cover several drops, timestamps differ by up to ~0.5 s),
    so don't match drops to events. Rule (window W = 1.0 s before the death):
        damage = max(0, HP_before - sum of all DamageEvents on the victim
                     with death - W <= timestamp <= death)
    where HP_before = the victim's last track value before death - W.
    Freshness: the victim must have at least one HP update inside the
    window; otherwise its HP is stale (ship out of the client's range) and
    the blow is unknown: skip it and count it (DEBUG log). No fallback.
    Checked on the real data (2026-11-14, my damage = my DamageEvents +
    my killing blows, against the report): Shards 79,302.9 + 1,298.6 =
    80,601.5 of 81,673 (-1.3 %); OC_prey 36,287.4 + 8,289.5 (Warzeimer,
    HP 8383.5 -> 341.1 -> 0 in one tick) + 0 (JaGGa_Man) = 44,576.8 of
    44,715 (-0.3 %). Libertad: Nile666_ (last HP 22.7 s old) and Xieres87
    (146 s old) are skipped; the old last-HP rule gave BUCA_72teava_1
    27,026 damage he never did.
    Skip deaths where the victim's HP is unknown or the killer is the victim
    itself (e.g. flooding with no attacker); log those at DEBUG.
    """
    if not isinstance(timeline, dict):
        return []
    events = timeline.get("events")
    if not isinstance(events, list):
        return []

    tracks: dict[int, list[tuple[float, float]]] = {}
    health_updates: dict[int, list[float]] = {}
    damage_events: dict[int, list[tuple[float, float]]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        timestamp = _number(event.get("timestamp"))
        if timestamp is None:
            continue
        if (
            event.get("event_type") == "PropertyUpdateEvent"
            and event.get("property_name") == "health"
        ):
            victim_id = _integer_id(event.get("entity_id"))
            if victim_id is not None and _number(event.get("value")) is not None:
                health_updates.setdefault(victim_id, []).append(timestamp)
        elif event.get("event_type") == "DamageEvent":
            victim_id = _integer_id(event.get("target_id"))
            damage = _number(event.get("damage"))
            if victim_id is not None and damage is not None:
                damage_events.setdefault(victim_id, []).append((timestamp, damage))

    blows: list[dict] = []
    for death in deduplicate_deaths(events):
        victim_id = _death_victim_id(death)
        killer_id = _integer_id(death.get("killer_id"))
        if (
            victim_id is None
            or killer_id is None
            or killer_id == 0
            or killer_id == victim_id
        ):
            logger.debug("Skipping killing blow with unknown or self killer: %r", death)
            continue
        timestamp = _number(death.get("timestamp"))
        if timestamp is None:
            logger.debug("Skipping killing blow with unknown death time: %r", death)
            continue
        window_start = timestamp - 1.0
        if not any(
            window_start <= update_time <= timestamp
            for update_time in health_updates.get(victim_id, [])
        ):
            logger.debug("Skipping killing blow with stale victim HP: %r", death)
            continue

        track = tracks.setdefault(victim_id, health_track(timeline, victim_id))
        health_before = _health_before(track, window_start)
        if health_before is None:
            logger.debug("Skipping killing blow with unknown victim HP: %r", death)
            continue
        damage_in_window = sum(
            damage
            for damage_time, damage in damage_events.get(victim_id, [])
            if window_start <= damage_time <= timestamp
        )
        blows.append({
            "time_s": timestamp,
            "victim_id": victim_id,
            "killer_id": killer_id,
            "damage": round(max(0.0, health_before - damage_in_window), 1),
        })
    return blows


def damage_dealt_by_ship(timeline: dict | None) -> dict[int, float]:
    """Return {attacker ship id: damage} from DamageEvents plus killing_blows().

    Replaces match_summary._damage_by_ship. Rounded to 0.1. DamageEvents
    with attacker_id 0 are not attributed (report them in COPILOT_NOTES if
    they are a large share).
    """
    if not isinstance(timeline, dict):
        return {}
    events = timeline.get("events")
    if not isinstance(events, list):
        return {}

    totals: dict[int, float] = {}
    for event in events:
        if not isinstance(event, dict) or event.get("event_type") != "DamageEvent":
            continue
        attacker_id = _integer_id(event.get("attacker_id"))
        damage = _number(event.get("damage"))
        if attacker_id is not None and attacker_id != 0 and damage is not None:
            totals[attacker_id] = totals.get(attacker_id, 0.0) + damage
    for blow in killing_blows(timeline):
        killer_id = blow["killer_id"]
        totals[killer_id] = totals.get(killer_id, 0.0) + blow["damage"]
    return {ship_id: round(damage, 1) for ship_id, damage in totals.items()}


def damage_windows(
    timeline: dict | None,
    ship_id: int,
    end_s: float | None,
    window_s: int = 30,
) -> list[dict]:
    """Return battle-time damage windows for the recording player.

    One dict per window that has any damage or healing:
    {"start_s", "end_s", "damage_dealt", "damage_taken", "healed"}.
    `end_s` is the recorded or battle duration in battle seconds.
    - damage_taken / healed: the sum of HP drops / rises in health_track()
      inside the window (this includes the killing blow).
    - damage_dealt: my DamageEvents plus my killing_blows() in the window.
    - Death: the window that contains it is split at the time of death
      (rounded to 0.1). Everything up to the death stays in the first part.
      Damage I deal after my death (torpedoes still running, flooding I
      caused) goes into the second part and the following windows as usual,
      with damage_taken 0, healed 0 and "after_death": true. Never drop it:
      the report counts it (Shards: 13,901 after death, torpedo hit at
      710.0 s plus flood ticks). `end_s` caps the last window.
    Checks (see check_damage_consistency): sum(damage_taken) - sum(healed)
    == max_health - final HP.
    """
    if (
        not isinstance(timeline, dict)
        or isinstance(window_s, bool)
        or not isinstance(window_s, int)
        or window_s <= 0
    ):
        return []
    events = timeline.get("events")
    if not isinstance(events, list):
        return []

    start_s = battle_start_s(timeline)
    death_s = next(
        (
            battle_time(timestamp, start_s)
            for death in deduplicate_deaths(events)
            if _death_victim_id(death) == ship_id
            and (timestamp := _number(death.get("timestamp"))) is not None
        ),
        None,
    )
    by_window: dict[tuple[int, bool], dict[str, float]] = {}

    def window_index(timestamp: float, after_death: bool) -> int:
        if (
            not after_death
            and death_s is not None
            and timestamp == death_s
            and timestamp > 0
            and timestamp % window_s == 0
        ):
            return int(timestamp // window_s) - 1
        return int(timestamp // window_s)

    limit = _number(end_s)
    if limit is None:
        limit = max(
            (
                battle_time(timestamp, start_s)
                for event in events
                if isinstance(event, dict)
                and (timestamp := _number(event.get("timestamp"))) is not None
            ),
            default=0.0,
        )

    def add(timestamp: float, key: str, amount: float) -> None:
        battle_timestamp = battle_time(timestamp, start_s)
        if battle_timestamp < 0 or battle_timestamp > limit:
            return
        after_death = death_s is not None and battle_timestamp > death_s
        if after_death and key != "damage_dealt":
            return
        index = window_index(battle_timestamp, after_death)
        if index < 0:
            return
        window_key = (index, after_death)
        totals = by_window.setdefault(
            window_key, {"damage_dealt": 0.0, "damage_taken": 0.0, "healed": 0.0}
        )
        totals[key] += amount

    track = health_track(timeline, ship_id)
    for previous, current in zip(track, track[1:]):
        delta = current[1] - previous[1]
        if delta < 0:
            add(current[0], "damage_taken", -delta)
        elif delta > 0:
            add(current[0], "healed", delta)

    for event in events:
        if not isinstance(event, dict) or event.get("event_type") != "DamageEvent":
            continue
        if _integer_id(event.get("attacker_id")) != ship_id:
            continue
        timestamp = _number(event.get("timestamp"))
        damage = _number(event.get("damage"))
        if timestamp is not None and damage is not None:
            add(timestamp, "damage_dealt", damage)

    for blow in killing_blows(timeline):
        if blow["killer_id"] == ship_id and blow["time_s"] is not None:
            add(blow["time_s"], "damage_dealt", blow["damage"])

    windows: list[dict] = []
    for index, after_death in sorted(by_window):
        totals = by_window[(index, after_death)]
        if not any(totals.values()):
            continue
        window_start = index * window_s
        window_end = min(window_start + window_s, limit)
        if after_death and death_s is not None:
            window_start = max(window_start, death_s)
        elif death_s is not None:
            window_end = min(window_end, death_s)
        if window_end < window_start:
            continue
        window = {
            "start_s": round(window_start, 1),
            "end_s": round(window_end, 1),
            **{key: round(value, 1) for key, value in totals.items()},
        }
        if after_death:
            window["after_death"] = True
        windows.append(window)
    return windows


def healing_received(timeline: dict | None, ship_id: int) -> dict | None:
    """Return {"total", "events": [{"start_s", "end_s", "amount"}]} or None.

    Events: group consecutive HP rises in health_track() that are at most
    2.5 s apart into one heal (start of first rise, time of last rise, sum).
    total: the last value of the ship's `regeneratedHealth` property when
    present, else the sum of the events; log a warning if the two differ by
    more than HP_TOLERANCE. None when there was no healing.
    Shards replay: total 997.5, one event 613.2-627.2 s.
    """
    if not isinstance(timeline, dict):
        return None
    track = health_track(timeline, ship_id)
    events: list[dict] = []
    current: dict | None = None
    for previous, point in zip(track, track[1:]):
        amount = point[1] - previous[1]
        if amount <= 0:
            if current is not None:
                events.append(current)
                current = None
            continue
        timestamp = point[0]
        if current is not None and timestamp - current["end_s"] <= 2.5:
            current["end_s"] = timestamp
            current["amount"] += amount
        else:
            if current is not None:
                events.append(current)
            current = {
                "start_s": timestamp,
                "end_s": timestamp,
                "amount": amount,
            }
    if current is not None:
        events.append(current)
    for event in events:
        event["amount"] = round(event["amount"], 1)

    timeline_events = timeline.get("events")
    regenerated_total = None
    if isinstance(timeline_events, list):
        for event in timeline_events:
            if (
                isinstance(event, dict)
                and _integer_id(event.get("entity_id")) == ship_id
                and event.get("property_name") == "regeneratedHealth"
            ):
                value = _number(event.get("value"))
                if value is not None:
                    regenerated_total = value
    event_total = sum(event["amount"] for event in events)
    if regenerated_total is not None and abs(regenerated_total - event_total) > HP_TOLERANCE:
        logger.warning(
            "Healing HP rises (%s) differ from regeneratedHealth (%s) for ship %s",
            round(event_total, 1),
            round(regenerated_total, 1),
            ship_id,
        )
    total = regenerated_total if regenerated_total is not None else event_total
    if total <= 0 and not events:
        return None
    return {
        "total": round(total, 1),
        "events": events,
    }


def damage_received_events(
    timeline: dict | None,
    ship_id: int,
    players_by_id: dict[int, dict],
    death_info: dict | None = None,
    projectile_types: dict[int, str] | None = None,
    by_type: dict | None = None,
) -> list[dict]:
    """Return who hit me, when and how hard, compact enough for the summary.

    Source: DamageEvents with target_id == ship_id, plus my own killing blow
    (from killing_blows(), weapon from the report's death_info "name", e.g.
    "ADBOMB"). Merge runs of events from the same attacker with the same
    amount (to 0.1) less than 2.5 s apart into one entry with a hit count;
    fire and flooding ticks become one entry each that way.
    Entry: {"start_s", "end_s", "attacker": {"player", "ship"},
    "weapon", "hits", "damage"}; end_s only when hits > 1. Leave out
    entries with 0 damage. Run the list through reconcile_with_report()
    last, using exact public-results damage_received_by_type when available.
    projectile_types: {GameParams id: "HE"/"AP"/"CS"} built from gamedata
    projectiles.json (accepted proposal, 0d review); optional, so the function
    still works without gamedata.

    weapon: one of "main_he", "main_ap", "secondary_he", "secondary_ap",
    "torpedo", "depth_charge_airstrike", "bomb_airstrike", "fire", "flood",
    "ram" or "unknown". DamageEvents have no weapon (damage_type "", ammo_id
    0), so classify_hit() derives it from timeline evidence and the optional
    GAMEPARAMS_ID-to-ammo-type lookup. Unresolved weapons remain "unknown".
    """
    events = timeline.get("events") if isinstance(timeline, dict) else None
    if not isinstance(events, list):
        return []

    start_s = battle_start_s(timeline)
    runs: list[list[dict]] = []
    runs_by_key: dict[tuple[int | None, float], list[dict]] = {}
    damage_events = sorted(
        (
            event for event in events
            if isinstance(event, dict)
            and event.get("event_type") == "DamageEvent"
            and _integer_id(event.get("target_id")) == ship_id
            and _number(event.get("timestamp")) is not None
            and _number(event.get("damage")) is not None
        ),
        key=lambda event: _number(event.get("timestamp")) or 0.0,
    )
    for event in damage_events:
        timestamp = _number(event.get("timestamp"))
        damage = _number(event.get("damage"))
        if timestamp is None or damage is None:
            continue
        attacker_id = _integer_id(event.get("attacker_id"))
        key = (attacker_id, round(damage, 1))
        run = runs_by_key.get(key)
        previous_time = _number(run[-1].get("timestamp")) if run else None
        if run is None or previous_time is None or timestamp - previous_time >= 2.5:
            run = []
            runs.append(run)
            runs_by_key[key] = run
        run.append(event)

    received: list[dict] = []
    for run in runs:
        first = run[0]
        first_time = _number(first.get("timestamp"))
        amounts = [_number(event.get("damage")) for event in run]
        last_time = _number(run[-1].get("timestamp"))
        if (
            first_time is None
            or last_time is None
            or any(amount is None or amount <= 0 for amount in amounts)
        ):
            continue
        attacker_id = _integer_id(first.get("attacker_id"))
        received.append({
            "start_s": battle_time(first_time, start_s),
            **({"end_s": battle_time(last_time, start_s)} if len(run) > 1 else {}),
            "attacker": _damage_player_reference(
                players_by_id.get(attacker_id) if attacker_id is not None else None
            ),
            "weapon": classify_hit(
                timeline, first, len(run), projectile_types
            ),
            "hits": len(run),
            "damage": round(sum(amount for amount in amounts if amount is not None), 1),
        })

    for blow in killing_blows(timeline):
        if blow["victim_id"] != ship_id:
            continue
        death_time = _number(blow.get("time_s"))
        blow_damage = _number(blow.get("damage"))
        if death_time is None or blow_damage is None or blow_damage <= 0:
            continue
        killer_id = _integer_id(blow.get("killer_id"))
        received.append({
            "start_s": battle_time(death_time, start_s),
            "attacker": _damage_player_reference(
                players_by_id.get(killer_id) if killer_id is not None else None
            ),
            "weapon": _death_info_weapon(death_info),
            "hits": 1,
            "damage": round(blow_damage, 1),
        })

    received.sort(key=lambda event: event["start_s"])
    return reconcile_with_report(received, by_type)


def classify_hit(
    timeline: dict,
    event: dict,
    run_length: int,
    projectile_types: dict[int, str] | None = None,
) -> str:
    """Return the weapon of one DamageEvent to me (values: see above).

    Use matching torpedo/projectile events and the closest per-weapon damage
    stat update. A projectile's ammo type comes from the optional
    GAMEPARAMS_ID lookup; gun class comes from its fire event or damage stat.
    A periodic run requires at least three small hits spaced 0.9-1.4 seconds
    apart. It is fire only while burning is recorded, or flood when it follows
    the same attacker's torpedo or depth-charge hit.

    Corrections from the 0d review (2026-11-15), OC_prey: two 1,785 hits from
    the same attacker 2.3 s apart (an ASW airstrike, report
    dbomb_airsupport 3570) were merged and called fire, and 5 ticks of 46.6
    (report flood 233, after those depth charges) were also called fire.
    - A damage-over-time run needs at least 3 hits about 0.9-1.4 s apart,
      each at most 1.5 % of my max HP. Two equal hits are just two hits.
    - Flood also follows the same attacker's depth-charge hits (ship or
      airstrike) within 10 s, not only torpedoes.
    - burningFlags alone never makes a run fire when the run also follows
      a torpedo or depth-charge hit of that attacker; say "unknown" then
      unless reconcile_with_report() settles it.
    """
    if not isinstance(timeline, dict) or not isinstance(event, dict):
        return "unknown"
    events = timeline.get("events")
    if not isinstance(events, list):
        return "unknown"
    attacker_id = _integer_id(event.get("attacker_id"))
    target_id = _integer_id(event.get("target_id"))
    timestamp = _number(event.get("timestamp"))
    if attacker_id is None or target_id is None or timestamp is None:
        return "unknown"

    max_health = _timeline_max_health(timeline, target_id)
    if _periodic_damage_run(events, event, run_length, max_health):
        if _follows_torpedo_hit(events, target_id, attacker_id, timestamp):
            return "flood"
        if _follows_depth_charge_hit(events, target_id, attacker_id, timestamp):
            return "flood"
        if _burning_at(events, target_id, timestamp):
            return "fire"
        return "unknown"
    if _amount_has_periodic_run(events, event, max_health):
        return "unknown"

    stat_weapon = _damage_stat_weapon(events, target_id, timestamp)
    projectile_weapon = _projectile_weapon(
        events, attacker_id, timestamp, projectile_types or {}
    )
    damage = _number(event.get("damage"))
    if (
        max_health is not None
        and damage is not None
        and damage <= max_health * 0.015
        and projectile_weapon is None
    ):
        return "unknown"
    if projectile_weapon == "torpedo":
        return "torpedo"
    if stat_weapon is not None:
        if (
            projectile_weapon is not None
            and projectile_weapon != stat_weapon
        ):
            return "unknown"
        return stat_weapon
    return projectile_weapon or "unknown"


_DAMAGE_STAT_WEAPONS = {
    "MAIN_HE": "main_he",
    "MAIN_AP": "main_ap",
    "ATBA_HE": "secondary_he",
    "ATBA_AP": "secondary_ap",
    "TORPEDO": "torpedo",
    "TORPEDO_ALTER": "torpedo",
    "TORPEDO_DEEP": "torpedo",
    "DEPTH_CHARGE": "depth_charge_airstrike",
    "DEPTH_CHARGE_ASUP": "depth_charge_airstrike",
    "DEPTH_CHARGE_ALTER": "depth_charge_airstrike",
    "DEPTH_CHARGE_TC": "depth_charge_airstrike",
    "BOMBER_AP": "bomb_airstrike",
    "BOMBER_HE": "bomb_airstrike",
    "BOMBER_AP_ASUP": "bomb_airstrike",
    "BOMBER_HE_ASUP": "bomb_airstrike",
    "BOMBER_AP_ALTER": "bomb_airstrike",
    "BOMBER_HE_ALTER": "bomb_airstrike",
    "BOMBER_AP_TC": "bomb_airstrike",
    "BOMBER_HE_TC": "bomb_airstrike",
    "BURN": "fire",
    "FLOOD": "flood",
    "RAM": "ram",
}


def _damage_stat_weapon(
    events: list[dict], ship_id: int, timestamp: float
) -> str | None:
    candidates: list[tuple[float, str]] = []
    for item in events:
        if (
            not isinstance(item, dict)
            or item.get("event_type") != "DamageReceivedStatEvent"
            or _integer_id(item.get("entity_id")) != ship_id
            or item.get("stat_type") != "AGRO"
        ):
            continue
        weapon = _DAMAGE_STAT_WEAPONS.get(item.get("damage_param"))
        stat_time = _number(item.get("timestamp"))
        if weapon is None or stat_time is None:
            continue
        distance = abs(stat_time - timestamp)
        if distance <= 2.1:
            candidates.append((distance, weapon))
    if not candidates:
        return None
    closest = min(distance for distance, _ in candidates)
    weapons = {
        weapon for distance, weapon in candidates
        if abs(distance - closest) <= 0.05
    }
    return next(iter(weapons)) if len(weapons) == 1 else None


def _projectile_weapon(
    events: list[dict],
    attacker_id: int,
    timestamp: float,
    projectile_types: dict[int, str],
) -> str | None:
    created_by_shot: dict[int, list[dict]] = {}
    fire_events = [
        item for item in events
        if isinstance(item, dict)
        and item.get("event_type") in ("GunFireEvent", "SecondaryFireEvent")
        and _integer_id(item.get("entity_id")) == attacker_id
    ]
    for item in events:
        if (
            isinstance(item, dict)
            and item.get("event_type") in ("TorpedoCreatedEvent", "ShotCreatedEvent")
            and _integer_id(item.get("owner_id")) == attacker_id
            and (shot_id := _integer_id(item.get("shot_id"))) is not None
        ):
            created_by_shot.setdefault(shot_id, []).append(item)

    impacts = [
        item for item in events
        if isinstance(item, dict)
        and item.get("event_type") == "ShotDestroyedEvent"
        and _integer_id(item.get("owner_id")) == attacker_id
        and (impact_time := _number(item.get("timestamp"))) is not None
        and abs(impact_time - timestamp) <= 0.25
    ]
    candidates: set[str] = set()
    for impact in impacts:
        shot_id = _integer_id(impact.get("shot_id"))
        if shot_id is None:
            continue
        for created in created_by_shot.get(shot_id, []):
            if created.get("event_type") == "TorpedoCreatedEvent":
                candidates.add("torpedo")
                continue
            params_id = _integer_id(created.get("params_id"))
            ammo_type = projectile_types.get(params_id) if params_id is not None else None
            if ammo_type not in ("HE", "AP"):
                continue
            created_time = _number(created.get("timestamp"))
            if created_time is None:
                continue
            fire_types = {
                fire_event.get("event_type")
                for fire_event in fire_events
                if (fire_time := _number(fire_event.get("timestamp"))) is not None
                and abs(fire_time - created_time) <= 1.5
            }
            if len(fire_types) == 1:
                prefix = "main" if next(iter(fire_types)) == "GunFireEvent" else "secondary"
                candidates.add(f"{prefix}_{ammo_type.lower()}")
    return next(iter(candidates)) if len(candidates) == 1 else None


def _periodic_damage_run(
    events: list[dict],
    event: dict,
    run_length: int,
    max_health: float | None,
) -> bool:
    if (
        isinstance(run_length, bool)
        or not isinstance(run_length, int)
        or run_length < 3
        or max_health is None
        or max_health <= 0
    ):
        return False
    attacker_id = _integer_id(event.get("attacker_id"))
    target_id = _integer_id(event.get("target_id"))
    damage = _number(event.get("damage"))
    timestamp = _number(event.get("timestamp"))
    if attacker_id is None or target_id is None or damage is None or timestamp is None:
        return False
    if damage > max_health * 0.015:
        return False
    matching = sorted(
        time_s
        for item in events
        if isinstance(item, dict)
        and item.get("event_type") == "DamageEvent"
        and _integer_id(item.get("attacker_id")) == attacker_id
        and _integer_id(item.get("target_id")) == target_id
        and (amount := _number(item.get("damage"))) is not None
        and amount <= max_health * 0.015
        and round(amount, 1) == round(damage, 1)
        and (time_s := _number(item.get("timestamp"))) is not None
    )
    group: list[float] = []
    for time_s in matching:
        if group and time_s - group[-1] >= 2.5:
            if (
                len(group) >= run_length
                and any(abs(time - timestamp) <= 0.01 for time in group)
                and _contains_periodic_sequence(group, None)
            ):
                return True
            group = []
        group.append(time_s)
    return (
        len(group) >= run_length
        and any(abs(time - timestamp) <= 0.01 for time in group)
        and _contains_periodic_sequence(group, None)
    )


def _amount_has_periodic_run(
    events: list[dict], event: dict, max_health: float | None
) -> bool:
    target_id = _integer_id(event.get("target_id"))
    damage = _number(event.get("damage"))
    timestamp = _number(event.get("timestamp"))
    if (
        target_id is None
        or damage is None
        or timestamp is None
        or max_health is None
        or max_health <= 0
        or damage > max_health * 0.015
    ):
        return False
    matching = [
        time_s
        for item in events
        if isinstance(item, dict)
        and item.get("event_type") == "DamageEvent"
        and _integer_id(item.get("target_id")) == target_id
        and (amount := _number(item.get("damage"))) is not None
        and amount <= max_health * 0.015
        and round(amount, 1) == round(damage, 1)
        and (time_s := _number(item.get("timestamp"))) is not None
    ]
    return _contains_periodic_sequence(matching, timestamp)


def _contains_periodic_sequence(
    times: list[float], timestamp: float | None
) -> bool:
    """Return whether a hit belongs to three small ticks spaced 0.9-1.4 s."""
    ordered = sorted(times)
    for start_index, start_time in enumerate(ordered):
        sequence = [start_time]
        # Same-amount damage messages can interleave within a periodic cadence.
        for time_s in ordered[start_index + 1:]:
            gap = time_s - sequence[-1]
            if gap < 0.9:
                continue
            if gap > 1.4:
                break
            sequence.append(time_s)
            if len(sequence) >= 3 and (
                timestamp is None
                or any(abs(time - timestamp) <= 0.01 for time in sequence)
            ):
                return True
    return False


def _timeline_max_health(timeline: dict, ship_id: int) -> float | None:
    players = timeline.get("players")
    if not isinstance(players, list):
        return None
    for player in players:
        if (
            isinstance(player, dict)
            and _integer_id(player.get("entity_id")) == ship_id
        ):
            return _number(player.get("max_health"))
    return None


def _follows_torpedo_hit(
    events: list[dict], target_id: int, attacker_id: int, timestamp: float
) -> bool:
    torpedo_ids = {
        _integer_id(item.get("shot_id"))
        for item in events
        if isinstance(item, dict)
        and item.get("event_type") == "TorpedoCreatedEvent"
        and _integer_id(item.get("owner_id")) == attacker_id
    }
    torpedo_impacts = [
        item for item in events
        if isinstance(item, dict)
        and item.get("event_type") == "ShotDestroyedEvent"
        and _integer_id(item.get("owner_id")) == attacker_id
        and _integer_id(item.get("shot_id")) in torpedo_ids
    ]
    for damage in events:
        if (
            not isinstance(damage, dict)
            or damage.get("event_type") != "DamageEvent"
            or _integer_id(damage.get("target_id")) != target_id
            or _integer_id(damage.get("attacker_id")) != attacker_id
        ):
            continue
        damage_time = _number(damage.get("timestamp"))
        if damage_time is None or not 0 < timestamp - damage_time <= 5.0:
            continue
        if any(
            (impact_time := _number(impact.get("timestamp"))) is not None
            and abs(impact_time - damage_time) <= 0.25
            for impact in torpedo_impacts
        ):
            return True
    return False


def _follows_depth_charge_hit(
    events: list[dict], target_id: int, attacker_id: int, timestamp: float
) -> bool:
    depth_charge_stats = [
        stat_time
        for item in events
        if isinstance(item, dict)
        and item.get("event_type") == "DamageReceivedStatEvent"
        and _integer_id(item.get("entity_id")) == target_id
        and item.get("stat_type") == "AGRO"
        and _DAMAGE_STAT_WEAPONS.get(item.get("damage_param"))
        == "depth_charge_airstrike"
        and (stat_time := _number(item.get("timestamp"))) is not None
        and 0 <= timestamp - stat_time <= 10
    ]
    return any(
        isinstance(damage, dict)
        and damage.get("event_type") == "DamageEvent"
        and _integer_id(damage.get("attacker_id")) == attacker_id
        and _integer_id(damage.get("target_id")) == target_id
        and (damage_time := _number(damage.get("timestamp"))) is not None
        and abs(damage_time - stat_time) <= 2.1
        for stat_time in depth_charge_stats
        for damage in events
    )


def _burning_at(events: list[dict], ship_id: int, timestamp: float) -> bool:
    updates = [
        item for item in events
        if isinstance(item, dict)
        and item.get("event_type") == "PropertyUpdateEvent"
        and _integer_id(item.get("entity_id")) == ship_id
        and item.get("property_name") == "burningFlags"
        and (_number(item.get("timestamp")) or 0.0) <= timestamp
    ]
    if updates:
        latest = max(updates, key=lambda item: _number(item.get("timestamp")) or 0.0)
        return bool(_integer_id(latest.get("value")))
    return False


def _death_info_weapon(death_info: dict | None) -> str:
    if not isinstance(death_info, dict):
        return "unknown"
    name = death_info.get("name")
    if not isinstance(name, str):
        return "unknown"
    normalized = name.upper()
    if normalized in ("ADBOMB", "DEPTH_CHARGE", "DEPTH_CHARGE_ASUP"):
        return "depth_charge_airstrike"
    if normalized in ("TORPEDO", "TORPEDO_ALTER", "TORPEDO_DEEP"):
        return "torpedo"
    if normalized in ("HE_SHELL", "AP_SHELL"):
        icon = death_info.get("icon")
        if isinstance(icon, str) and "main_caliber" in icon:
            return "main_he" if normalized == "HE_SHELL" else "main_ap"
        if isinstance(icon, str) and "secondary_caliber" in icon:
            return "secondary_he" if normalized == "HE_SHELL" else "secondary_ap"
        return "unknown"
    return _DAMAGE_STAT_WEAPONS.get(normalized, "unknown")


def _damage_player_reference(player: dict | None) -> dict:
    if not isinstance(player, dict):
        return {"player": None, "ship": None}
    ship = player.get("ship_id") or player.get("ship")
    if isinstance(ship, str):
        match = re.fullmatch(r"[A-Za-z]+\d+_(.+)", ship)
        if match is not None:
            ship = match.group(1).replace("_", " ")
    else:
        ship = None
    return {"player": player.get("name"), "ship": ship}


def reconcile_with_report(entries: list[dict], by_type: dict | None) -> list[dict]:
    """Make the hit list agree with the game's per-weapon totals (0d review).

    Complete replays only (by_type = me.damage_received_by_type from the
    public results, which is exact); return entries unchanged when None.
    Map weapons to categories: main_he/main_ap -> main_he/main_ap (also
    main_cs), secondary_* -> atba_*, torpedo -> tpd_*, depth_charge_airstrike
    -> dbomb_airsupport, bomb_airstrike -> bomb_airsupport, fire, flood, ram.
    1. An entry whose weapon has no damage in the report becomes "unknown".
    2. For each category, if its classified sum exceeds the report by more
       than 1 HP + 0.5 per hit, set that category's entries to "unknown".
    3. Fill: for every category still short of the report, if one unknown
       entry, or all unknown entries of one attacker, match the shortfall
       within 1 HP + 0.5 per hit, give them that weapon. Never split an
       entry. Leave the rest "unknown".
    Shards: Castle3's 59.6 tick becomes flood (1490 - 1429.6 = 60.4).
    OC_prey: the 3570.0 entry becomes depth_charge_airstrike and the 232.8
    entry flood.
    """
    if by_type is None:
        return entries

    categories = {
        "main_he": ("main_he", "main_cs"),
        "main_ap": ("main_ap",),
        "secondary_he": ("atba_he",),
        "secondary_ap": ("atba_ap",),
        "torpedo": tuple(
            key for key in by_type if isinstance(key, str) and key.startswith("tpd_")
        ),
        "depth_charge_airstrike": ("dbomb_airsupport",),
        "bomb_airstrike": ("bomb_airsupport",),
        "fire": ("fire",),
        "flood": ("flood",),
        "ram": ("ram",),
    }

    def report_amount(weapon: str) -> float:
        return sum(
            amount
            for key in categories[weapon]
            if (amount := _number(by_type.get(key))) is not None
        )

    def entry_damage(entry: dict) -> float:
        return _number(entry.get("damage")) or 0.0

    def entry_hits(entry: dict) -> float:
        return max(1.0, _number(entry.get("hits")) or 1.0)

    result = [dict(entry) for entry in entries]
    for entry in result:
        weapon = entry.get("weapon")
        if weapon in categories and report_amount(weapon) <= 0:
            entry["weapon"] = "unknown"

    for weapon in categories:
        classified = [
            entry for entry in result if entry.get("weapon") == weapon
        ]
        if not classified:
            continue
        amount = sum(entry_damage(entry) for entry in classified)
        tolerance = 1 + 0.5 * sum(entry_hits(entry) for entry in classified)
        if amount > report_amount(weapon) + tolerance:
            for entry in classified:
                entry["weapon"] = "unknown"

    while True:
        unknown = [
            (index, entry)
            for index, entry in enumerate(result)
            if entry.get("weapon") == "unknown"
        ]
        groups: dict[tuple[int, ...], list[dict]] = {
            (index,): [entry] for index, entry in unknown
        }
        by_attacker: dict[tuple[object, object], list[int]] = {}
        for index, entry in unknown:
            attacker = entry.get("attacker")
            if not isinstance(attacker, dict):
                continue
            identity = (attacker.get("player"), attacker.get("ship"))
            if any(value is not None for value in identity):
                by_attacker.setdefault(identity, []).append(index)
        for indexes in by_attacker.values():
            groups[tuple(indexes)] = [result[index] for index in indexes]

        candidates: dict[str, set[tuple[int, ...]]] = {}
        for weapon in categories:
            shortfall = report_amount(weapon) - sum(
                entry_damage(entry)
                for entry in result
                if entry.get("weapon") == weapon
            )
            if shortfall <= 0:
                continue
            for indexes, group in groups.items():
                group_damage = sum(entry_damage(entry) for entry in group)
                tolerance = 1 + 0.5 * sum(entry_hits(entry) for entry in group)
                if abs(group_damage - shortfall) <= tolerance:
                    candidates.setdefault(weapon, set()).add(indexes)

        group_categories: dict[tuple[int, ...], set[str]] = {}
        for weapon, matching_groups in candidates.items():
            for indexes in matching_groups:
                group_categories.setdefault(indexes, set()).add(weapon)

        assignments = [
            (weapon, next(iter(matching_groups)))
            for weapon, matching_groups in candidates.items()
            if len(matching_groups) == 1
            and len(group_categories[next(iter(matching_groups))]) == 1
        ]
        unambiguous: list[tuple[str, tuple[int, ...]]] = []
        for assignment in assignments:
            indexes = set(assignment[1])
            if not any(
                indexes.intersection(other_indexes)
                for other_weapon, other_indexes in assignments
                if (other_weapon, other_indexes) != assignment
            ):
                unambiguous.append(assignment)
        if not unambiguous:
            break
        for weapon, indexes in unambiguous:
            for index in indexes:
                result[index]["weapon"] = weapon

    return result


def check_damage_consistency(summary: dict) -> list[str]:
    """Return a list of problems in a built summary (empty when consistent).

    Log each problem as a warning in build_all_summaries; never fail the
    summary. Checks, each skipped when its inputs are missing:
    1. me.damage_received == sum of me.damage_received_by_type categories.
    2. me.damage_received - healing.total == max_health - final HP (0 when
       the player died), within HP_TOLERANCE x number of hits.
    2b. me.time_of_death_s within 3 s of me.life_time_s (both battle time).
    3. sum of damage_summary damage_taken == me.damage_received (when the
       replay is complete or the player died while recording).
    4. no two kill events with the same victim.
    5. me.frags == number of kill events with me as killer.
    6. sum of damage_summary damage_dealt within 2 % of me.damage (complete
       replays only; the timeline misses a little, Shards 0.94 %).
    """
    problems: list[str] = []
    match = summary.get("match")
    me = summary.get("me")
    events = summary.get("events")
    if not isinstance(match, dict) or not isinstance(me, dict):
        return problems

    received = _number(me.get("damage_received"))
    by_type = me.get("damage_received_by_type")
    if received is not None and isinstance(by_type, dict):
        categories = []
        for key, value in by_type.items():
            amount = _number(value)
            if key != "total" and amount is not None:
                categories.append(amount)
        reported_total = _number(by_type.get("total"))
        if categories or reported_total == 0:
            category_total = sum(categories)
            if abs(received - category_total) > HP_TOLERANCE:
                problems.append(
                    "damage_received differs from the sum of damage_received_by_type "
                    f"categories ({received:g} vs {category_total:g})"
                )

    healing = me.get("healing")
    healed = _number(healing.get("total")) if isinstance(healing, dict) else 0.0
    max_health = _number(me.get("max_health"))
    final_health = _number(me.get("final_health"))
    if final_health is None and me.get("survived") is False:
        final_health = 0.0
    if (
        received is not None
        and max_health is not None
        and final_health is not None
    ):
        expected = max_health - final_health
        tolerance = HP_TOLERANCE * max(1, int(_number(me.get("damage_taken_changes")) or 1))
        if abs(received - healed - expected) > tolerance:
            problems.append(
                "damage_received minus healing differs from max_health minus final HP "
                f"({received - healed:g} vs {expected:g})"
            )

    time_of_death = _number(me.get("time_of_death_s"))
    life_time = _number(me.get("life_time_s"))
    if (
        time_of_death is not None
        and life_time is not None
        and abs(time_of_death - life_time) > 3
    ):
        problems.append(
            f"time_of_death_s differs from life_time_s by more than 3 s "
            f"({time_of_death:g} vs {life_time:g})"
        )

    if isinstance(events, list):
        windows = [
            event for event in events
            if isinstance(event, dict) and event.get("type") == "damage_summary"
        ]
        complete_or_died = (
            match.get("replay_complete") == 1
            or match.get("replay_complete") is True
            or match.get("end_reason") == "left_after_death"
        )
        if complete_or_died and received is not None and windows:
            taken = sum(_number(event.get("damage_taken")) or 0.0 for event in windows)
            if abs(taken - received) > HP_TOLERANCE:
                problems.append(
                    f"damage_summary damage_taken differs from damage_received "
                    f"({taken:g} vs {received:g})"
                )

        complete = (
            match.get("replay_complete") == 1
            or match.get("replay_complete") is True
        )
        damage = _number(me.get("damage"))
        if complete and damage is not None:
            dealt = sum(
                _number(event.get("damage_dealt")) or 0.0 for event in windows
            )
            if abs(dealt - damage) > abs(damage) * 0.02:
                problems.append(
                    f"damage_summary damage_dealt differs from damage "
                    f"({dealt:g} vs {damage:g}; over 2%)"
                )

        kills = [
            event for event in events
            if isinstance(event, dict) and event.get("type") == "kill"
        ]
        victims = [
            victim_id for event in kills
            if (victim_id := _integer_id(event.get("victim_id"))) is not None
        ]
        if len(victims) != len(set(victims)):
            problems.append("kill events contain duplicate victims")
        frags = _number(me.get("frags"))
        own_name = me.get("player")
        if isinstance(own_name, str) and frags is not None:
            own_kills = sum(
                isinstance(event.get("killer"), dict)
                and event["killer"].get("name") == own_name
                for event in kills
            )
            if frags != own_kills:
                problems.append(
                    f"me.frags differs from kill events ({frags:g} vs {own_kills})"
                )
    return problems


def _integer_id(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _death_victim_id(event: dict) -> int | None:
    victim_id = _integer_id(event.get("victim_id"))
    return victim_id if victim_id is not None else _integer_id(event.get("entity_id"))


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _health_before(
    track: list[tuple[float, float]], timestamp: float
) -> float | None:
    for time_s, health in reversed(track):
        if time_s <= timestamp:
            return health
    return None
