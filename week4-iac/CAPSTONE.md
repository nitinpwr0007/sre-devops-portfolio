# Week 4 Capstone — Module Design & State Strategy

A one-page synthesis of the whole week: how I structure Terraform modules, how I
manage state safely across environments, and how I keep infrastructure honest
(drift, policy, imports). Built hands-on against LocalStack ($0, no AWS account).

---

## 1. Module design

### The three-layer shape I used
```
root (main.tf)          composition — wires modules together, passes env values
  └─ module "vpc"       network:   vpc + public subnets + IGW + route table
  └─ module "security"  firewall:  security groups (for_each over a map)
  └─ module "service"   compute:   one EC2 per subnet (for_each over a map)
```
Each module owns **one concern**, exposes **inputs (variables)** and **outputs**,
and knows nothing about the others. The root is the only place that composes them
— `module.security` consumes `module.vpc.public_subnet_ids`, and so on. This is
the same "small, single-purpose, composable" instinct as good functions in code.

### `for_each` vs `count` — the decision that matters most
| | `count` (positional) | `for_each` (keyed) |
|---|---|---|
| Addressed by | index `[0]`, `[1]` | stable key `["web"]`, `["us-east-1a"]` |
| Remove the middle item | **shifts** every later item → recreate | only that key is destroyed, others untouched |
| Best for | truly identical, order-agnostic copies | a set/map of *named* things |

**Rule I follow:** if the things have identity (named SGs, per-AZ instances),
use `for_each` keyed by that identity. `count` only for anonymous N-of-a-kind.

### The `for_each` trap I hit (D3) and the rule it taught me
`for_each = toset(var.subnet_ids)` **failed in a fresh environment**:
> for_each set includes values derived from resource attributes that cannot be
> determined until apply

Terraform must know the **keys** of a `for_each` at *plan* time. Subnet IDs are
unknown until the VPC is applied, so they can't be keys. **Fix:** key by
something static (the AZ), and let the unknown be the *value*:
```hcl
# root: build an AZ-keyed map; keys known at plan, values may be unknown
subnet_ids = { for idx, id in module.vpc.public_subnet_ids : var.azs[idx] => id }
```
**Rule:** never `for_each` over unknown-at-plan values. Key on something stable
(name/AZ); the unknown belongs on the value side (which `for_each` allows).

---

## 2. State strategy

### Remote state + locking (D1)
- **Backend:** S3 bucket `tf-state`, one key per stack (`week4/vpc/terraform.tfstate`).
- **Locking:** DynamoDB table `tf-lock` (classic) — stops two applies from
  racing and corrupting state. Modern alternative: `use_lockfile = true` for
  S3-native locking (no DynamoDB needed). I kept DynamoDB for the interview value.
- **Bootstrap chicken-and-egg:** the bucket/table that *hold* remote state can't
  themselves live in remote state, so `bootstrap/` uses a **local** backend and
  runs first. Everything else uses the S3 backend.
- **Commit `.terraform.lock.hcl`** (provider version pins); **gitignore**
  `.terraform/` and `*.tfstate*` (state can contain secrets).

### Multi-environment isolation (D3)
Two knobs, kept deliberately separate:
- **`.tfvars` = the *inputs*** — `dev.tfvars` (small, 2 AZs, t3.micro) vs
  `prod.tfvars` (bigger, 3 AZs, t3.large, extra SG). Same code, different values.
- **workspaces = the *state***. `terraform workspace new dev` makes S3 auto-prefix
  the key with `env:/dev/…`, so three state files coexist in one bucket:
  ```
  week4/vpc/terraform.tfstate            (default)
  env:/dev/week4/vpc/terraform.tfstate   (dev)
  env:/prod/week4/vpc/terraform.tfstate  (prod)
  ```
  Changing `dev` can never touch `prod` — separate state = separate blast radius.

> Honest caveat: workspaces share one backend + one code path, which is fine for
> a lab. For real prod isolation many teams prefer **separate backends/accounts
> per env** (directory-per-env) so a blast radius or credential can't cross over.

---

## 3. Keeping infrastructure honest

### Drift (D4) — plan is a drift detector
`terraform plan` refreshes real state, diffs it against code, and prints
*"Objects have changed outside of Terraform."* Two ways to reconcile:
- **Code wins** → `terraform apply` reverts reality back to code (undo the drift).
- **Reality wins** → **codify** the change into `.tf`/`.tfvars` so the next plan
  says *No changes* (accept the drift). I did this for a legit bastion SSH rule.
- `terraform apply -refresh-only` syncs *state* to reality **without changing
  infra** — good for adopting computed/immutable attrs or auditing, but for
  config-managed attributes codifying is the durable fix.
- Gotcha: AWS SG ingress is an unordered **set**, so any membership change
  re-renders the whole block (a `-80/+80` pair shows up next to the real `-22`).

### Policy-as-code (D5) — shift-left security gate
A `pre-commit` hook runs on every commit touching `week4-iac/*.tf`:
`terraform fmt` → `tflint` → `trivy config` (fails on HIGH/CRITICAL). Bad config
(e.g. SSH `22` from `0.0.0.0/0` = AWS-0107 CRITICAL) is **blocked before it's
even committed**. The real skill was **triage**: *fix* what should be fixed
(bucket public-access-block + encryption) and *suppress with a reasoned
`#trivy:ignore` comment* what's intentional for the lab (all-egress, public
subnet, SSE-S3-not-KMS).

### Import + `moved` (D6) — evolve without destroying
- **`import {}`** adopts an existing (ClickOps / legacy) resource into state —
  `Plan: 1 to import`, no recreate. Turns orphaned infra into managed IaC.
- **`moved {}`** renames a resource's address (or moves it into/out of a module)
  as a pure **state relabel** — `0 to destroy`. Without it, a rename = destroy +
  create. Both are about **protecting live resources during change**.

---

## 4. Interview one-liners
- *"Modules are single-concern; the root composes them and is the only place that
  wires inputs to outputs."*
- *"`for_each` keys must be known at plan time — key on identity (name/AZ), never
  on an unknown resource attribute."*
- *"Remote state in S3 + a lock (DynamoDB or lockfile) so concurrent applies
  can't corrupt it; bootstrap the backend with a local state first."*
- *"`.tfvars` change the inputs, workspaces isolate the state — for hard prod
  isolation I'd use separate backends per account."*
- *"`plan` is my drift detector; reconcile by either applying (code wins) or
  codifying (reality wins)."*
- *"Policy-as-code in pre-commit shifts security left; `import`/`moved` let me
  adopt and refactor infra without destroy-and-recreate."*

---

## Artifacts this week
`bootstrap/` · `modules/{vpc,security,service}/` · `envs/{dev,prod}.tfvars` ·
`backend.tf` `providers.tf` · `.pre-commit-config.yaml` + `.tflint.hcl` ·
`d6-import.tf` — all validated against LocalStack, gated by trivy + tflint.
