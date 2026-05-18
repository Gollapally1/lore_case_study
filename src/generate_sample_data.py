"""
Generate synthetic engagement events that mimic what would flow through
Kafka in production. Writes to data/raw/engagement_events.jsonl.

Realistic enough to exercise the pipeline:
- Multiple partners (employers)
- Multiple users per partner, with stable IDs
- Sessions with realistic event sequences
- Duplicate events (idempotency test)
- Late-arriving events (filter test)
- Invalid partner_ids (quality gate test)
"""
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(42)

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "engagement_events.jsonl"

PARTNERS = ["acme-corp", "globex", "initech", "umbrella", "stark-industries"]
EVENT_TYPES = ["chat_message", "session_start", "session_end",
               "exercise_complete", "community_post", "reward_earned"]
PLATFORMS = ["ios", "android", "web"]
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def generate_session(user_id: str, partner_id: str, session_start_ts: datetime):
    """Generate a realistic event sequence for one session."""
    session_id = str(uuid.uuid4())
    platform = random.choice(PLATFORMS)
    app_version = random.choice(["3.4.1", "3.5.0", "3.5.1"])
    events = []

    # session_start
    events.append({
        "event_id": str(uuid.uuid4()),
        "event_timestamp": session_start_ts.isoformat(),
        "user_id": user_id,
        "partner_id": partner_id,
        "event_type": "session_start",
        "session_id": session_id,
        "event_properties": {"is_first_session": str(random.random() < 0.05).lower()},
        "app_version": app_version,
        "device_platform": platform,
    })

    # 1-8 in-session events
    n_in_session = random.randint(1, 8)
    cursor = session_start_ts
    for _ in range(n_in_session):
        cursor += timedelta(seconds=random.randint(10, 120))
        evt = random.choice(["chat_message", "exercise_complete",
                             "community_post", "reward_earned"])
        events.append({
            "event_id": str(uuid.uuid4()),
            "event_timestamp": cursor.isoformat(),
            "user_id": user_id,
            "partner_id": partner_id,
            "event_type": evt,
            "session_id": session_id,
            "event_properties": {"category": random.choice(["anxiety","sleep","focus","relationships"])},
            "app_version": app_version,
            "device_platform": platform,
        })

    # session_end
    cursor += timedelta(seconds=random.randint(30, 300))
    duration = int((cursor - session_start_ts).total_seconds())
    events.append({
        "event_id": str(uuid.uuid4()),
        "event_timestamp": cursor.isoformat(),
        "user_id": user_id,
        "partner_id": partner_id,
        "event_type": "session_end",
        "session_id": session_id,
        "event_properties": {"duration_seconds": str(duration)},
        "app_version": app_version,
        "device_platform": platform,
    })
    return events


def main(n_users: int = 500, days_back: int = 7):
    all_events = []
    for u in range(n_users):
        user_id = f"user_{u:05d}"
        partner_id = random.choice(PARTNERS)
        # 0-15 sessions per user across the window
        n_sessions = random.randint(0, 15)
        for _ in range(n_sessions):
            day_offset = random.randint(0, days_back - 1)
            hour = random.randint(6, 23)
            session_ts = (NOW - timedelta(days=day_offset)).replace(
                hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59)
            )
            all_events.extend(generate_session(user_id, partner_id, session_ts))

    # --- Inject realistic dirt for the pipeline to handle ---
    # 1) duplicates: re-emit ~2% of events with same event_id
    duplicates = random.sample(all_events, k=int(len(all_events) * 0.02))
    all_events.extend(duplicates)

    # 2) late-arriving (older than 7-day window): 50 stragglers
    for _ in range(50):
        late = random.choice(all_events).copy()
        late["event_id"] = str(uuid.uuid4())
        late_ts = NOW - timedelta(days=random.randint(8, 30))
        late["event_timestamp"] = late_ts.isoformat()
        all_events.append(late)

    # 3) invalid partner_id: 20 events
    for _ in range(20):
        bad = random.choice(all_events).copy()
        bad["event_id"] = str(uuid.uuid4())
        bad["partner_id"] = "ghost-partner-do-not-exist"
        all_events.append(bad)

    # Shuffle so order doesn't help
    random.shuffle(all_events)

    # Add ingest_timestamp (would be set by Kafka consumer in real life)
    for e in all_events:
        e["ingest_timestamp"] = (NOW - timedelta(seconds=random.randint(0, 120))).isoformat()

    with OUTPUT_PATH.open("w") as f:
        for e in all_events:
            f.write(json.dumps(e) + "\n")

    print(f"Generated {len(all_events)} events -> {OUTPUT_PATH}")
    print(f"  Unique event_ids:  {len(set(e['event_id'] for e in all_events))}")
    print(f"  Unique user_ids:   {len(set(e['user_id'] for e in all_events))}")
    print(f"  Unique partner_ids:{len(set(e['partner_id'] for e in all_events))}")


if __name__ == "__main__":
    main()
