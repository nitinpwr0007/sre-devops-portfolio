# SLO — Availability (Week 1, Day 5)

## The SLO
**99.9%** of HTTP requests succeed (non-5xx) — measured over a rolling **30-day** window.

- **SLI** (what we measure): `sum(non-5xx requests) / sum(all requests)` — see [SLI.md](SLI.md).
- **SLO** (the target): SLI ≥ **99.9%**.
- **Error budget**: the 0.1% we are *allowed* to fail = **0.001** of all requests.

## Error budget → allowed downtime
Error budget as *time* (100% unavailable for that long) per window:

| Window   | 99.9% budget | 99.95% (stretch) | 99.99% (aspirational) |
|----------|-------------:|-----------------:|----------------------:|
| 30 days  | **43m 12s**  | 21m 36s          | 4m 19s                |
| 7 days   | 10m 05s      | 5m 02s           | 1m 00s                |
| 1 day    | 1m 26s       | 43s              | 8.6s                  |
| 1 hour   | 3.6s         | 1.8s             | 0.36s                 |

> 99.9% sounds strict but is **~43 minutes/month** of full outage — or the equivalent
> spread as a low error rate. The budget is what we *spend* on risky deploys and blips.

## Burn rate — why two windows
**Burn rate** = how fast we spend the budget. Burn rate `1` exhausts the 30-day budget
in exactly 30 days; burn rate `14.4` exhausts it in ~2 days.

We alert only when a **long** and a **short** window both exceed the threshold:
- long window = "is this a real, sustained burn?"
- short window = "is it *still* happening right now?" (so the alert resolves fast after recovery)

| Alert                  | Burn rate | 5xx ratio threshold | Windows (long / short) | Budget gone in | Severity |
|------------------------|:---------:|:-------------------:|:----------------------:|:--------------:|:--------:|
| `ErrorBudgetBurnFast`  | 14.4x     | > 1.44%             | 1h / 5m                | ~2 days        | page     |
| `ErrorBudgetBurnSlow`  | 6x        | > 0.6%              | 6h / 30m               | ~5 days        | ticket   |

Rules live in [prometheus/rules/slo_burn_rate.yml](prometheus/rules/slo_burn_rate.yml).

## Verify
- Rules loaded: Prometheus → **Status → Rules** (both groups healthy).
- Recorded SLI: query `job:slo_errors:ratio_rate5m` in Prometheus.
- Alerts: **Alerts** tab shows both inactive (green) until Day 6 fault injection makes them fire.
