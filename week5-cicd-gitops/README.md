# week5-cicd-gitops — CI/CD + GitOps

Build → test → scan → push (CI, D1), then GitOps continuous delivery with ArgoCD
(D2+). Personal GitHub account + GHCR only — no AWS, $0.

## Layout
```
app/                     tiny Flask app = the thing the pipeline ships
  app.py                 GET / (version) + GET /healthz
  test_app.py            pytest unit tests (the 'test' gate)
  requirements.txt
  Dockerfile             non-root, APP_VERSION baked in at build time
../.github/workflows/week5-ci.yml   the pipeline (lives at REPO ROOT, not here)
```

## D1 — GitHub Actions: build → test → scan → push

**Pipeline stages** (`week5-ci.yml`):
1. **test** job — installs deps, runs `pytest`. Nothing else runs if tests fail.
2. **build-scan-push** job (`needs: test`):
   - **build** the Docker image, tagged with the commit SHA.
   - **scan** it with trivy, failing on HIGH/CRITICAL (the security gate).
   - **push** to GHCR (`ghcr.io/<owner>/<repo>/week5-app`) — only on pushes to
     `main`, authenticated with the built-in `GITHUB_TOKEN`.

**Key ideas**
- The workflow lives at the **repo root** `.github/workflows/` (GitHub only runs
  it there); `paths:` scopes it to Week 5 app changes.
- **Scan before push** — never publish an image you haven't vetted.
- **Least privilege** — `permissions: contents:read, packages:write`.
- **Traceability** — image tagged with `github.sha`; the running container reports
  the same version via `APP_VERSION`.

### Run the same gates locally first
```bash
cd week5-cicd-gitops/app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                                   # test gate
docker build --build-arg APP_VERSION=local -t week5-app:local .   # build
docker run --rm -p 8080:8080 week5-app:local &                    # smoke test
curl -s localhost:8080/ ; echo             # {"app":"week5-cicd","version":"local"}
trivy image --severity HIGH,CRITICAL --ignore-unfixed week5-app:local  # scan
```

### See it in CI
After pushing, watch the run: `gh run watch` (or the Actions tab). A green run
publishes the image to **Packages** on the GitHub repo.

## D2 — ArgoCD on kind: GitOps auto-sync

**GitOps** = Git is the single source of truth for what runs in the cluster. A
controller (**ArgoCD**) watches a Git path and continuously **reconciles** the
cluster to match it. You stop running `kubectl apply` by hand; you `git push`,
and ArgoCD applies.

```
deploy/                  desired state ArgoCD keeps the cluster matched to
  deployment.yaml        week5-app (the image CI published), 1 replica, probes
  service.yaml           ClusterIP :80 -> :8080
argocd/
  application.yaml       the Application CR: watch deploy/ path, auto-sync to ns week5
```

**The reconcile loop**
```
Git (deploy/*.yaml)  --watched by-->  ArgoCD  --applies-->  cluster (ns week5)
        ^                                                        |
        \--------------- selfHeal reverts manual drift ----------/
```

`syncPolicy.automated`: `prune` deletes what you remove from Git; `selfHeal`
reverts manual `kubectl` edits back to the Git state.

### Setup (one time)
```bash
kind create cluster --name week5
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd rollout status deploy/argocd-server   # wait until Ready
```

### Register the app
```bash
kubectl apply -f week5-cicd-gitops/argocd/application.yaml
kubectl -n argocd get applications          # week5-app -> Synced / Healthy
kubectl -n week5 get pods                    # the app pod ArgoCD created
```

> NOTE: the GHCR package must be **public** (Packages -> week5-app -> settings ->
> change visibility) or the cluster can't pull it. Public is fine for a lab.

### Prove GitOps
Edit `deploy/deployment.yaml` `replicas: 1` -> `2`, commit, push. Within ~3 min
(or click Refresh in the UI) ArgoCD syncs and a 2nd pod appears — no `kubectl`.
Then try `kubectl -n week5 scale deploy/week5-app --replicas=5`: **selfHeal**
drags it back to 2, because Git says 2.

### See the UI
```bash
kubectl -n argocd port-forward svc/argocd-server 8081:443
# open https://localhost:8081  (user: admin)
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d ; echo
```

