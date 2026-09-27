# Week 6 — Reliability Engineering (interview notes)

> Notes-only week (this is my day-to-day). A concise, interview-ready reference for
> load testing, chaos engineering, autoscaling under stress, incident response,
> blameless postmortems, and the queueing-theory math behind capacity.

---

## D1 — Load testing to the breaking point (k6)

**Goal:** find the *knee* of the curve — the load where latency rockets while
throughput flattens. That's your capacity ceiling.

**The three regions of a load curve**
```
throughput (req/s)                 latency (p95)
  │        ┌───── plateau            │            ╱ hockey-stick
  │      ╱                           │          ╱
  │    ╱  linear (healthy)           │ ───────╱
  └──────────────► offered load      └──────────────► offered load
        knee ↑                              knee ↑
```
- **Linear region:** throughput rises with load, latency flat → headroom.
- **Knee:** throughput stops rising; latency starts climbing → **this is capacity**.
- **Saturation/collapse:** throughput *drops* (context-switching, queue thrash,
  timeouts, retries amplifying load) → congestion collapse.

**Load-test types**
| Type | Question it answers |
|---|---|
| **Smoke** | does it work at all under minimal load? |
| **Load** | does it meet SLOs at *expected* peak? |
| **Stress** | where does it break, and how? |
| **Spike** | can it survive a sudden 10× burst? |
| **Soak/endurance** | does it degrade over hours (leaks, disk, fd)? |

**k6 essentials**
```js
import http from 'k6/http';
import { check, sleep } from 'k6';
export const options = {
  stages: [
    { duration: '2m', target: 100 },   // ramp up
    { duration: '5m', target: 100 },   // steady
    { duration: '2m', target: 400 },   // push past the knee
    { duration: '2m', target: 0 },     // ramp down
  ],
  thresholds: {                        // FAIL the run if SLOs break
    http_req_duration: ['p(95)<300'],  // p95 latency < 300ms
    http_req_failed:   ['rate<0.01'],  // error rate < 1%
  },
};
export default function () {
  const res = http.get('http://app/health');
  check(res, { 'status 200': (r) => r.status === 200 });
  sleep(1);
}
```
- **VUs vs iterations:** VUs = concurrent virtual users; k6 reports `http_reqs`
  (throughput), `http_req_duration` (latency percentiles), `http_req_failed`.
- **Open vs closed model:** default k6 is **closed** (a VU waits for the response
  before the next request → self-throttles). Use the `constant-arrival-rate` executor
  for an **open model** (fixed req/s regardless of latency) to truly find the breaking
  point — closed models hide collapse because slow responses reduce offered load.
- **`thresholds`** make the test a *gate* (non-zero exit) — wire into CI.

**Interview one-liner:** *"I ramp offered load until throughput plateaus and p95 goes
hockey-stick — that knee is capacity. I use an open-model (arrival-rate) executor so
slow responses don't mask collapse, and encode SLOs as thresholds so the test fails
CI."*

---

## D2 — Chaos engineering (kill pods / inject latency)

**Definition:** deliberately injecting failure into a system to verify it tolerates it
— *"break it on purpose, on a Tuesday, with a hypothesis and a stop button."*

**The scientific method of chaos**
1. Define **steady state** (an SLI: success rate, p95, throughput).
2. Hypothesize: *"killing 1 of 3 pods keeps success rate ≥ 99.9%."*
3. Inject the smallest real fault; keep **blast radius** tiny.
4. Observe the SLI; **abort** if it breaches (automated halt condition).
5. Fix the weakness; widen scope only once it holds.

**Common experiments & what they prove**
| Experiment | Validates |
|---|---|
| Kill a pod | Deployment reschedules; replicas + PDB absorb it |
| Inject latency | timeouts, retries, circuit breakers behave |
| Drop packets / partition | retry/backoff, graceful degradation |
| CPU/memory hog | limits + HPA + OOM behavior |
| Node drain/failure | anti-affinity spreads load; no single-node SPOF |

**Tooling:** Chaos Mesh / LitmusChaos (k8s-native CRDs: `PodChaos`, `NetworkChaos`,
`StressChaos`), or `kubectl delete pod` + `tc netem` for the manual version.

```bash
# manual "kill a pod" chaos, watch self-healing
kubectl delete pod -l app=myapp --wait=false
kubectl get pods -l app=myapp -w        # Deployment recreates to desired replicas

# manual latency injection inside a pod (needs NET_ADMIN)
tc qdisc add dev eth0 root netem delay 200ms 50ms   # 200ms ±50ms jitter
tc qdisc del dev eth0 root netem                    # remove
```

**Game days:** scheduled, whole-team chaos drills against staging/prod to rehearse
detection + response, not just the tech.

