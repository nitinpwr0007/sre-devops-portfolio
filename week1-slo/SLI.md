# Week 1 · Day 1 — SLI definitions for `week1-demo`

An **SLI** (Service Level Indicator) is a *measured number* that reflects the health of the
service from the **user's** point of view. It is always a ratio of `good events / valid events`.
Below are the 2 SLIs for this app, tied to the exact metrics it already exposes at `/metrics`.

---

## SLI 1 — Availability (request success rate)

- **User question it answers:** "When I call the API, does it work?"
- **Good event:** an HTTP response that is **not** a server error (status `< 500`).
- **Valid event:** every request the service handled (excluding `/metrics` and health checks).
- **Definition:**

  $$\text{Availability} = \frac{\text{requests with status} < 500}{\text{all requests}}$$

- **Raw metric used:** `http_requests_total{status, endpoint}`
- **PromQL (built for real in Day 3):**

  ```promql
  sum(rate(http_requests_total{status!~"5..", endpoint!~"/healthz|/metrics"}[5m]))
  /
  sum(rate(http_requests_total{endpoint!~"/healthz|/metrics"}[5m]))
  ```

  > ✅ **Day 3 done** — this is now a live Grafana panel ("Availability SLI") on the
  > *Week 1 · SLO Dashboard*, provisioned from `grafana/dashboards/week1-slo.json`.

- **Why 5xx (not 4xx):** a `400/404` is usually the *client's* fault, not the service failing.
  Counting 4xx as "bad" would punish us for user errors. We only count `5xx` as unavailability.

---

## SLI 2 — Latency (95th percentile response time)

- **User question it answers:** "Is the API fast enough?"
- **Good event:** a request served **faster than the latency threshold** (we'll target p95).
- **Valid event:** every served request.
- **Definition:** the response time below which **95%** of requests fall (p95).

  $$\text{Latency}_{p95} = \text{the value } t \text{ such that } 95\% \text{ of requests complete in} \le t$$

- **Raw metric used:** `http_request_duration_seconds` (a **histogram** → gives us percentiles).
- **PromQL (built for real in Day 4):**

  ```promql
  histogram_quantile(
    0.95,
    sum by (le) (rate(http_request_duration_seconds_bucket{endpoint="/api/checkout"}[5m]))
  )
  ```

  > ✅ **Day 4 done** — p50/p95/p99 are now live panels on the *Week 1 · SLO Dashboard*.

- **Why p95, not average:** averages hide the slow tail. If 5% of users wait 3s while the
  average looks fine, those users still suffer. Percentiles expose the tail that users feel.

---

## The two user journeys these map to
| Journey | Endpoint | SLI that matters most |
|---------|----------|-----------------------|
| Browse catalog (read) | `/api/products` | Availability + low latency |
| Place an order (write)| `/api/checkout` | Availability (money path!) + p95 latency |

## What comes next
- **Day 2:** stand up Prometheus + Grafana and actually **scrape** these metrics.
- **Day 3–4:** turn the two PromQL queries above into **live Grafana panels**.
- **Day 5:** wrap an **SLO** (target %) + **error budget** + **burn-rate alert** around them.

> Note: an SLI is the *measurement*. An **SLO** is the *target* we set on it (e.g. "availability ≥ 99.9%").
> A **SLA** is the *contract* with consequences. Day 5 turns these SLIs into an SLO.