### Gotchas hit (and fixed) during D2

**1. kube-proxy CrashLoop → whole cluster networking broken (kind on colima).**
After installing ArgoCD many pods failed with `dial tcp 10.96.0.1:443: i/o timeout`
and `CreateContainerConfigError`. Red herring: looked like NetworkPolicy. Real
cause found in `kubectl -n kube-system logs kube-proxy-xxx`:
`fsnotify watcher init: too many open files` — the colima VM's inotify limits were
exhausted, killing kube-proxy, which broke ClusterIP routing (API + DNS) for
everything. Fix (runtime; not persistent across colima restarts):
```bash
colima ssh -- sudo sysctl -w fs.inotify.max_user_instances=8192
colima ssh -- sudo sysctl -w fs.inotify.max_user_watches=524288
kubectl -n kube-system delete pod -l k8s-app=kube-proxy
```
Lesson: `dial 10.96.0.1 i/o timeout` from many pods ⇒ suspect kube-proxy first,
check `kube-system` before app-level configs.

**2. New pod crash-looped on a busy node — liveness killed it during startup.**
When the 2nd replica landed on an already-loaded node, gunicorn booted too slowly
to answer `/healthz` within the liveness probe's default 1s timeout →
`connection refused` / `context deadline exceeded` → Kubernetes killed it (4
restarts). App logs showed `Handling signal: term` = killed, not crashed. Fix: add
a **startupProbe** (freezes liveness/readiness until boot completes) and raise
`timeoutSeconds` to 3. Lesson: never let a liveness probe run during startup — use
a startupProbe for slow-booting apps, not a bigger `initialDelaySeconds`.

## D3 — App-of-apps: one root manages many apps

D2 registered a single app by hand (`kubectl apply` the Application). That doesn't
scale. **App-of-apps** = one **root** Application whose Git source is a *folder of
other Application manifests*. Sync the root, and ArgoCD creates every child app.
Onboarding a new app becomes: drop one YAML in `gitops/apps/` and push.

```
gitops/
  root-app.yaml            the root Application (path -> gitops/apps, recurse)
  apps/
    week5-app.yaml         child -> deploy/  (ns week5)  — the D2 app, now a child
    hello-app.yaml         child -> hello/   (ns hello)  — a 2nd app
hello/
  deployment.yaml          reuses the week5-app image, APP_VERSION=hello
  service.yaml
```

**The tree ArgoCD builds**
```
root ──> week5-app ──> Deployment/Service in ns week5
    └──> hello-app ──> Deployment/Service in ns hello
```

### Adopt the D2 app + bootstrap everything
```bash
kubectl apply -f week5-cicd-gitops/gitops/root-app.yaml
kubectl -n argocd get applications      # root, week5-app, hello-app all -> Synced/Healthy
kubectl -n hello get pods                # the 2nd app the root created
```
The existing `week5-app` Application is **adopted** by the root (same name/spec, so
no workload restart) — its `deploy/` manifests and running pods are untouched.

### The payoff: onboard a 3rd app with one file
Add `gitops/apps/<newapp>.yaml`, commit, push. The root auto-syncs and creates it —
no `kubectl`. Delete that file and push: `prune` removes the app. The whole platform
is described declaratively in Git.

> Standalone D2 registration (`argocd/application.yaml`) is superseded by the child
> `gitops/apps/week5-app.yaml`. Kept in the repo only as the D2 teaching artifact —
> don't `kubectl apply` it anymore; the root owns week5-app now.

### Gotcha: prune orphans the workload without a finalizer
Deleting a child app's YAML pruned the child **Application** but left its **pods
running** — deleting an ArgoCD Application does NOT cascade-delete its resources by
default. Fix: add the cascade finalizer to every child Application so prune tears
down the whole app:
```yaml
metadata:
  finalizers:
    - resources-finalizer.argocd.argoproj.io
```

## D4 — Argo Rollouts: metric-gated canary (progressive delivery)