**Interview one-liner:** *"Chaos is a hypothesis-driven experiment on steady-state SLIs
with a small blast radius and an automated abort — I'm validating that redundancy,
timeouts and autoscaling actually work, before an incident proves they don't."*

---

## D3 — Network faults, resource exhaustion & blast radius

**Failure domains / blast radius:** the set of things that break when one thing fails.
Reliability = **shrinking blast radius**: zones, cells, shards, bulkheads.

**Resilience patterns**
| Pattern | Problem it solves |
|---|---|
| **Timeout** | never wait forever on a dependency |
| **Retry + exponential backoff + jitter** | transient blips — jitter avoids retry storms |
| **Circuit breaker** | stop hammering a dead dependency; fail fast, recover |
| **Bulkhead** | isolate resources (thread/conn pools) so one dep can't drain all |
| **Rate limit / load shedding** | drop excess load to protect the core |
| **Graceful degradation** | serve a cached/partial response vs total failure |
| **Backpressure** | signal upstream to slow down instead of collapsing |

**The danger: retry amplification.** A failing dependency + aggressive retries =
**metastable failure** — the retries *become* the load, so the system stays down even
after the root cause clears. Fix: backoff **with jitter**, retry budgets, circuit
breakers, and idempotency.

**Resource exhaustion classics**
- **CPU throttling:** hitting the CPU *limit* throttles (CFS), spiking latency without
  OOM — often mistaken for a code slowdown.
- **Memory:** exceeding the memory *limit* = **OOMKilled** (exit 137).
- **File descriptors / conn pool / thread pool:** silent ceilings; exhaustion looks
  like hangs, not crashes.
- **Disk / PID / inotify:** node-level exhaustion takes down *everything* on the node
  (e.g. inotify limits crashing kube-proxy → cluster-wide DNS/routing failure — hit
  this for real in Week 5 D2).

**Interview one-liner:** *"I design to shrink blast radius and add timeouts, jittered
backoff and circuit breakers — the failure mode I watch for is retry amplification /
metastable failure, where the retries themselves keep the system down."*

---

## D4 — Autoscaling under chaos (HPA + PDB)

**HPA (Horizontal Pod Autoscaler):** scales replica *count* on a metric (CPU by
default; custom/external via metrics adapters). Needs `metrics-server`.
`desiredReplicas = ceil(currentReplicas × currentMetric / targetMetric)`.
- Tune **stabilization windows** (`behavior.scaleDown.stabilizationWindowSeconds`) to
  stop **flapping** (rapid scale up/down). Scale up fast, scale down slow.
- **Requests matter:** HPA CPU % is relative to the **request**, so wrong requests =
  wrong scaling.

**VPA** (right-sizes requests/limits) — don't run VPA + HPA on the *same* CPU metric
(they fight). **Cluster Autoscaler / Karpenter** add *nodes* when pods are `Pending`.

**PDB (Pod Disruption Budget):** floor on availability during **voluntary**
disruptions (node drain, upgrades). `minAvailable: 2` or `maxUnavailable: 1`.
- Guards **voluntary** disruptions only (drains, rollouts) — **not** crashes/node
  failure (those are involuntary).
- **Trap:** `minAvailable` ≥ replica count → drains **block forever**; the node cordon
  hangs. Budget must leave room to move a pod.

**Under chaos the combo:** HPA gives headroom (more replicas), anti-affinity spreads
them across nodes, PDB caps how many go down at once during maintenance → a node loss
or drain stays within SLO.

**Interview one-liner:** *"HPA scales pods on load, Cluster Autoscaler adds nodes when
pods pend, PDB protects availability during voluntary disruptions — I scale up fast and
down slow to avoid flapping, and I make sure the PDB leaves room so drains don't
deadlock."*

---

## D5 — Mock incident end-to-end (via dashboards)

**Incident lifecycle:** Detect → Triage → Mitigate → Resolve → Learn.
- **Detect:** alert fires (SLO burn-rate / RED symptom), not a human noticing.
- **Triage:** declare severity, assign **Incident Commander (IC)**, open a comms
  channel. IC coordinates; doesn't fix hands-on.
- **Mitigate first, root-cause later:** stop the bleeding (rollback, scale, failover,
  feature-flag off) *before* diagnosing. **MTTR** is what users feel.
- **Diagnose with the golden signals:** RED (Rate/Errors/Duration) to *detect*, USE
  (Utilization/Saturation/Errors) to *localize*, traces to find the slow hop, logs for
  the why.

**Roles:** Incident Commander, Comms/Scribe, Ops/Subject-matter experts. Clear roles
= no chaos.

**Key metrics**
| Metric | Meaning |
|---|---|
| **MTTD** | mean time to **detect** |
| **MTTA** | mean time to **acknowledge** |
| **MTTR** | mean time to **restore** (the headline number) |
| **MTBF** | mean time between failures |

