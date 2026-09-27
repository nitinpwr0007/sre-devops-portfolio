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


