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

# BigWorld world unit in metres (see point 5 above). Use world_to_km() for
# every distance in a summary; never print raw world-unit distances.
WORLD_UNIT_M = 30.0

# A tolerance in HP for the consistency checks (float rounding in events).
HP_TOLERANCE = 2.0


def world_to_km(units: float) -> float:
    """Convert a world-unit distance to km, rounded to 0.1 km."""
    raise NotImplementedError


def battle_start_s(timeline: dict | None) -> float | None:
    """Return the recording time when the battle starts (end of countdown).

    The BattleLogic entity's `timeLeft` property counts the 30 s countdown
    down to 0, then jumps to the battle length (1200) and `battleStage`
    becomes 0; that event's timestamp is the start (Shards: 32.35 s).
    None when not found.
    """
    raise NotImplementedError


def battle_time(recording_s: float, start_s: float | None) -> float:
    """Convert a recording time to battle time (seconds since battle start),
    rounded to 0.1. Negative during the countdown; unchanged when start_s is
    None."""
    raise NotImplementedError


def health_track(timeline: dict | None, ship_id: int) -> list[tuple[float, float]]:
    """Return [(time_s, hp)] for one ship from its `health` PropertyUpdateEvents.

    Start with (0.0, max_health) from timeline.players when the first update
    is later. Keep the order of the events; drop exact repeats of the same
    value. Empty list if the timeline has no health updates for the ship.
    """
    raise NotImplementedError


def deduplicate_deaths(events: list[dict]) -> list[dict]:
    """Return the DeathEvents with exactly one per victim_id.

    When a victim has two events (see point 4 above), keep the one whose
    entity_id differs from victim_id (the Avatar one, with the real
    death_reason). Keep the original order. Use this everywhere deaths are
    read: kill events, frags, time of death, alive checks.
    """
    raise NotImplementedError


def killing_blows(timeline: dict | None) -> list[dict]:
    """Return the damage of every killing blow, which has no DamageEvent.

    For each deduplicated death: {"time_s", "victim_id", "killer_id",
    "damage"}, where damage = the victim's last HP before the death (from
    health_track, or from the last state snapshot if the track is empty).
    Skip deaths where the victim's HP is unknown or the killer is the victim
    itself (e.g. flooding with no attacker); log those at DEBUG.
    """
    raise NotImplementedError


def damage_dealt_by_ship(timeline: dict | None) -> dict[int, float]:
    """Return {attacker ship id: damage} from DamageEvents plus killing_blows().

    Replaces match_summary._damage_by_ship. Rounded to 0.1. DamageEvents
    with attacker_id 0 are not attributed (report them in COPILOT_NOTES if
    they are a large share).
    """
    raise NotImplementedError


def damage_windows(
    timeline: dict | None,
    ship_id: int,
    end_s: float | None,
    window_s: int = 30,
) -> list[dict]:
    """Return the per-window damage summary for the recording player.

    One dict per window that has any damage or healing:
    {"start_s", "end_s", "damage_dealt", "damage_taken", "healed"}.
    - damage_taken / healed: the sum of HP drops / rises in health_track()
      inside the window (this includes the killing blow).
    - damage_dealt: my DamageEvents plus my killing_blows() in the window.
    - The window that contains the player's death ends at the time of death
      (end_s = time of death, rounded to 0.1), and no window follows it for
      taken/healed. `end_s` (the recorded or battle duration) caps the last
      window the same way.
    Checks (see check_damage_consistency): sum(damage_taken) - sum(healed)
    == max_health - final HP.
    """
    raise NotImplementedError


def healing_received(timeline: dict | None, ship_id: int) -> dict | None:
    """Return {"total", "events": [{"start_s", "end_s", "amount"}]} or None.

    Events: group consecutive HP rises in health_track() that are at most
    2.5 s apart into one heal (start of first rise, time of last rise, sum).
    total: the last value of the ship's `regeneratedHealth` property when
    present, else the sum of the events; log a warning if the two differ by
    more than HP_TOLERANCE. None when there was no healing.
    Shards replay: total 997.5, one event 613.2-627.2 s.
    """
    raise NotImplementedError


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
    """
    raise NotImplementedError