**Dashboard drill (using my Week 1/2 stack):** alert on RED burn-rate → open the SLO
dashboard (is the budget burning?) → RED panels (which endpoint erroring?) → USE panels
(CPU/mem/queue saturated?) → trace exemplar (which downstream hop?) → Loki logs
(trace_id correlated). That path *is* the mitigation decision tree.

**Interview one-liner:** *"Detect via SLO burn-rate alerts, mitigate before diagnosing
to protect MTTR, and use RED to detect + USE to localize + traces/logs to explain. An
Incident Commander coordinates while SMEs execute."*

---

## D6 — Blameless postmortem (5-whys + actions)

**Blameless = systems, not people.** Assume everyone acted reasonably with the info
they had; ask *how the system let a human make that choice*, not *who erred*. Blame
kills the honest reporting you need to actually fix things.

**Structure**
1. **Summary** — one paragraph: what, impact, duration.
2. **Impact** — users affected, SLO/error-budget burned, $/reputation.
3. **Timeline** — UTC, detection → mitigation → resolution (with MTTD/MTTR).
4. **Root cause** — **5 Whys** drilling past symptoms to a systemic cause.
5. **What went well / poorly / got lucky.**
6. **Action items** — each **owned, dated, tracked**; prefer systemic fixes
   (guardrails, automation, tests) over "be more careful".

**5 Whys example**
```
Site down →
1. Why? App pods OOMKilled.
2. Why? A query loaded an unbounded result set into memory.
3. Why? No pagination on that endpoint.
4. Why? Load tests never exercised large tenants.
5. Why? No perf-test data represented big customers.
→ Root cause: test data didn't model real scale.
→ Actions: add pagination (owner/date) + large-tenant load fixtures (owner/date)
           + memory-limit alert before OOM (owner/date).
```

**Error budget policy:** postmortems feed the budget — burn it down and you *freeze
features to spend on reliability*. That's the SRE feedback loop that makes reliability
a first-class, negotiated priority.

**Interview one-liner:** *"Blameless means fixing the system that allowed the mistake,
not the person; 5 Whys gets past the symptom to a systemic cause, and every action item
is owned, dated, and prefers a guardrail over 'try harder'."*

---

## D7 — Little's Law & capacity math

**Little's Law:** for a stable system,
$$L = \lambda \times W$$
- **L** = average number of requests *in the system* (concurrency / in-flight)
- **λ** (lambda) = arrival rate (throughput, req/s)
- **W** = average time in the system (latency, s)

**Why it's the most useful formula in SRE**
- **Concurrency needed:** `L = λ × W`. At 500 req/s with 200ms latency →
  `L = 500 × 0.2 = 100` in-flight requests → size thread/connection pools ≥ 100.
- **Max throughput from a pool:** `λ_max = L / W`. A 50-connection pool at 100ms →
  `50 / 0.1 = 500 req/s` ceiling — beyond that, requests **queue** and W rises.
- **Explains the latency knee:** once arrival rate exceeds service capacity, the queue
  grows, W grows, and (by the law) L grows — the hockey-stick from D1.

**Utilization & queueing intuition (M/M/1):** as utilization ρ → 1, wait time → ∞
non-linearly: $W \propto \dfrac{1}{1-\rho}$. Latency explodes *before* 100% util — the
reason to run at ~60–70% and why "we still have 20% CPU" isn't safety.

**USE this to size things:** thread pools, connection pools, HPA targets, and queue
depths all fall out of `L = λ × W` + a utilization target.

**Interview one-liner:** *"Little's Law, L = λW, ties throughput, latency and
concurrency: I use it to size connection/thread pools (L = λW) and to find a pool's max
throughput (λ = L/W). And because M/M/1 wait scales with 1/(1−ρ), latency blows up
before 100% utilization — so I target ~60–70% headroom."*

---

## Reliability cheat-sheet (one screen)
- Find capacity at the **latency knee** (open-model load test); encode SLOs as
  thresholds.
- **Chaos** = hypothesis on a steady-state SLI, small blast radius, auto-abort.
- Shrink **blast radius**; add timeout + jittered backoff + circuit breaker; fear
  **retry amplification / metastable failure**.
- **HPA** scales pods, **CA/Karpenter** scales nodes, **PDB** protects voluntary
  disruptions (don't let `minAvailable` deadlock drains); scale up fast, down slow.
- Incidents: **mitigate before diagnose**; RED to detect, USE to localize; protect
  **MTTR**; an **IC** coordinates.
- Postmortems are **blameless**; **5 Whys** → systemic cause; action items owned +
  dated; **error budget** governs feature-freeze.
- **Little's Law L = λW** sizes pools and explains the knee; latency ∝ 1/(1−ρ), so keep
  ~30–40% headroom.