A plain Deployment does all-or-nothing rollouts. **Argo Rollouts** replaces it with
a `Rollout` that shifts traffic to a new version in **steps**, and — the key part —
runs an **analysis** between steps that decides *automatically* whether to keep
going (**auto-promote**) or roll back (**auto-abort**). This is *metric-gated
promotion*: a new version must prove itself against data before it earns more
traffic.

```
rollout/
  rollout.yaml             kind: Rollout, canary strategy, version via APP_VERSION env
  service.yaml             rollout-demo + rollout-demo-canary + rollout-demo-stable
  analysis-template.yaml   the gate: probe the canary, pass/fail on a successCondition
gitops/apps/rollout-app.yaml   child Application -> rollout/  (ns rollout, finalizer)
```

**The canary flow**
```
new version pushed
   │
setWeight 25 ─► [analysis: probe canary x3]
                     │ pass ─► setWeight 50 ─► 75 ─► 100  (canary becomes stable)
                     │ fail ─► ABORT: canary -> 0, stable keeps 100%
```

### Why a canary/stable Service split
So the gate judges the **new** version only. The Rollout is given `canaryService`
and `stableService`; Argo Rollouts injects the pod-template-hash into their
selectors, so `rollout-demo-canary` resolves to canary pods **only**. The analysis
probes that service — never the old stable pods.

### The analysis gate
`AnalysisTemplate` defines the check. Here the built-in **web** provider GETs the
canary and asserts the reported `version` matches the expected one — a deterministic
stand-in for a real metric. In production this block is `prometheus:` querying a
success-rate/latency query instead; the pass/fail mechanics are identical.
```yaml
metrics:
  - name: version-match
    initialDelay: 45s      # let the canary finish startup before sampling
    count: 3               # sample 3 times...
    interval: 10s          # ...10s apart (a metric window)
    failureLimit: 1        # tolerate 1 blip; 2+ bad samples -> abort
    successCondition: result == "{{args.expected-version}}"
    provider:
      web: { url: "http://{{args.service-name}}/", jsonPath: "{$.version}" }
```

### Setup (one time)
```bash
kubectl create namespace argo-rollouts
kubectl apply -n argo-rollouts --server-side --force-conflicts \
  -f https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml
kubectl -n argo-rollouts rollout status deploy/argo-rollouts
brew install argoproj/tap/kubectl-argo-rollouts    # the CLI plugin
```

### Demo A — good version auto-promotes
Bump `APP_VERSION` (e.g. `v2 -> v3`), commit, push, refresh the app. Watch:
```bash
kubectl argo rollouts get rollout rollout-demo -n rollout --watch
```
Canary comes up at 25%, the `AnalysisRun` waits 45s, samples 3× → `✔ Successful`
→ rollout **auto-promotes** through 50/75/100. No manual `promote`.

### Demo B — bad version auto-aborts
Set `APP_VERSION: broken` while the gate still expects the good version. The canary
honestly reports `broken`, every sample mismatches → `AnalysisRun ✖ Failed` →
`RolloutAborted`. Canary scales to 0; **stable keeps 100% the entire time**. The bad
release never gets past one pod, then is pulled. Recover by reverting `APP_VERSION`
to the good value and pushing.

