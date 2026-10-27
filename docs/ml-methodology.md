# Detection & ML Methodology

Code: `server/app/services/` — `synthetic.py`, `policy.py`, `features.py`,
`rules.py`, `ml.py`, `scoring.py`, `pipeline.py`.

## 1. Synthetic dataset

`generate_dataset(seed=42, n_users=60, days=14, n_records=2200)` draws everything
from a single `numpy.random.default_rng(seed)`, so the same seed always yields an
identical dataset (verified by `test_same_seed_is_reproducible`).

**Users.** 60 users across six departments (Engineering 16, Sales 12,
Operations 10, Finance 8, IT Security 8, HR 6). Each has an office IP
(`10.x.x.x`), a home/VPN IP (`192.0.2.x`), a primary device and an activity
weight. A third of Operations staff work a legitimate night shift.

**Normal behaviour.** Day-shift hours ~ N(13:00, 2.4 h) clipped to 07:30–21:00;
night shift ~ N(01:00, 2.2 h). Weekends get ¼ of weekday traffic. Actions:
login 26%, file_read 40%, file_write 14%, download 12%, logout 8%; IT admins also
perform `admin_action`. 80% of events come from the office IP, 20% from VPN.

**Benign noise (intentional false-positive sources).** 2% of events from a random
"travel" IP (`198.51.100.x`), 5% of logins fail once (typos), 1% of file actions
are denied, 2% of day-shift events happen late (21:00–23:30), and IT admins
legitimately access restricted resources.

**Injected anomalies (default run: 143 events = 6.5%).**

| Label | Count | Generation |
|---|---|---|
| `failed_logins` | 53 (8 bursts) | 5–9 failed logins 20–150 s apart from an external `203.0.113.x` IP, foreign location, suspicious device; ~40% end with a successful login |
| `unusual_hours` | 30 | Day-shift users at 01:00–04:30; 20% subtle (≈05:12 or 23:18) |
| `new_ip` | 30 | Unseen `203.0.113.x` IP; 75% foreign country (+ often suspicious device), 25% domestic with normal device (subtle) |
| `sensitive_access` | 30 | Restricted resource (`/finance/payroll`, `/hr/employee-records`, `/admin/user-management`, `/secrets/vault`, `/db/customer-pii-export`) by an unauthorised role; 30% denied |

The `injected_anomaly` column is **never** a model or rule input.

## 2. Feature engineering (`features.py`)

Baselines are computed per user over the analysed window, so every feature
describes how unusual an event is *for that user*.

| Feature | Definition |
|---|---|
| `hour_deviation` | Circular distance (0–12 h) between event hour and the user's circular-mean hour |
| `is_weekend` | Saturday/Sunday |
| `failed_logins_1h` | User's failed logins in the trailing 60 minutes (inclusive), via pandas time-based rolling window |
| `events_1h` | User's events in the trailing 60 minutes (burst activity) |
| `ip_user_share` | Fraction of the user's events from this IP |
| `is_foreign_country` | Country ≠ user's modal country |
| `device_share` | Fraction of the user's events from this device |
| `sensitivity_level` | public 0, internal 1, confidential 2, restricted 3 |
| `unauthorised_access` | Sensitivity ≥ 2 and the role is not authorised (static policy in `policy.py`) |
| `is_failure` | Status is failure or denied |

Helper columns used by rules: `usual_hour`, `ip_event_count`, `is_rare_ip`
(`ip_event_count ≤ 3` or `ip_user_share < 0.05`), `usual_country`.

Circular statistics are used for hours so that 23:00 and 01:00 are 2 h apart,
not 22 h — essential for night-shift users.

## 3. Rule-based detection (`rules.py`)

| Code | Rule | Condition | Points |
|---|---|---|---|
| R1A | Brute-force burst | `failed_logins_1h ≥ 5` | 70 |
| R1B | Repeated failed logins | `3 ≤ failed_logins_1h < 5` | 40 |
| R1C | Success after failures | successful login with `failed_logins_1h ≥ 3` | 25 |
| R2A | Highly unusual hour | `hour_deviation ≥ 7` | 60 |
| R2B | Unusual hour | `5 ≤ hour_deviation < 7` | 25 |
| R3A | Rare IP address | `is_rare_ip` | 30 |
| R3B | Unusual country | `is_foreign_country` | 35 |
| R3C | Unfamiliar device | `device_share < 0.05` | 15 |
| R4A | Restricted resource outside role | unauthorised and restricted | 75 |
| R4B | Confidential resource outside role | unauthorised and confidential | 45 |
| R4C | Denied sensitive request | denied and sensitivity ≥ 2 | 15 |

