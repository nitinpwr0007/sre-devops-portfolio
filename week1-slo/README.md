# Week 1 — SRE Foundations (SLI / SLO / Error Budget)

A hands-on lab: instrument a real service, then build SLIs, an SLO, an error budget, and a
burn-rate alert on top of it — all locally with Docker.

## What's here
| Path | What it is |
|------|-----------|
| `app/` | A small Flask service instrumented with Prometheus metrics |
| `docker-compose.yml` | Runs app + Prometheus + Grafana |
| `prometheus/prometheus.yml` | **Day 2** — scrape config (pulls `app:8080/metrics` every 5s) |
| `grafana/provisioning/` | **Day 2** — auto-provisions the Prometheus datasource |
| `grafana/dashboards/week1-slo.json` | **Day 3** — SLO dashboard (availability panel) as code |
| `SLI.md` | **Day 1** — the 2 SLIs defined for this app (availability, latency-p95) |

## The app
Endpoints:
- `GET /` — hello / status
- `GET /healthz` — health check
- `GET /api/products` — fast read path
- `GET|POST /api/checkout` — slower write path (fault-injection target in Day 6)
- `GET /metrics` — Prometheus metrics

Metrics exposed:
- `http_requests_total{method,endpoint,status}` → **availability SLI**
- `http_request_duration_seconds{endpoint}` (histogram) → **latency SLI**

Fault injection (Day 6) via env vars in `docker-compose.yml`: `FAIL_RATE`, `LATENCY_MS`.

## Run it
```bash
docker compose up -d --build
curl localhost:8080/api/products
curl localhost:8080/api/checkout
curl -s localhost:8080/metrics | grep http_requests_total
```

## Access the stack (Day 2)
| Service | URL | Login |
|---------|-----|-------|
| Demo app | http://localhost:8080 | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | `admin` / `admin` |

Sanity check Prometheus is scraping the app: open http://localhost:9090/targets —
the `week1-demo` target should be **UP**. In Grafana the **Prometheus** datasource is
already wired up (no setup needed).

## Progress
- [x] **D1** — app running in Docker + 2 SLIs defined (`SLI.md`)
- [x] **D2** — Prometheus scraping the app + Grafana with datasource provisioned
- [x] **D3** — availability SLI as PromQL + live Grafana panel (`Week 1 · SLO Dashboard`)
- [ ] D3 — availability SLI panel
- [ ] D4 — latency SLI panel
- [ ] D5 — SLO + error budget + burn-rate alert
- [ ] D6 — break the app, watch the budget burn
- [ ] D7 — write-up + capstone

