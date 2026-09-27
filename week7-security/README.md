# Week 7 — Security & Supply Chain (interview notes)

> Notes-only week. A concise, interview-ready reference for image scanning, SBOM +
> signing, secret hygiene, least-privilege IAM, Kubernetes RBAC/NetworkPolicy/OPA,
> shift-left scan gates, and the DevSecOps pipeline story.

---

## D1 — Image scanning in CI (Trivy)

**Goal:** catch known-vulnerable OS packages and app dependencies **before** an image
ships. Shift-left = fail the build, not production.

**What Trivy scans:** OS packages (apk/apt/yum), language deps (npm/pip/go/maven),
IaC misconfig, secrets, and licenses — from an image, filesystem, or repo.

**CVE / severity basics**
- **CVE** = a single catalogued vulnerability (CVE-2024-xxxx); **CVSS** = its 0–10
  severity score → LOW/MEDIUM/HIGH/CRITICAL.
- Gate on **fixable CRITICAL/HIGH** first — `--ignore-unfixed` avoids failing on CVEs
  with no patch available yet (noise you can't action).

**CI gate**
```bash
# fail the pipeline on fixable HIGH/CRITICAL
trivy image --severity HIGH,CRITICAL --ignore-unfixed \
  --exit-code 1 ghcr.io/me/app:sha
```
```yaml
# GitHub Actions
- uses: aquasecurity/trivy-action@master
  with:
    image-ref: ghcr.io/me/app:${{ github.sha }}
    severity: HIGH,CRITICAL
    ignore-unfixed: true
    exit-code: '1'
```

**How you actually fix a vuln (in order of preference)**
1. **Bump the base image** — `python:3.12-slim` → latest patch, or switch to a
   **distroless**/`-alpine` minimal base (fewer packages = smaller attack surface).
2. **Update the vulnerable dependency** (pin the patched version).
3. **Rebuild** — a stale image re-inflates old CVEs; rebuild regularly even without
   code changes.
4. If unfixable + not exploitable in your context, **document an exception** (`.trivyignore` with a reason + expiry), don't silently mute.

**Interview one-liner:** *"I scan images in CI with Trivy, fail on fixable HIGH/CRITICAL
with `--ignore-unfixed`, and fix by bumping to a slim/distroless base and patching
deps — a smaller base is the cheapest vuln reduction there is."*

---

## D2 — SBOM (syft) + image signing (cosign)

**SBOM (Software Bill of Materials):** a machine-readable inventory of every component
+ version in an artifact (formats: **SPDX**, **CycloneDX**). It's the "ingredients
label" — when the next Log4Shell drops, you `grep` your SBOMs to know instantly what's
affected.
```bash
syft ghcr.io/me/app:sha -o spdx-json > sbom.json
grep -i log4j sbom.json            # "am I affected?" in seconds
```

**Signing with cosign (Sigstore):** proves an image came from *your* pipeline and
wasn't tampered with. **Keyless signing** uses OIDC (the CI's identity) + the public
**Rekor** transparency log — no private key to leak.
```bash
cosign sign     ghcr.io/me/app@sha256:...     # keyless, OIDC identity
cosign verify   ghcr.io/me/app@sha256:... \
  --certificate-identity-regexp '.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
cosign attest --predicate sbom.json --type spdx ghcr.io/me/app@sha256:...  # attach SBOM
```
- **Sign by digest (`@sha256:`), not tag** — tags are mutable, digests aren't.
- **Attestation** = a signed statement *about* an artifact (its SBOM, its scan result,
  its build provenance) — not just "this is signed" but "here's verified metadata".

**Enforce at admission:** a policy controller (**Kyverno** / **Sigstore policy-controller**
/ Gatekeeper) rejects unsigned images at the cluster door → only pipeline-built,
signed images run.

**SLSA:** a supply-chain integrity framework; higher levels require signed
**provenance** (who built what, from which source, with which builder) — cosign
attestations are how you satisfy it.

**Interview one-liner:** *"Syft generates an SBOM so I can answer 'am I affected?'
instantly; cosign keyless-signs the image by digest and attaches the SBOM as an
attestation; an admission controller then refuses to run anything unsigned — that's the
provenance chain (SLSA)."*

---

## D3 — Secret hygiene (gitleaks + secret managers)

**Rule 0: secrets never live in Git.** Even if you `git rm` them, they persist in
history — a leaked key must be **rotated**, not just deleted.

