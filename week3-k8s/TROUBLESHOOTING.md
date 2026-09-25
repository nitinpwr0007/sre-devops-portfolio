# Kubernetes Troubleshooting Cheat-Sheet

> Week 3 capstone. Failure modes I induced and diagnosed on a 3-node `kind`
> cluster (1 control-plane + 2 workers), plus the resiliency/recovery ops and
> LGTM-on-k8s notes. Same primitives as EKS — only the node autoscaler differs.

---

## 0. The 30-second triage flow

Always start wide, then narrow:

```bash
kubectl get pods -o wide                 # STATUS + which node
kubectl describe pod <pod>               # Events + Last State (bottom = newest)
kubectl logs <pod>                       # current process output
kubectl logs <pod> --previous            # output of the crashed instance
kubectl get events --sort-by=.lastTimestamp | tail -20
```

Golden rules:
- **`describe` Events** answer *"why won't it schedule / start / pull?"*
- **`logs --previous`** answer *"why did it crash?"*
- A `Pending` pod is a **scheduler/storage** problem; a `CrashLoopBackOff` pod is an **app/runtime** problem. Never confuse the two.

---

## 1. Pod-level failure modes (from `break/`)

| Symptom (`STATUS`) | Root cause | Diagnose | Fix |
|---|---|---|---|
| `CrashLoopBackOff` / `Error` | app exits non-zero, kubelet backs off | `describe` → Last State: Terminated, Exit Code; `logs --previous` | fix the app / config that makes it exit |
| `ImagePullBackOff` / `ErrImagePull` | image tag/registry wrong, can't pull | `describe` → Events "Failed to pull ... not found" | correct image name/tag; check registry creds |
| `OOMKilled` | process exceeds memory **limit** | `get pod -o jsonpath='{.status.containerStatuses[0].lastState.terminated.reason}'` → `OOMKilled` | raise memory limit **or** fix the leak |
| `Pending` (compute) | no node has the requested cpu/mem | `describe pod` → `FailedScheduling: Insufficient cpu` | lower requests, add nodes, or fix taints |
| DNS fails, pods healthy | CoreDNS down / NetworkPolicy blocks :53 | healthy `kube-dns` Service but **empty Endpoints** | restore CoreDNS replicas; check netpol |
| `Pending` (storage) | PVC never bound | `describe **pvc**` → `storageclass ... not found` | point PVC at a real StorageClass |

### The two traps that look identical
- **Two `Pending`s:** compute (`describe pod` → Insufficient cpu) vs storage
  (`describe pvc` → unbound). Same STATUS, different object to inspect.
- **DNS outage fingerprint:** `kube-dns` (the *Service*, stable ClusterIP)
  survives, but its **Endpoints go empty** because `coredns` (the *pods*) are
  gone. `EAI_AGAIN`/SERVFAIL = infra down; `NXDOMAIN` = your name is wrong.
  Reaching a ClusterIP **by IP but not by name** ⇒ it's DNS, stop debugging the app.

### Handy one-liners
```bash
# OOM reason:
kubectl get pod <pod> -o jsonpath='{.status.containerStatuses[0].lastState.terminated.reason}'
# Why unschedulable:
kubectl get event --field-selector involvedObject.name=<pod> | grep -i schedul
# DNS health (the empty-endpoints tell):
kubectl -n kube-system get endpoints kube-dns
kubectl -n kube-system get pods -l k8s-app=kube-dns
# PVC binding:
kubectl get pvc; kubectl describe pvc <claim> | grep -A3 Events
```

---

## 2. Resiliency & recovery ops (from D6)

### Node drain / cordon (every cluster upgrade does this)
```bash
kubectl cordon <node>                     # stop NEW pods landing here
kubectl drain <node> --ignore-daemonsets --delete-emptydir-data   # evict existing
kubectl uncordon <node>                   # allow scheduling again (heal)
```
- `--ignore-daemonsets` — DaemonSet pods (kube-proxy/CNI) can't be evicted.
- Drain respects **PodDisruptionBudgets**: it brings a replacement Ready before
  evicting the next replica, and will **block** if honoring the budget is impossible.

