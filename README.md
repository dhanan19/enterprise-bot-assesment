# Part 4 — Kubernetes Debug Lab

## Run and verify

Run commands from the lab directory:

```bash
helm lint broken-chart
helm template debug-lab broken-chart -n debug-lab
./scenario.sh up
./scenario.sh verify
```

Use `./scenario.sh reset` only when a reset is intended and its effects are understood. Do not modify `cluster-state/`, change the required image repository/tag, or delete workloads to conceal a failure. Review the chart changes before committing:

```bash
git diff -- broken-chart
```

## Resource requests and limits

The chart uses these values for the primary workloads:

| Resource | Request | Limit | Rationale |
|---|---:|---:|---|
| CPU | `50m` | `200m` | Small baseline for lightweight HTTP services; limits burst usage while keeping the configured CPU values modest for the lab. |
| Memory | `64Mi` | `128Mi` | A small starting allocation for the lightweight service image; the limit bounds memory use. These values should be validated against measured usage under representative load before production. |

The metrics workload uses the same `50m` CPU request and `200m` CPU limit, keeping it within the lab's stated resource constraints. These are lab values, not capacity recommendations for a production workload.

The application image is constrained by the assessment to `docker.io/ebinterview/eb-debug-app:1.0.1`. Do not change its repository or tag.

## Deliberately skipped and risks

- **Reporter root cause:** The latest shared verification showed 9 checks passing and 2 failing: reporter readiness and `/report` pod count. Reporter logs repeatedly showed `parse pod list: unexpected end of JSON input`. Independent API clients received HTTP 200 and valid JSON, so the exact reporter-side cause was not proven. I did not mask readiness or replace the required image. Risk: reporter functionality remains unavailable and the assessment is not fully passing.
- **Full production load testing:** The resource settings were not established through load testing. Risk: throttling, memory pressure, or unexpected latency at higher traffic.
- **Production hardening beyond the lab scope:** The chart has not been validated against a full production threat model, disaster-recovery plan, or multi-zone failure exercise. Risk: operational gaps may remain.

## What I would change for production

- Add readiness, liveness, and startup probes appropriate to each workload; alert on sustained probe failures.
- Set resource requests/limits from measured p95/p99 usage and load tests; add HPA only where scaling signals and application behavior support it.
- Add structured logs, metrics, traces, dashboards, and actionable alerts.
- Use least-privilege RBAC, short-lived ServiceAccount tokens, network policies, and a security context tested against the actual image.
- Manage TLS and secrets with an approved secret-management workflow; rotate credentials.
- Add CI checks for YAML/Helm linting, rendered-manifest policy validation, unit/integration tests, image scanning, and staged deployment/rollback.
- Test backup/restore, cluster upgrades, node disruption, capacity limits, and multi-zone resilience.
- Pin and regularly review controller/chart/image versions; document ownership, SLOs, runbooks, and rollback procedures.

## How I used AI

I used ChatGPT and Claude as assistants to help organize troubleshooting steps, interpret command output, and draft documentation. I ran the commands in my environment and reviewed the resulting output. AI suggestions were treated as hypotheses rather than proof; for example, the reporter JSON parsing root cause remains unresolved and is documented as such. I reviewed the proposed chart changes against the assessment constraints and did not use AI-generated claims as substitutes for observed evidence.