`rule_score = min(100, Σ points)`. Each hit stores a human-readable reason, e.g.
*"Role 'developer' accessed restricted resource /finance/payroll"*.

Point values were tuned so that one strong indicator on its own pushes an event
to roughly the High band once combined with a typical ML score. An earlier
version (max 45 points per rule) left single-rule anomalies such as 2 AM
activity at ~28 risk (Medium); see [implementation-log.md](implementation-log.md).

## 4. Isolation Forest (`ml.py`)

- Input: the 10 features above, standardised with `StandardScaler`.
- Model: `IsolationForest(n_estimators=200, contamination=0.05, random_state=seed)`.
- `ml_is_anomaly`: `predict(x) == -1` (the ~5% of points isolated fastest).
- `ml_score`: anomaly score `s = −score_samples(x)` rescaled so the **median
  event maps to 0** and the most anomalous maps to 100:
  `ml_score = 100 · clip((s − median(s)) / (max(s) − median(s)), 0, 1)`.
  Centring on the median stops ordinary events from contributing a baseline
  risk of 30–40 points, as plain min-max scaling would.
- Fewer than 10 events: the forest is skipped and ML scores are 0.

Isolation Forest is unsupervised: it needs no labels and isolates points that
are separable with few random splits — a good fit when attacks are rare and
unlabelled.

## 5. Risk formula and severity (`scoring.py`)

```
risk = w · rule_score + (1 − w) · ml_score + B
       B = 10 if (rule_score > 0 and ml_is_anomaly) else 0
risk = clip(risk, 0, 100)          default w = 0.6
```

The agreement bonus rewards independent confirmation: a rule fired *and* the
model separately found the event anomalous.

| Severity | Risk range |
|---|---|
| Critical | ≥ 75 |
| High | 50 – 74.99 |
| Medium | 25 – 49.99 |
| Low | < 25 |

An **alert** is created when `risk ≥ alert_threshold` (default **40**, i.e. upper
Medium and above). The threshold, `w` and contamination are adjustable on the
Analysis page / `POST /analyze`.

## 6. Explainability

For every event Lognexa stores:

1. The triggered rules with points and concrete reasons.
2. Rule score, ML score, whether the forest flagged it, and the exact arithmetic
   (`risk = 0.6 × 100 + 0.4 × 93.1 + 10 = 100`), shown in the UI.
3. `top_features`: up to 3 features whose population z-score ≥ 2 (sign flipped
   for share features, where low = unusual). This is a simple **heuristic**,
   not a model-attribution method such as SHAP; it is labelled as such in the UI.
4. A one-paragraph plain-language explanation.

## 7. Evaluation

Measured by `evaluation_metrics()` on the default dataset (seed 42, 2,200
events, 143 injected anomalies), contamination 0.05, threshold 40, w = 0.6.
These are the actual values from analysis run #2:

| Detector | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| **Combined (risk ≥ 40)** | 137 | 38 | 6 | **0.783** | **0.958** | **0.862** |
| Rules only (rule score ≥ 40) | 136 | 45 | 7 | 0.751 | 0.951 | 0.840 |
| Isolation Forest only (flagged) | 95 | 15 | 48 | 0.864 | 0.664 | 0.751 |

Per anomaly type (combined): failed logins 53/53, sensitive access 30/30,
new IP 27/30, unusual hours 27/30.

Threshold sensitivity (same data, measured during tuning):

| Threshold | Precision | Recall | F1 |
|---|---|---|---|
| 25 | 0.626 | 0.993 | 0.768 |
| 40 | 0.783 | 0.958 | 0.862 |
| 50 | 0.905 | 0.797 | 0.848 |

**Interpretation.** The hybrid has a better F1 than either detector alone: rules
give high recall and explanations, the forest adds precision, and the agreement
bonus separates events where both agree. Most false positives are the benign
travel-IP and late-working noise; most misses are the deliberately subtle
domestic-IP and near-normal-hour anomalies.

**Caveats — do not over-interpret these numbers.**

- The generator and the detector were designed by the same team, so the
  injected anomalies match the rules' assumptions. Real attacks are more varied.
- Metrics are measured on the data the forest was fitted on (no hold-out set);
  this is normal for unsupervised outlier detection but is not a generalisation
  estimate.
- Point weights and the threshold were tuned on this dataset.
- The numbers are **not** an estimate of real-world accuracy.
