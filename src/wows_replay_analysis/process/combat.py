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
) -> list[dict]:
    """Return who hit me, when and how hard, compact enough for the summary.

    Source: DamageEvents with target_id == ship_id, plus my own killing blow
    (from killing_blows(), weapon from the report's death_info "name", e.g.
    "ADBOMB"). Merge runs of events from the same attacker with the same
    amount (to 0.1) less than 2.5 s apart into one entry with a hit count;
    fire and flooding ticks become one entry each that way.
    Entry: {"start_s", "end_s", "attacker": {"player", "ship"},
    "weapon", "hits", "damage"}; end_s only when hits > 1.

    weapon: one of "main_he", "main_ap", "secondary_he", "secondary_ap",
    "torpedo", "depth_charge_airstrike", "bomb_airstrike", "fire", "flood",
    "ram" or "unknown". DamageEvents have no weapon (damage_type "", ammo_id
    0), so classify_hit() derives it; return "unknown" rather than guess.
    """
    raise NotImplementedError


def classify_hit(timeline: dict, event: dict, run_length: int) -> str:
    """Return the weapon of one DamageEvent to me (values: see above).

    Investigate on the real replays first and report in COPILOT_NOTES what
    works. Ideas, best first:
    - ShotDestroyedEvent / ShotCreatedEvent with owner_id == attacker at the
      same timestamp: params_id -> gamedata projectile -> ammo type (HE/AP)
      and whether the gun is main battery or secondary.
    - Torpedo hits: a torpedo of the attacker (TorpedoCreatedEvent
      owner_id) destroyed at that time.
    - Airstrike: the attacker is not near (> 6 km) and a DepthChargeEvent /
      squadron of the attacker is active.
    - Ticks: a run of equal amounts about 1.15 s apart is fire or flood;
      tell them apart with the own ship's burningFlags / flood state
      properties.
    Then reconcile: the per-weapon sums must match the report's by-type
    figures (expected values for Shards are in the module docstring).
    """
    raise NotImplementedError


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
