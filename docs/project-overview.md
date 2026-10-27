# Project Overview

## Problem statement

Organisations record every login, file access and administrative action in
access logs, but the volume makes manual review impractical. Real threats —
brute-force attempts, compromised credentials used from a new location, insiders
working at odd hours, or staff touching data outside their role — are a tiny
fraction of events and are easily missed. Pure rule systems are transparent but
rigid; pure machine-learning systems adapt but are hard to explain to an analyst.

**Lognexa** addresses this by auditing access logs with a hybrid of explainable
rules and an unsupervised anomaly detector, producing a risk score and a
plain-language explanation for every event.

## Motivation

- Security analysts need to *trust* an alert before acting on it, so every score
  must show which behaviour caused it.
- Labelled attack data is rarely available, so the ML component must be
  unsupervised (Isolation Forest).
- Students cannot use real corporate logs (privacy, access), so a reproducible
  synthetic dataset with known injected anomalies is used for development and
  evaluation.

## Objectives

1. Generate a reproducible synthetic access-log dataset (~2,200 events, 60 users,
   14 days) with four injected anomaly families.
2. Store users, logs, risk scores and alerts in a relational database (PostgreSQL).
3. Engineer behavioural features relative to each user's own baseline.
4. Implement explainable rule-based detection and an Isolation Forest model.
5. Combine both into a documented risk formula with four severity levels.
6. Expose the results through a validated REST API (FastAPI).
7. Provide a responsive dashboard for monitoring, investigation and alert triage.
8. Evaluate detection against the injected labels and document the limitations honestly.

All eight objectives are implemented (see [implementation-log.md](implementation-log.md)).

## Scope

**In scope**

- Synthetic data generation, storage and batch analysis of the whole dataset.
- Four anomaly types: repeated failed logins, unusual login hours,
  new/unusual IPs and locations, sensitive-resource access outside role.
- Alert lifecycle: open → acknowledged → resolved (and reopen), with analyst name
  and resolution note.
- Evaluation (precision / recall / F1) against the generator's labels.

**Out of scope (not implemented)**

- Ingesting real logs from SIEMs, syslog, Windows Event Log or cloud providers.
- Real-time / streaming detection (analysis is a batch run over all stored logs).
- Authentication and role-based access for dashboard users.
- Automated response (blocking IPs, disabling accounts) or notifications.
- Geo-IP lookup: countries/cities are generated, not resolved.

## Anomaly types

| Type | How it is injected | Main detecting rules |
|---|---|---|
| Repeated failed logins | 5–9 failed logins within minutes from an external IP; ~40% end in a success | R1A, R1B, R1C |
| Unusual login hours | Day-shift users active at 01:00–04:30 (20% subtle: ~05:00 or ~23:00) | R2A, R2B |
| New / unusual IP | Login or access from a never-seen external IP, mostly foreign (25% domestic, subtle) | R3A, R3B, R3C |
| Sensitive-resource access | Restricted resource accessed by a role that is not authorised (30% denied) | R4A, R4B, R4C |

## Users of the system

- **Security analyst** – monitors the overview, investigates high-risk events and
  resolves alerts.
- **Evaluator / examiner** – enrols a test endpoint, reviews its live
  telemetry and alerts, and inspects the detection test suite and its metrics.
