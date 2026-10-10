
#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
CHART = ROOT / "broken-chart"
TEMPLATES = CHART / "templates"

FILES = [
    CHART / "values.yaml",
    TEMPLATES / "backend.yaml",
    TEMPLATES / "gateway.yaml",
    TEMPLATES / "worker.yaml",
    TEMPLATES / "reporter.yaml",
    TEMPLATES / "metrics.yaml",
    TEMPLATES / "migrate-job.yaml",
    TEMPLATES / "rbac.yaml",
]

def run(cmd, *, check=True):
    print("\n$", " ".join(map(str, cmd)), flush=True)
    result = subprocess.run(cmd, cwd=ROOT)
    if check and result.returncode:
        raise RuntimeError(f"Command failed: {cmd}")
    return result.returncode

def read(path):
    if not path.exists():
        raise FileNotFoundError(f"Expected chart file not found: {path}")
    return path.read_text()

def write(path, content):
    path.write_text(content)

def replace_once(text, old, new, description):
    if new in text:
        print(f"Already applied: {description}")
        return text
    if old not in text:
        raise RuntimeError(
            f"Could not safely apply '{description}'. "
            f"Expected text was not found: {old!r}"
        )
    print(f"Applying: {description}")
    return text.replace(old, new, 1)

def main():
    # Safety checks: never modify the protected cluster-state directory.
    protected = ROOT / "cluster-state"
    original_protected = {}
    if protected.exists():
        for p in protected.rglob("*"):
            if p.is_file():
                original_protected[p.relative_to(ROOT)] = p.read_bytes()

    contents = {p: read(p) for p in FILES}

    # Back up all chart files before making any changes.
    backup = ROOT / (
        "chart-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    backup.mkdir()
    for path, content in contents.items():
        dest = backup / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
    print(f"Backups saved to: {backup}")

    # 1. Application port and gateway backend address.
    p = CHART / "values.yaml"
    s = contents[p]
    s = replace_once(
        s, "  port: 8080", "  port: 8081",
        "common application port 8081"
    )
    s = replace_once(
        s,
        'BACKEND_URL: "http://backend.default.svc:8080"',
        'BACKEND_URL: "http://backend.debug-lab.svc:8080"',
        "gateway backend URL"
    )
    s = replace_once(
        s, '      cpu: "2"', '      cpu: "50m"',
        "metrics CPU request"
    )
    s = replace_once(
        s, '      cpu: "4"', '      cpu: "200m"',
        "metrics CPU limit"
    )
    contents[p] = s

    # 2. Bind the pod-list permission to the reporter service account.
    p = TEMPLATES / "rbac.yaml"
    s = contents[p]
    s = replace_once(
        s, "    name: default",
        "    name: {{ .Values.reporter.serviceAccountName }}",
        "reporter RoleBinding subject"
    )
    if "namespace: {{ .Release.Namespace }}" not in s:
        raise RuntimeError(
            "RBAC namespace is not release-scoped; inspect rbac.yaml manually."
        )
    contents[p] = s

    # 3. Add numeric non-root UID to existing non-root security contexts.
    for p in FILES:
        if p.name in ("values.yaml", "rbac.yaml"):
            continue
        s = contents[p]
        lines = s.splitlines(keepends=True)
        out = []
        for i, line in enumerate(lines):
            out.append(line)
            if line.strip() == "runAsNonRoot: true":
                indent = line[:len(line) - len(line.lstrip())]
                next_line = lines[i + 1] if i + 1 < len(lines) else ""
                if next_line.strip() != "runAsUser: 10001":
                    out.append(indent + "runAsUser: 10001\n")
        contents[p] = "".join(out)

    # 4. Migration Job restart policy.
    p = TEMPLATES / "migrate-job.yaml"
    contents[p] = replace_once(
        contents[p],
        "restartPolicy: Always",
        "restartPolicy: OnFailure",
        "migration Job restart policy"
    )

    # 5. Explicit reporter namespace and service-account token automount.
    p = TEMPLATES / "reporter.yaml"
    s = contents[p]
    s = replace_once(
        s,
        "      serviceAccountName: {{ .Values.reporter.serviceAccountName }}\n",
        "      serviceAccountName: {{ .Values.reporter.serviceAccountName }}\n"
        "      automountServiceAccountToken: true\n",
        "reporter service-account token automount"
    )
    s = replace_once(
        s,
        "            - name: NAMESPACE\n"
        "              valueFrom:\n"
        "                fieldRef:\n"
        "                  fieldPath: metadata.namespace\n",
        "            - name: NAMESPACE\n"
        "              value: {{ .Release.Namespace | quote }}\n",
        "reporter namespace environment variable"
    )
    contents[p] = s

    # 6. Ensure the worker has a writable cache directory.
    p = TEMPLATES / "worker.yaml"
    s = contents[p]
    if "name: app-cache" not in s:
        pod_spec = "    spec:\n      containers:\n"
        if pod_spec not in s:
            raise RuntimeError(
                "Cannot safely add worker cache volume; inspect worker.yaml."
            )
        s = s.replace(
            pod_spec,
            "    spec:\n"
            "      volumes:\n"
            "        - name: app-cache\n"
            "          emptyDir: {}\n"
            "      containers:\n",
            1
        )
        container_env = "          env:\n"
        if container_env not in s:
            raise RuntimeError(
                "Cannot safely add worker cache mount; inspect worker.yaml."
            )
        s = s.replace(
            container_env,
            "          volumeMounts:\n"
            "            - name: app-cache\n"
            "              mountPath: /var/cache/app\n"
            "          env:\n",
            1
        )
        print("Applying: worker writable cache volume")
    else:
        print("Already applied: worker cache volume")
    contents[p] = s

    # Write only chart files.
    for path, content in contents.items():
        write(path, content)

    # Confirm the protected directory remains byte-for-byte unchanged.
    if protected.exists():
        for rel, original in original_protected.items():
            if (ROOT / rel).read_bytes() != original:
                raise RuntimeError(f"Protected file changed: {rel}")

    print("\nChart edits completed.")
    print("Review changes with: git diff -- broken-chart")

    # Validate before applying to the cluster.
    run(["helm", "lint", "./broken-chart"])
    run(["helm", "template", "debug-lab", "./broken-chart",
         "-n", "debug-lab"], check=True)

    # Apply and verify. A failed verification is reported, not hidden.
    run(["helm", "upgrade", "--install", "debug-lab",
         "./broken-chart", "-n", "debug-lab"])
    run(["kubectl", "-n", "debug-lab", "rollout", "status",
         "deployment/backend", "--timeout=90s"])
    run(["kubectl", "-n", "debug-lab", "rollout", "status",
         "deployment/gateway", "--timeout=90s"])
    run(["kubectl", "-n", "debug-lab", "rollout", "status",
         "deployment/worker", "--timeout=90s"])
    run(["kubectl", "-n", "debug-lab", "rollout", "status",
         "deployment/reporter", "--timeout=90s"], check=False)
    run(["kubectl", "-n", "debug-lab", "rollout", "status",
         "deployment/metrics", "--timeout=90s"])
    verify_code = run(["./scenario.sh", "verify"], check=False)

    print("\nBackup directory:", backup)
    if verify_code:
        print(
            "\nSome checks still fail. Review the verification output "
            "and reporter logs; do not assume the unknown JSON parsing "
            "cause has been fixed."
        )
        sys.exit(verify_code)

    print("\nAll scenario verification checks passed.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        print("No automatic commit was made.", file=sys.stderr)
        sys.exit(1)
