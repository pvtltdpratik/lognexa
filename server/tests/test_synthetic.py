from collections import Counter

from app.services.policy import is_authorised
from tests.synthetic import generate_dataset


def test_default_dataset_shape():
    ds = generate_dataset()
    assert len(ds.users) == 60
    assert len(ds.logs) == 2200
    days = {e["timestamp"].date() for e in ds.logs}
    assert len(days) == 14


def test_all_four_anomaly_types_injected():
    labels = Counter(e["injected_anomaly"] for e in generate_dataset().logs if e["injected_anomaly"])
    assert set(labels) == {"failed_logins", "unusual_hours", "new_ip", "sensitive_access"}
    assert all(n >= 20 for n in labels.values())


def test_same_seed_is_reproducible():
    a, b = generate_dataset(seed=123), generate_dataset(seed=123)
    assert a.users == b.users
    assert a.logs == b.logs


def test_different_seed_changes_data():
    assert generate_dataset(seed=1).logs != generate_dataset(seed=2).logs


def test_logs_sorted_and_reference_known_users():
    ds = generate_dataset()
    ids = {u["id"] for u in ds.users}
    assert all(e["user_id"] in ids for e in ds.logs)
    ts = [e["timestamp"] for e in ds.logs]
    assert ts == sorted(ts)


def test_sensitive_access_anomalies_are_policy_violations():
    ds = generate_dataset()
    roles = {u["id"]: u["role"] for u in ds.users}
    for e in ds.logs:
        if e["injected_anomaly"] == "sensitive_access":
            assert not is_authorised(roles[e["user_id"]], e["resource"])


def test_ips_use_reserved_ranges_only():
    prefixes = ("10.", "192.0.2.", "198.51.100.", "203.0.113.")
    assert all(e["ip_address"].startswith(prefixes) for e in generate_dataset().logs)
