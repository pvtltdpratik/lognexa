# Final Report Notes

Report-ready material organised by typical B.E./B.Tech chapter. Numbers are
the actual values from the implemented system (seed 42, analysis run with
contamination 0.05, threshold 40, rule weight 0.6).

## Abstract (draft)

Access logs record every authentication and resource request in an
organisation, but their volume makes manual auditing impractical. This project
presents **Lognexa**, a web-based prototype that audits user access logs using a
hybrid of explainable rule-based detection and the unsupervised Isolation Forest
algorithm. Ten behavioural features are computed relative to each user's own
baseline. Eleven weighted rules capture repeated failed logins, unusual hours,
unfamiliar IP addresses or locations, and sensitive-resource access outside a
user's role, while an Isolation Forest scores how isolated each event is. Both
signals are combined into a 0–100 risk score with four severity levels, and
events above a threshold raise alerts with plain-language explanations. The
system is built with FastAPI, PostgreSQL, scikit-learn and a Next.js dashboard.
On a reproducible synthetic dataset of 2,200 events from 60 users over 14 days
with 143 injected anomalies, the hybrid achieved precision 0.78, recall 0.96 and
F1 0.86, higher than rules alone (F1 0.84) or the Isolation Forest alone
(F1 0.75). These results apply only to synthetic data and do not estimate
real-world performance.

## Chapter 1 – Introduction

- Background: insider threats, credential stuffing, privilege misuse; logs as
  the primary evidence source.
- Problem statement and objectives: see [project-overview.md](project-overview.md).
- Contribution: an explainable hybrid scoring scheme, a reproducible synthetic
  benchmark with ground truth, and an analyst-oriented triage dashboard.

## Chapter 2 – Literature survey (topics to cite)

- Signature/rule-based intrusion detection (e.g. Snort-style rules, SIEM correlation rules).
- User and Entity Behaviour Analytics (UEBA) and per-user baselining.
- Isolation Forest: Liu, Ting & Zhou, "Isolation Forest", ICDM 2008.
- Other unsupervised detectors for comparison: One-Class SVM, Local Outlier
  Factor, autoencoders.
- Explainable AI for security (why analysts need reasons, not just scores).
- Use of synthetic datasets for security research (e.g. CERT insider-threat dataset).

## Chapter 3 – System requirements

- Functional: data generation, storage, analysis, risk scoring, alerting,
  alert resolution, search/filter, analytics, evaluation.
- Non-functional: explainability, reproducibility (seeded), input validation
  on client and server, responsive UI, graceful error handling, secrets in
  environment variables.
- Hardware/software: Python 3.10, Node 20, PostgreSQL 18, any modern browser.

## Chapter 4 – System design

Use the diagrams in [architecture.md](architecture.md) (architecture, pipeline
data flow, sequence diagram) and the ER diagram in
[database-schema.md](database-schema.md). Include the risk formula and
severity table from [ml-methodology.md](ml-methodology.md).

## Chapter 5 – Implementation

- Module list with file paths: [implementation-log.md](implementation-log.md).
- Key algorithms to describe with pseudo-code:
  1. Rolling 60-minute failed-login count per user (pandas time window).
  2. Circular mean / distance for hour-of-day deviation.
  3. Isolation Forest training and median-centred score rescaling.
  4. Risk combination with agreement bonus and severity classification.
  5. Re-analysis that preserves acknowledged/resolved alerts.
- Validation design: Pydantic schemas (server) mirrored by Zod schemas
  (client); uniform error envelope.

## Chapter 6 – Results

### Dataset

| Item | Value |
|---|---|
| Users | 60 (6 departments) |
| Events | 2,200 over 1–14 Oct 2026 (synthetic) |
| Injected anomalies | 143 (6.5%): failed logins 53, unusual hours 30, new IP 30, sensitive access 30 |
| Failed / denied requests | 101 (4.6%) |

### Detection performance (synthetic labels)

| Detector | Precision | Recall | F1 |
|---|---|---|---|
| Combined (risk ≥ 40) | 0.783 | 0.958 | 0.862 |
| Rules only | 0.751 | 0.951 | 0.840 |
| Isolation Forest only | 0.864 | 0.664 | 0.751 |

Per-type recall: failed logins 1.00, sensitive access 1.00, new IP 0.90, unusual hours 0.90.

### Severity distribution (all 2,200 events)

Critical 84 · High 42 · Medium 101 · Low 1,973. Alerts raised: 175.

### Most frequent rules

R3A rare IP 89 · R2A highly unusual hour 83 · R3B unusual country 79 ·
R2B unusual hour 78 · R3C unfamiliar device 45 · R4A restricted outside role 30.

### Threshold trade-off

| Threshold | Precision | Recall | F1 |
|---|---|---|---|
| 25 | 0.626 | 0.993 | 0.768 |
| 40 | 0.783 | 0.958 | 0.862 |
| 50 | 0.905 | 0.797 | 0.848 |

Discussion points: the hybrid beats each component; Isolation Forest alone is
precise but misses rule-specific anomalies such as role violations at normal
hours; false positives come mainly from benign travel IPs and late working.

### Testing

48 automated backend tests pass; TypeScript, ESLint and the production build
pass; 11 manual end-to-end scenarios verified (see [testing.md](testing.md)).

## Screenshots to capture

1. Overview page – dark theme (KPI cards + charts).
2. Overview page – light theme (theme toggle).
3. Access logs with filters applied (e.g. severity = critical).
4. Inline validation error (end date before start date).
5. Log detail sheet showing triggered rules, ML score and formula.
6. Alerts page – Open tab.
7. Resolve-alert dialog with validation errors, then success toast.
8. Risk scores page – methodology card and severity band bar.
9. Analysis page – evaluation table and per-type recall cards.
10. Run history after a second analysis.
11. "Backend unavailable" error state.
12. Mobile layout (375 px) with collapsed sidebar.
13. Swagger UI at `/docs`.
14. pytest output (48 passed).

## Limitations (state these explicitly)

- **Synthetic data only.** The anomalies were designed alongside the rules; real
  attacks are more diverse, so real-world accuracy is unknown.
- Metrics are computed on the same data the forest was fitted on, and weights
  and threshold were tuned on it.
- Baselines use the whole 14-day window, so a long-running compromise would
  shift the baseline (a sliding training window would be needed in production).
- Batch analysis only; no streaming or real-time alerting.
- Locations are generated, not geo-resolved; no IP reputation data.
- Static role policy; no dynamic access-control integration.
- No authentication or authorisation on the dashboard or API.
- `top_features` is a z-score heuristic, not a formal attribution method.
- End-to-end runs were done on SQLite; a PostgreSQL run is still pending.
- No frontend automated tests.

## Future scope

- Ingest real logs (syslog, Windows Security events, AWS CloudTrail, Azure AD sign-ins).
- Streaming detection with Kafka or Redis Streams and incremental baselines.
- Compare additional models (LOF, One-Class SVM, autoencoders, sequence models).
- SHAP-based explanations for the ML component.
- Analyst feedback loop: use resolved alerts (true/false positive) to tune weights.
- Geo-IP and threat-intelligence enrichment, impossible-travel detection.
- Authentication, role-based access, audit log of analyst actions.
- E-mail / Slack notifications for critical alerts; automated response playbooks.
- Playwright end-to-end tests and CI pipeline.
