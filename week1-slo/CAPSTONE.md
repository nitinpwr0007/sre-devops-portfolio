# Week 1 Capstone — SLI vs SLO vs Error Budget (with my live lab)

One page, using the stack I built this week (`labs/week1-slo/`) as the running example.

## The three terms, in one sentence each
- **SLI** — what I *measure*: a ratio of good events to total events.
- **SLO** — the *target* I hold that SLI to (e.g. 99.9%).
- **Error budget** — the *allowance* to miss it: `100% − SLO`. It's what I get to spend on risk.

## Made concrete in my lab
| Concept | In this lab |
|---|---|
| **SLI (availability)** | `sum(non-5xx) / sum(all requests)` on the Flask app — see [SLI.md](SLI.md) |
| **SLI (latency)** | p95 of `http_request_duration_seconds` (histogram) |
| **SLO** | **99.9%** of requests non-5xx over 30 days — see [SLO.md](SLO.md) |
| **Error budget** | 0.1% = **43m 12s** of full outage per 30 days |
| **Where I see it** | Grafana → *Week 1 · SLO Dashboard* (availability + p50/p95/p99 panels) |
| **What alerts me** | `ErrorBudgetBurnFast` / `ErrorBudgetBurnSlow` in [prometheus/rules/slo_burn_rate.yml](prometheus/rules/slo_burn_rate.yml) |

## Error budget → why it's a budget, not a target
99.9% doesn't mean "never fail." It means I can fail **0.1% of requests** (≈43 min/month of
downtime-equivalent) *before I've broken my promise*. That budget is a resource:
- Budget left → ship features, take deploy risk.
- Budget spent → freeze risky changes, spend on reliability.

## Burn rate — the idea that makes budgets actionable
**Burn rate** = how fast I'm spending the budget. `1×` = on pace to use exactly the 30-day
budget in 30 days. `14.4×` = the whole month's budget gone in ~2 days.

I alert on **two windows at once** so I only page on a burn that is *both severe and ongoing*:
| Alert | Burn | 5xx threshold | Windows (long / short) | Budget gone in | Severity |
|---|:--:|:--:|:--:|:--:|:--:|
| `ErrorBudgetBurnFast` | 14.4× | > 1.44% | 1h / 5m | ~2 days | page |
| `ErrorBudgetBurnSlow` | 6× | > 0.6% | 6h / 30m | ~5 days | ticket |

- **long window** = "is this real / sustained?"
- **short window** = "is it *still happening*?" → the alert resolves fast after recovery.

## Proof I ran it (Day 6)
Injected 60% failures (`FAIL_RATE=0.6 docker compose up -d app`), drove load, and watched:
- error ratio climb across every window (5m → ~56%),
- `ErrorBudgetBurnFast` go **inactive → pending → firing** (`severity: page`),
- then, after healing the app, the 5m window rolled off and the alert **cleared** — while the
  slow alert lingered on its longer windows, exactly as designed.

## The one-liner I'd give in an interview
> "An SLI is the measurement, the SLO is the goal, and the error budget is the room to miss.
> I don't alert on raw error rate — I alert on **how fast I'm burning the budget**, across a
> long and a short window, so I page on real sustained pain and not on blips."