### PodDisruptionBudget (`manifests/pdb.yaml`)
- `minAvailable: 1` (or `maxUnavailable: 1`) = the floor during **voluntary**
  disruptions (drain, upgrade). It does **not** protect against a node crash.
- Blocked-drain message to expect: `Cannot evict pod ...: The disruption budget
  needs 1 healthy pod and has 1 currently`. That's the PDB working.

### Spreading replicas (`manifests/deployment.yaml`)
- `topologySpreadConstraints` (modern) + `podAntiAffinity` (classic) over
  `kubernetes.io/hostname` keep replicas on different nodes so one node loss
  isn't an outage. Use **soft** (`ScheduleAnyway` / `preferred`) in small
  clusters so a drain can still pack pods onto the surviving node.

### Taints & tolerations (dedicated node pools)
```bash
kubectl taint nodes <node> dedicated=lgtm:NoExecute   # add (bouncer)
kubectl taint nodes <node> dedicated=lgtm:NoExecute-  # remove (trailing -)
```
- Effects: `NoSchedule` = block new pods · `PreferNoSchedule` = soft avoid ·
  `NoExecute` = block **and evict** existing untolerated pods.
- **Taint** = the node repels; **toleration** = the pod's pass to land there.

---

## 3. LGTM-on-Kubernetes ops notes

The observability stack (Loki, Grafana, Tempo, Mimir) is just StatefulSets +
Services + PVCs, so every failure mode above applies. Extra gotchas:

- **StatefulSet won't start → check the PVC first.** #1 cause of a stuck
  Loki/Mimir ingester is an unbound PVC (`get pvc` shows `Pending`). See §1.
- **`WaitForFirstConsumer` StorageClass** (kind default `standard`,
  `rancher.io/local-path`): a lone PVC stays `Pending` until a pod consumes it —
  that's *normal*, not a bug.
- **Node loss & stateful pods:** a StatefulSet pod is pinned to its PVC. On a
  real node failure the pod reschedules only where its volume can attach
  (topology-aware). Spread + PDB keep quorum during rolling upgrades.

### Multi-tenancy — Loki `X-Scope-OrgID`
- Loki/Mimir isolate tenants by the **`X-Scope-OrgID`** HTTP header. No header
  (multitenancy disabled) ⇒ everything lands in tenant `anonymous`.
- A write with `X-Scope-OrgID: team-a` is invisible to a read with
  `X-Scope-OrgID: team-b` — a very common "my logs are missing" cause: the
  Grafana datasource queries a different tenant than the shipper wrote to.
- Per-tenant **retention & limits** (retention period, ingestion rate,
  max active series/streams) are set in the Loki/Mimir `limits_config` /
  per-tenant overrides — the guardrails against one noisy tenant.

### Cardinality (the cost & stability killer)
- **Cardinality = number of unique label combinations.** High-cardinality
  labels (user IDs, request IDs, timestamps, pod IPs) explode series/streams,
  blow up memory, and slow queries.
- Keep labels **low-cardinality and bounded** (env, service, route, status
  class). Put the high-cardinality stuff in the **log line / trace**, never in a
  metric or Loki stream label.

---

## 4. Quick reference — kubectl I reach for most

```bash
kubectl get pods -A -o wide                 # everything, everywhere
kubectl describe <kind> <name>              # Events are at the bottom
kubectl logs -f <pod> [-c <container>] [--previous]
kubectl get events --sort-by=.lastTimestamp
kubectl top nodes ; kubectl top pods        # needs metrics-server
kubectl rollout status/history/undo deploy/<name>
kubectl get endpoints <svc>                 # empty = Service has no healthy backends
kubectl exec -it <pod> -- sh                # poke from inside
kubectl get <kind> <name> -o yaml           # the real, full spec + status
```