**gitleaks:** regex/entropy scanner for committed secrets. Run it as a **pre-commit
hook** (block before it's ever committed) *and* in CI (catch what slipped through).
```bash
gitleaks detect --source . --redact          # scan history
gitleaks protect --staged                    # pre-commit: block staged secrets
```

**Where secrets *should* live**
| Option | Notes |
|---|---|
| **AWS Secrets Manager / SSM Parameter Store** | managed, IAM-scoped, auto-rotation (SM) |
| **HashiCorp Vault** | dynamic short-lived secrets, leasing, broad backends |
| **k8s External Secrets Operator** | syncs from SM/Vault → a k8s Secret (only a *reference* in Git) |
| **Sealed Secrets** (Week 5 D6) | encrypted blob safe to commit; no external store |

**k8s Secret reality check:** k8s Secrets are **base64, not encrypted** at rest by
default — enable **encryption-at-rest** (KMS provider) on etcd, and use RBAC to limit
who can `get secrets`.

**Best practices:** short-lived/rotated credentials, least privilege on the secret,
audit access, prefer **workload identity / IRSA** (no long-lived keys at all) over
static keys.

**Interview one-liner:** *"gitleaks runs pre-commit and in CI so secrets never reach
Git; real secrets live in Secrets Manager/Vault pulled via External Secrets or IRSA;
and if one leaks the only fix is rotation, because Git history is forever."*

---

## D4 — Least-privilege IAM

**Principle of least privilege:** grant the minimum permissions needed, nothing more —
and prefer **temporary** credentials over long-lived keys.

**IAM policy anatomy:** `Effect` (Allow/Deny), `Action`, `Resource`, `Condition`.
- **Explicit Deny always wins** over any Allow.
- Scope `Resource` to specific ARNs, not `"*"`; scope `Action` to specific verbs, not
  `s3:*`.
- Use **Conditions** (e.g. `aws:SourceIp`, `aws:MultiFactorAuthPresent`,
  `aws:PrincipalTag`) to tighten further.

```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject"],
  "Resource": "arn:aws:s3:::my-bucket/reports/*",
  "Condition": { "Bool": { "aws:SecureTransport": "true" } }
}
```

**Roles over users/keys:** assume a **role** (STS temporary creds) instead of static
access keys. For workloads:
- **EKS → IRSA / EKS Pod Identity** — a pod assumes an IAM role via a projected OIDC
  token; **no keys in the pod**.
- **EC2 → instance profile**; **Lambda → execution role**.

**Verify before you ship**
- **IAM Policy Simulator** — test "can principal X do action Y on resource Z?" without
  live calls.
- **Access Analyzer** — flags resources shared externally + can *generate* a
  least-priv policy from CloudTrail usage.
- **Permissions boundaries** cap the max a role can ever have; **SCPs** (Org level) set
  guardrails no account can exceed.

**Interview one-liner:** *"Least privilege = specific Actions on specific Resource ARNs,
temporary role creds not static keys, IRSA for pods; explicit Deny wins, and I validate
with the Policy Simulator and Access Analyzer before rollout."*

---

## D5 — Kubernetes RBAC + NetworkPolicy + OPA/Gatekeeper

**RBAC (who can do what to the API):**
- **Role / ClusterRole** = a set of allowed verbs on resources (namespaced vs
  cluster-wide).
- **RoleBinding / ClusterRoleBinding** = grants a Role to a subject (user, group,
  **ServiceAccount**).
- RBAC is **additive, allow-only** (no deny rules) — you grant, you don't subtract.
- Give each workload its **own ServiceAccount** with a minimal Role; never use the
  `default` SA with broad rights; avoid `cluster-admin`.

**NetworkPolicy (who can talk to whom):**
- Default k8s networking is **flat — every pod can reach every pod**. NetworkPolicy is
  how you segment (needs a CNI that enforces it: Calico/Cilium).
- Start with a **default-deny** ingress/egress in a namespace, then allow only the
  flows you need → **micro-segmentation**, shrinks lateral-movement blast radius.
```yaml
# default-deny all ingress in a namespace
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: default-deny-ingress, namespace: app }
spec:
  podSelector: {}
  policyTypes: [Ingress]
```

**OPA/Gatekeeper (policy-as-code admission):** a validating admission controller that
rejects non-compliant resources at apply time. Policies (Rego for OPA; Kyverno as a
YAML alternative) enforce org rules:
- no `:latest` tags, no privileged/`hostNetwork`/root containers, required
  requests/limits, required labels/probes, only approved registries, disallow
  `NodePort`, etc.
- **Audit mode** first (report violations) → then **enforce** (block) so you don't
  break existing workloads.

**Pod-level hardening:** `securityContext` — `runAsNonRoot`, drop all capabilities,
`readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`; enforce via **Pod
Security Admission** (baseline/restricted) or Gatekeeper.

**Interview one-liner:** *"RBAC controls API access (allow-only, per-ServiceAccount
least privilege), NetworkPolicy segments pod-to-pod traffic starting from default-deny,
and OPA/Gatekeeper enforces policy-as-code at admission — I roll policies out in audit
mode before enforce."*

---

## D6 — Dependency + IaC scanning & threat modeling