Manual controls (when there's no gate, or to override one):
`kubectl argo rollouts promote <ro>` (advance one step), `promote --full` (skip to
100%), `abort <ro>` (roll back), `retry <ro>` (re-attempt an aborted rollout).

### Gotcha 1: node can't pull the controller image (corporate TLS proxy)
`argo-rollouts` controller stuck `ImagePullBackOff` with `x509: certificate signed
by unknown authority` pulling `quay.io`. The kind node's containerd doesn't trust
the corporate CA. Fix = pull on the host (which does trust it) and side-load into
the node so it never pulls:
```bash
docker pull --platform linux/arm64 quay.io/argoproj/argo-rollouts:v1.10.0
docker save  --platform linux/arm64 quay.io/argoproj/argo-rollouts:v1.10.0 -o /tmp/argo-rollouts.tar
kind load image-archive /tmp/argo-rollouts.tar --name week5
kubectl -n argo-rollouts delete pod -l app.kubernetes.io/name=argo-rollouts
```

### Gotcha 2: analysis started before the canary was Ready → false abort
First auto-promote attempt aborted a **good** version. Cause: the analysis ran
immediately after `setWeight: 25`, but the new pod needed ~45s to pass its
`startupProbe`. The web probe hit a Service with **no ready endpoints →
connection refused → failed sample**, and `failureLimit: 0` aborted on that single
blip. Fix: give the metric an `initialDelay` (warm-up window) and a `failureLimit`
> 0 so a startup blip doesn't nuke a healthy release. Lesson: an analysis gate must
wait for the canary to be Ready and tolerate transient noise, or you'll auto-abort
good deploys on timing alone.

## D5 — Blue-green with a pre-promotion gate

Canary (D4) shifts traffic *gradually*. **Blue-green** stands up the *entire* new
version alongside the old, then **flips 100% at once**. Two Services make it work:
`active` (what users hit) and `preview` (points at the new version before the flip).
A **pre-promotion analysis** probes the preview; only if it passes does `active`
flip to the new version. If it fails, the flip never happens — the old version keeps
serving. The safest rollback is never rolling forward.

```
bluegreen/
  rollout.yaml             kind: Rollout, strategy.blueGreen, prePromotionAnalysis
  services.yaml            bluegreen-active + bluegreen-preview
  analysis-template.yaml   the gate (namespaced copy of D4's version-check)
gitops/apps/bluegreen-app.yaml   child Application -> bluegreen/  (ns bluegreen)
```

**Canary vs blue-green**

| | Canary (D4) | Blue-green (D5) |
|---|---|---|
| Traffic shift | Gradual 25→50→75→100 | Instant 0→100 flip |
| Pods mid-rollout | Mostly old + few new | **Both full stacks** side-by-side |
| Test new version pre-cutover | Only via canary weight | **Yes — dedicated `preview` Service** |
| Cost | Low (few extra pods) | Higher (2× replicas briefly) |

**The flip flow**
```
new version pushed
   │
green stands up FULL SIZE (preview)  ── blue stays active ──►  users still on blue
   │
prePromotionAnalysis probes preview
   │ pass ─► active flips 0→100 to green (instant); blue scales down
   │ fail ─► NO flip; green scaled down; blue keeps serving 100%
```

Key `blueGreen` fields:
```yaml
strategy:
  blueGreen:
    activeService: bluegreen-active     # users hit this; Rollouts flips it on promote
    previewService: bluegreen-preview   # points at green before the flip
    autoPromotionEnabled: true          # flip automatically once the gate passes
    prePromotionAnalysis:               # the gate, run against preview BEFORE the flip
      templates: [{ templateName: version-check }]
      args: [ service-name=bluegreen-preview..., expected-version=<new> ]
```
(`postPromotionAnalysis` is the complement: it runs *after* the flip and, if it
fails, auto-rolls the `active` Service back to the old version — for issues that only
surface under real traffic.)

### Demo A — good version cuts over
Bump `APP_VERSION` and `expected-version` together (`v1 -> v2`), push. Green comes
up as `preview` (2 pods) next to blue (still `active`). While in preview you can prove
the isolation — port-forward each Service and see different versions at the same time:
```bash
kubectl -n bluegreen port-forward svc/bluegreen-active  8090:80   # v1 (blue)
kubectl -n bluegreen port-forward svc/bluegreen-preview 8091:80   # v2 (green)
```
The `AnalysisRun *-pre` passes → `active` flips to green (one step) → blue scales down.

### Demo B — bad version is blocked
Set `APP_VERSION: broken` but leave the gate expecting `v2`. Green stands up in
preview, the gate probes it, every sample mismatches → `AnalysisRun ✖ Failed` →
`RolloutAborted`. **The flip never happens** — the tree shows revision 3 as
`preview,delay:passed` but `ScaledDown`, while revision 2 (`v2`) stays `stable,active`
throughout. `curl` the active Service and it still returns `v2`. Recover by reverting
`APP_VERSION` to the good value and pushing.

Same manual controls as canary apply: `kubectl argo rollouts promote / abort / retry`.
With `autoPromotionEnabled: false` the rollout pauses in preview until you `promote`
manually — useful when you want a human to eyeball the preview before the flip.




