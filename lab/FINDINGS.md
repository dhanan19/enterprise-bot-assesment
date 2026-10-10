# Findings --- Part 4 debug lab

> Draft based on the terminal output shared in this conversation. Keep
> only claims supported by your actual session recording and `git diff`.
> The reporter issue is still unresolved; do not present a hypothesis as
> a confirmed cause.

Before submission, follow the assessment instructions to record the
session with `script -q part4-session.log` or
`asciinema rec part4-session.cast`, and commit the recording alongside
this file. Do not overwrite an existing recording without checking it.

------------------------------------------------------------------------

## Defect 1 --- Common application port

**Symptom** (actual output observed):

The image metadata showed:

``` text
"ExposedPorts": {
  "8081/tcp": {}
}
```

The chart's `values.yaml` had a malformed boundary between the port
setting and the backend section in the earlier diff:

``` diff
-  port: 8081backend:
+  port: 8081
+
+backend:
```

**Cause** (root cause):

The `common.port` value was malformed in the original chart content, and
the chart needed a clean `common.port: 8081` value matching the app
image's port.

**Fix**:

Set `common.port: 8081` and ensure `backend:` begins as a separate YAML
key. Kept the required image and tag unchanged.

**How I found it**:

Inspected `broken-chart/values.yaml`, reviewed
`git diff -- broken-chart`, and inspected the image metadata with
`docker exec demo-control-plane crictl inspecti docker.io/ebinterview/eb-debug-app:1.0.1`.
The image metadata confirmed port `8081/tcp`.

------------------------------------------------------------------------

## Defect 2 --- Gateway upstream URL

**Symptom** (actual output observed):

The gateway check was initially among the failing probes during
troubleshooting. After configuration changes, the verifier reported:

``` text
PASS  gateway /status reports backend=ok
```

**Cause** (root cause):

The gateway's configured backend URL needed to target the Kubernetes
backend Service and its Service port.

**Fix**:

Set the gateway environment value to:

``` yaml
BACKEND_URL: "http://backend.debug-lab.svc:8080"
```

Kept the gateway Service port at `80` and the backend Service port at
`8080`, with their target ports using the app port.

**How I found it**:

Inspected `broken-chart/values.yaml` and tested the gateway status
endpoint from inside the cluster. The later `./scenario.sh verify`
output showed the gateway check passing.

------------------------------------------------------------------------

## Defect 3 --- Reporter RoleBinding subject

**Symptom** (actual output observed):

The intended reporter identity needed permission to list pods. The
following check passed after the RBAC configuration was corrected:

``` text
PASS  ServiceAccount debug-lab/reporter can list pods
```

The earlier investigation also reported that the reporter lacked `watch`
permission and received a `403`; preserve the exact original output from
the session recording if documenting that finding.

**Cause** (root cause):

The RoleBinding subject must refer to the reporter ServiceAccount in the
release namespace. The reporter may also require `watch` if its actual
API request uses a watch operation; only claim this additional cause if
the recorded `403` confirms it.

**Fix**:

Use the configured reporter ServiceAccount and release namespace in
`broken-chart/templates/rbac.yaml`:

``` yaml
subjects:
  - kind: ServiceAccount
    name: {{ .Values.reporter.serviceAccountName }}
    namespace: {{ .Release.Namespace }}
```

Add `watch` to the Role's pod verbs only if supported by the captured
permission-denied output and the application's request behavior.

**How I found it**:

Inspected `broken-chart/templates/rbac.yaml` and ran the assessment's
ServiceAccount permission check. The current chart shows the templated
subject, and verification reports that the reporter can list pods.

------------------------------------------------------------------------

## Defect 4 --- Reporter non-root security context

**Symptom** (actual output observed):

The earlier event recorded in `part4-session.log` included:

``` text
Error: container has runAsNonRoot and image has non-numeric user (nonroot), cannot verify user is non-root
```

**Cause** (root cause):

The image metadata specifies the username `nonroot`, rather than a
numeric UID that Kubernetes can validate against `runAsNonRoot: true`.

**Fix**:

Set an explicit numeric UID in the reporter pod security context:

``` yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
```

The current reporter template also sets `readOnlyRootFilesystem: true`,
disables privilege escalation, and drops all capabilities. Keep these
hardening settings if compatible with the assessment.

**How I found it**:

