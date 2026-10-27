"""Reproducible synthetic access-log generator (TEST FIXTURE ONLY).

This lives in the test suite, not the application: the app holds only real
data. Tests use it to exercise the access-log detection pipeline against
known, injected anomalies.

Produces ~2,200 events for 60 synthetic users over 14 days, with four
injected anomaly families:

* ``failed_logins``    - bursts of failed logins from an external IP
* ``unusual_hours``    - activity by day-shift users in the middle of the night
* ``new_ip``           - logins from an IP / country never used by the user
* ``sensitive_access`` - access to restricted resources outside the user's role

Normal traffic deliberately contains benign "noise" (the odd typo'd password,
legitimate travel / VPN IPs, late working, authorised admin access) so that
detection is not trivially perfect. Some injected anomalies are also subtle.

All randomness flows from one ``numpy.random.Generator`` so the same seed
always produces the same dataset. IP addresses use RFC 1918 / RFC 5737
documentation ranges and never correspond to real hosts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from app.services.policy import DEPARTMENTS, SENSITIVE_RESOURCES, sensitivity_of

DEFAULT_START = datetime(2026, 10, 1)

FIRST_NAMES = [
    "Aarav", "Diya", "Rohan", "Ananya", "Kabir", "Isha", "Vihaan", "Meera", "Arjun", "Saanvi",
    "Reyansh", "Kavya", "Aditya", "Nisha", "Karan", "Priya", "Dev", "Tara", "Nikhil", "Riya",
    "Sahil", "Pooja", "Yash", "Sneha", "Omkar", "Aditi", "Varun", "Neha", "Siddharth", "Lavanya",
]
LAST_NAMES = [
    "Sharma", "Patil", "Iyer", "Kulkarni", "Reddy", "Deshmukh", "Nair", "Joshi", "Mehta", "Gupta",
    "Rao", "Shinde", "Banerjee", "Kapoor", "Pillai", "Chavan", "Verma", "Menon", "Bhosale", "Das",
]
HOME_CITIES = ["Pune", "Mumbai", "Bengaluru", "Hyderabad"]
DEVICES = ["Windows 11 / Chrome", "Windows 11 / Edge", "macOS / Safari", "macOS / Chrome", "Ubuntu / Firefox"]
SUSPICIOUS_DEVICES = ["Linux / curl", "Kali Linux / Firefox", "Unknown / python-requests", "Android / WebView"]
FOREIGN_LOCATIONS = [
    ("RU", "Moscow"), ("CN", "Shenzhen"), ("BR", "Sao Paulo"), ("NG", "Lagos"),
    ("US", "Ashburn"), ("DE", "Frankfurt"), ("RO", "Bucharest"), ("VN", "Hanoi"),
]

# Department -> headcount weight; scaled to the requested number of users.
DEPARTMENT_WEIGHTS = {
    "Engineering": 16, "Finance": 8, "Human Resources": 6,
    "Sales": 12, "Operations": 10, "IT Security": 8,
}

NORMAL_ACTIONS = ["login", "file_read", "file_write", "download", "logout"]
NORMAL_ACTION_P = [0.26, 0.40, 0.14, 0.12, 0.08]


@dataclass
class Dataset:
    users: list[dict]
    logs: list[dict]


def _doc_ip(rng: np.random.Generator, block: str) -> str:
    """Return an address from a documentation / private block."""
    if block == "external":  # RFC 5737 TEST-NET-3
        return f"203.0.113.{rng.integers(1, 255)}"
    if block == "travel":  # RFC 5737 TEST-NET-2
        return f"198.51.100.{rng.integers(1, 255)}"
    raise ValueError(block)


def _make_users(rng: np.random.Generator, n_users: int) -> list[dict]:
    depts = list(DEPARTMENT_WEIGHTS)
    weights = np.array([DEPARTMENT_WEIGHTS[d] for d in depts], dtype=float)
    counts = np.floor(weights / weights.sum() * n_users).astype(int)
    # Distribute the remainder to the largest departments first.
    for i in np.argsort(-weights)[: n_users - counts.sum()]:
        counts[i] += 1

    users: list[dict] = []
    used: set[str] = set()
    uid = 1
    for d_idx, dept in enumerate(depts):
        for k in range(counts[d_idx]):
            while True:
                first = FIRST_NAMES[rng.integers(len(FIRST_NAMES))]
                last = LAST_NAMES[rng.integers(len(LAST_NAMES))]
                username = f"{first[0]}{last}".lower()
                if username not in used:
                    break
                username = f"{first}.{last}".lower()
                if username not in used:
                    break
            used.add(username)
            # A third of Operations staff work the night shift (legitimately).
            shift = "night" if dept == "Operations" and k % 3 == 0 else "day"
            users.append(
                {
                    "id": uid,
                    "username": username,
                    "full_name": f"{first} {last}",
                    "email": f"{username}@lognexa-demo.test",
                    "department": dept,
                    "role": DEPARTMENTS[dept]["role"],
                    "home_country": "IN",
                    "home_city": HOME_CITIES[rng.integers(len(HOME_CITIES))],
                    "shift": shift,
                    "office_ip": f"10.{d_idx + 10}.{rng.integers(0, 8)}.{rng.integers(2, 250)}",
                    "vpn_ip": f"192.0.2.{rng.integers(1, 255)}",  # RFC 5737 TEST-NET-1
                    "device": DEVICES[rng.integers(len(DEVICES))],
                    "activity": float(rng.uniform(0.6, 1.6)),
                }
            )
            uid += 1
    return users


def _sample_day(rng: np.random.Generator, days: int) -> int:
    # Weekends (relative to DEFAULT_START being a Thursday) are quieter.
    weights = np.array(
        [0.25 if (DEFAULT_START + timedelta(days=d)).weekday() >= 5 else 1.0 for d in range(days)]
    )
    return int(rng.choice(days, p=weights / weights.sum()))


def _normal_hour(rng: np.random.Generator, shift: str) -> float:
    if shift == "night":
        return float(np.clip(rng.normal(25.0, 2.2), 20, 30.9)) % 24
    hour = float(np.clip(rng.normal(13.0, 2.4), 7.5, 20.9))
    if rng.random() < 0.02:  # occasional legitimate late working
        hour = float(rng.uniform(21, 23.5))
    return hour


def _ts(start: datetime, day: int, hour: float) -> datetime:
    return start + timedelta(days=day, hours=hour)


def _event(user: dict, ts: datetime, **overrides) -> dict:
    action = overrides.pop("action", "login")
    resource = overrides.pop("resource", "/auth/sso")
    base = {
        "user_id": user["id"],
        "timestamp": ts.replace(microsecond=0),
        "ip_address": user["office_ip"],
        "country": user["home_country"],
        "city": user["home_city"],
        "device": user["device"],
        "action": action,
        "resource": resource,
        "resource_sensitivity": "public" if resource == "/auth/sso" else sensitivity_of(resource),
        "status": "success",
        "injected_anomaly": None,
    }
    base.update(overrides)
    return base


def _normal_event(rng: np.random.Generator, user: dict, start: datetime, days: int) -> dict:
    ts = _ts(start, _sample_day(rng, days), _normal_hour(rng, user["shift"]))
    action = str(rng.choice(NORMAL_ACTIONS, p=NORMAL_ACTION_P))
    if user["role"] == "it_admin" and rng.random() < 0.15:
        action = "admin_action"
    resources = DEPARTMENTS[user["department"]]["resources"]
    resource = "/auth/sso" if action in ("login", "logout") else str(rng.choice(resources))

    ip = user["office_ip"] if rng.random() < 0.8 else user["vpn_ip"]
    overrides: dict = {"ip_address": ip, "action": action, "resource": resource}

    if rng.random() < 0.02:  # benign travel / hotel Wi-Fi
        overrides.update(ip_address=_doc_ip(rng, "travel"), city=str(rng.choice(HOME_CITIES)))
    if action == "login" and rng.random() < 0.05:  # mistyped password
        overrides["status"] = "failure"
    elif action != "login" and rng.random() < 0.01:
        overrides["status"] = "denied"
    return _event(user, ts, **overrides)


def _inject_failed_logins(rng, users, start, days, n_bursts) -> list[dict]:
    events = []
    for user in rng.choice(users, size=n_bursts, replace=False):
        day = _sample_day(rng, days)
        t0 = _ts(start, day, float(rng.uniform(0, 23)))
        attacker_ip = _doc_ip(rng, "external")
        country, city = FOREIGN_LOCATIONS[rng.integers(len(FOREIGN_LOCATIONS))]
        n = int(rng.integers(5, 10))
        t = t0
        for i in range(n):
            t = t + timedelta(seconds=int(rng.integers(20, 150)))
            status = "success" if (i == n - 1 and rng.random() < 0.4) else "failure"
            events.append(
                _event(
                    user, t, ip_address=attacker_ip, country=country, city=city,
                    device=str(rng.choice(SUSPICIOUS_DEVICES)), status=status,
                    injected_anomaly="failed_logins",
                )
            )
    return events


def _inject_unusual_hours(rng, users, start, days, n) -> list[dict]:
    day_users = [u for u in users if u["shift"] == "day"]
    events = []
    for _ in range(n):
        user = day_users[rng.integers(len(day_users))]
        # ~20% are subtle (just before dawn / late evening).
        hour = float(rng.uniform(1, 4.5)) if rng.random() > 0.2 else float(rng.choice([5.2, 23.3]))
        action = str(rng.choice(["login", "download", "file_read"]))
        resource = "/auth/sso" if action == "login" else str(rng.choice(DEPARTMENTS[user["department"]]["resources"]))
        events.append(
            _event(user, _ts(start, _sample_day(rng, days), hour), action=action,
                   resource=resource, injected_anomaly="unusual_hours")
        )
    return events


def _inject_new_ip(rng, users, start, days, n) -> list[dict]:
    events = []
    for _ in range(n):
        user = users[rng.integers(len(users))]
        if rng.random() < 0.25:  # subtle: new IP but domestic, normal device
            country, city, device = "IN", str(rng.choice(HOME_CITIES)), user["device"]
        else:
            country, city = FOREIGN_LOCATIONS[rng.integers(len(FOREIGN_LOCATIONS))]
            device = str(rng.choice(SUSPICIOUS_DEVICES + [user["device"]]))
        action = str(rng.choice(["login", "file_read", "download"]))
        resource = "/auth/sso" if action == "login" else str(rng.choice(DEPARTMENTS[user["department"]]["resources"]))
        events.append(
            _event(user, _ts(start, _sample_day(rng, days), _normal_hour(rng, user["shift"])),
                   ip_address=_doc_ip(rng, "external"), country=country, city=city,
                   device=device, action=action, resource=resource, injected_anomaly="new_ip")
        )
    return events


def _inject_sensitive_access(rng, users, start, days, n) -> list[dict]:
    from app.services.policy import is_authorised

    events = []
    while len(events) < n:
        user = users[rng.integers(len(users))]
        resource = str(rng.choice(SENSITIVE_RESOURCES))
        if is_authorised(user["role"], resource):
            continue
        status = "denied" if rng.random() < 0.3 else "success"
        events.append(
            _event(user, _ts(start, _sample_day(rng, days), _normal_hour(rng, user["shift"])),
                   action=str(rng.choice(["file_read", "download"])), resource=resource,
                   status=status, injected_anomaly="sensitive_access")
        )
    return events


def generate_dataset(
    seed: int = 42,
    n_users: int = 60,
    days: int = 14,
    n_records: int = 2200,
    start: datetime = DEFAULT_START,
) -> Dataset:
    """Generate users and access logs deterministically from ``seed``."""
    if n_users < 6:
        raise ValueError("n_users must be at least 6 (one per department)")
    if days < 1:
        raise ValueError("days must be at least 1")

    rng = np.random.default_rng(seed)
    users = _make_users(rng, n_users)

    n_bursts = max(2, round(n_records * 0.0036))
    n_each = max(3, round(n_records * 0.0136))
    anomalies = (
        _inject_failed_logins(rng, users, start, days, n_bursts)
        + _inject_unusual_hours(rng, users, start, days, n_each)
        + _inject_new_ip(rng, users, start, days, n_each)
        + _inject_sensitive_access(rng, users, start, days, n_each)
    )
    n_normal = n_records - len(anomalies)
    if n_normal < n_users:
        raise ValueError("n_records too small for the requested users")

    activity = np.array([u["activity"] for u in users])
    per_user = rng.multinomial(n_normal, activity / activity.sum())
    normal = [
        _normal_event(rng, user, start, days)
        for user, count in zip(users, per_user)
        for _ in range(count)
    ]

    logs = sorted(normal + anomalies, key=lambda e: (e["timestamp"], e["user_id"]))
    public_users = [
        {k: v for k, v in u.items() if k not in ("office_ip", "vpn_ip", "device", "activity")}
        for u in users
    ]
    return Dataset(users=public_users, logs=logs)


def load_dataset(db, dataset: Dataset) -> dict:
    """Insert ``dataset`` into a (test) database session."""
    from app.models import AccessLog, User

    db.bulk_insert_mappings(User, dataset.users)
    db.bulk_insert_mappings(AccessLog, dataset.logs)
    db.commit()
    return {"users": len(dataset.users), "logs": len(dataset.logs)}