**Shift-left scan gates (defense in depth across the pipeline):**
| Stage | Tool | Catches |
|---|---|---|
| Pre-commit | gitleaks | secrets |
| Deps (SCA) | `npm audit` / Trivy / Grype / Dependabot | vulnerable libraries |
| IaC | tfsec / Checkov / Trivy config / KICS | misconfigured Terraform/K8s/CFN |
| Image | Trivy / Grype | OS + app CVEs |
| SAST | CodeQL / Semgrep | insecure code patterns |
| DAST | ZAP | runtime vulns against a running app |

- **SCA** (Software Composition Analysis) = *your dependencies*; **SAST** = *your
  code*; **DAST** = *the running app*. You want all three.
- **IaC misconfig examples:** public S3 bucket, `0.0.0.0/0` security group, unencrypted
  volume, no logging — caught statically before `apply`.

**Threat modeling — STRIDE:**
| Letter | Threat | Mitigation theme |
|---|---|---|
| **S** | Spoofing | authentication |
| **T** | Tampering | integrity (signing, checksums) |
| **R** | Repudiation | logging / audit trails |
| **I** | Information disclosure | encryption, access control |
| **D** | Denial of service | rate limits, quotas, autoscaling |
| **E** | Elevation of privilege | least privilege, authorization |

**Process:** diagram the system + **trust boundaries** → enumerate threats per
component (STRIDE) → rank by risk → design mitigations → track as action items. Do it
early; cheapest to fix at design time.

**OWASP Top 10** = the checklist for web-app risks (injection, broken access control,
broken auth, SSRF, security misconfig, vulnerable components…). Know it by name.

**Interview one-liner:** *"Defense in depth = layered scan gates — gitleaks, SCA on
deps, tfsec/Checkov on IaC, Trivy on images, SAST/DAST on code — plus STRIDE threat
modeling at design time around trust boundaries so I mitigate before writing code."*

---

## D7 — DevSecOps pipeline (the whole story)

**DevSecOps = security as a built-in stage, not a gate at the end.** "Shift left":
find issues where they're cheapest to fix — in the IDE/PR, not in prod.

**A hardened pipeline, start to finish**
```
commit ─▶ pre-commit: gitleaks
   │
   PR  ─▶ SAST (CodeQL) · SCA (deps) · IaC scan (tfsec/Checkov) · unit tests
   │
 build ─▶ build image (pinned/distroless base, non-root)
   │
  scan ─▶ Trivy image (fail HIGH/CRITICAL fixable) · syft SBOM
   │
  sign ─▶ cosign keyless sign by digest + attest SBOM (Rekor log)
   │
  push ─▶ registry (immutable digest)
   │
 deploy ─▶ ArgoCD (GitOps) ─▶ admission: verify signature + OPA/Gatekeeper policy
   │
   run ─▶ NetworkPolicy default-deny · RBAC least-priv SA · runtime scan
```

**Guiding principles**
- **Least privilege everywhere** — CI tokens (`contents:read`, `packages:write`), IAM
  roles, k8s SAs.
- **Immutability & provenance** — sign by digest, verify at admission, keep the SBOM.
- **Fail closed on fixable criticals**, but manage exceptions with expiry so the gate
  stays credible (no permanent mutes).
- **Everything as code + audited** — policies, IAM, network rules all in Git, reviewed,
  logged.
- **Security is shared ownership**, not a separate team's final sign-off.

**Interview one-liner:** *"DevSecOps bakes security into every pipeline stage — secret
scan, SCA, IaC scan, SAST at the PR; image scan + SBOM + cosign sign at build; signature
+ OPA verification at admission; least privilege and default-deny at runtime — so a bad
artifact fails early and only signed, policy-compliant images ever run."*

---

## Security cheat-sheet (one screen)
- **Trivy** scan images in CI; fail fixable HIGH/CRITICAL; fix via slim/distroless base
  + dep bumps.
- **SBOM (syft)** = ingredient label → instant "am I affected?"; **cosign** keyless-sign
  by **digest** + attest; verify at admission (SLSA provenance).
- Secrets **never in Git** (gitleaks pre-commit + CI); real ones in SM/Vault via
  External Secrets/IRSA; a leak = **rotate**.
- IAM least privilege: specific Action+Resource, **temporary role creds not keys**,
  IRSA for pods, explicit **Deny wins**, validate with Policy Simulator.
- k8s: **RBAC** (allow-only, per-SA) + **NetworkPolicy** (default-deny segmentation) +
  **OPA/Gatekeeper** (policy-as-code, audit→enforce) + non-root securityContext.
- Layered scan gates: **SCA** (deps) · **SAST** (code) · **DAST** (running) · **IaC**
  (tfsec/Checkov); **STRIDE** threat model at design time; know **OWASP Top 10**.
- **DevSecOps** = shift-left, least privilege everywhere, immutable+signed artifacts,
  fail closed on fixable criticals, security is shared ownership.