Read the pod events in the session output and inspected the image
metadata using `crictl inspecti`. The metadata showed
`"User": "nonroot"`. The numeric UID addresses the Kubernetes validation
error without changing the required image.

------------------------------------------------------------------------

## Defect 5 --- Metrics CPU resources

**Symptom** (actual output observed):

The investigation identified the metrics workload's CPU settings as
exceeding the lab's intended CPU resource constraints. Preserve the
exact LimitRange/admission error from the session recording here if it
was captured; it is not reproduced in the chat history supplied for this
draft.

**Cause** (root cause):

The metrics pod's CPU request and/or limit exceeded the namespace's
configured resource constraints.

**Fix**:

Use the values currently shown in `broken-chart/values.yaml`:

``` yaml
resources:
  requests:
    cpu: "50m"
    memory: "64Mi"
  limits:
    cpu: "200m"
    memory: "128Mi"
```

**How I found it**:

Compared the metrics workload resources with the namespace resource
constraints and reviewed the values file. The latest verification
reports:

``` text
PASS  deployment metrics: 1/1 ready
```

Before submitting, include the original resource-limit output from the
recording so the cause is evidenced rather than inferred.

------------------------------------------------------------------------

## Defect 6 --- Migration Job restart policy

**Symptom** (actual output observed):

The migration Job completed successfully after the chart fixes:

``` text
PASS  migrate Job completed
```

The original Job validation/admission error is not included in the
conversation history available for this draft. Paste the exact original
error from the session recording before claiming a specific root cause.

**Cause** (root cause):

A Kubernetes Job's pod template cannot use `restartPolicy: Always`; it
must use `OnFailure` or `Never`. Confirm that the original template
contained `Always` before stating this as the observed cause.

**Fix**:

Set the Job pod template to a supported policy, typically:

``` yaml
restartPolicy: OnFailure
```

**How I found it**:

Inspected `broken-chart/templates/migrate-job.yaml` and verified the Job
state with `./scenario.sh verify`, which reported
`PASS migrate Job completed`. Include the exact original Job error from
the recording to fully substantiate this finding.

------------------------------------------------------------------------

## Outstanding issue --- Reporter readiness and `/report`

The latest verification output shared in the conversation was:

``` text
==> verifying goal state in namespace debug-lab
  PASS  migrate Job completed
  PASS  deployment backend: 1/1 ready
  PASS  deployment gateway: 1/1 ready
  PASS  deployment worker: 1/1 ready
  FAIL  deployment reporter: 0/1 ready
  PASS  deployment metrics: 1/1 ready
  PASS  no pods in CrashLoopBackOff
  PASS  ServiceAccount debug-lab/reporter can list pods
  PASS  backend answers on http://backend:8080/healthz
  PASS  gateway /status reports backend=ok
  FAIL  reporter /report does not return a pod count

2 check(s) failing, 9 passing.
```

The reporter logs repeatedly showed:

``` text
pod list failed: parse pod list: unexpected end of JSON input
GET /healthz -> 503
```

An independent Python client successfully queried the Kubernetes API and
reported HTTP `200`, valid JSON, and `9` pod items. A separate curl
diagnostic also received HTTP `200` and `129873` bytes, although its
`jq` command failed because `jq` was not installed in that diagnostic
image.

The required reporter image is
`docker.io/ebinterview/eb-debug-app:1.0.1`; its image metadata showed
entrypoint `/eb-debug-app`, exposed port `8081/tcp`, and configured user
`nonroot`. The repository's `service/app.py` is a separate Python sample
and does not implement `/report` or Kubernetes pod listing.

**Conclusion:** The reporter's JSON parsing failure remains unresolved.
Response truncation and a `kubectl run -i --rm` attach race were
hypotheses, not proven root causes in the supplied evidence. Do not
claim either as the confirmed cause. The next tests would be to run the
attach-race test using the verifier's exact flags, preserve its full
output, and capture the reporter's API request behavior if feasible
without changing the required image.

## Submission checklist

-   Replace any missing original symptom/admission output above with the
    exact output from the recording.
-   Confirm each described change in `git diff -- broken-chart`.
-   Do not change `image.repository` or `image.tag`.
-   Do not modify anything under `cluster-state/`.
-   Do not delete workloads to hide failing checks.
-   If the reporter remains unresolved, state that plainly and include
    the next test you would run.