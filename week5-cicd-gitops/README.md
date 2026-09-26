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

