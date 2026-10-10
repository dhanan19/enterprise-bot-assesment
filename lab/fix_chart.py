
from pathlib import Path
import shutil
import re
import sys

ROOT = Path("broken-chart")
VALUES = ROOT / "values.yaml"
RBAC = ROOT / "templates" / "rbac.yaml"
REPORTER = ROOT / "templates" / "reporter.yaml"


def backup(path):
    backup_path = path.with_suffix(path.suffix + ".bak")
    if not backup_path.exists():
        shutil.copy2(path, backup_path)
    print(f"Backup: {backup_path}")


def replace_once(text, old, new, description):
    count = text.count(old)
    if count != 1:
        raise ValueError(
            f"{description}: expected one match, found {count}"
        )
    return text.replace(old, new, 1)


def main():
    for path in (VALUES, RBAC, REPORTER):
        if not path.is_file():
            sys.exit(f"ERROR: Missing file: {path}")

    values = VALUES.read_text()
    rbac = RBAC.read_text()
    reporter = REPORTER.read_text()

    # 1. Set common application port to 8081.
    match = re.search(
        r"(?m)^common:\s*\n((?:^[ \t]+.*\n)*)",
        values,
    )
    if not match:
        sys.exit("ERROR: common section not found in values.yaml")

    common = match.group(0)
    updated_common = re.sub(
        r"(?m)^([ \t]+port:\s*)\d+\s*$",
        r"\g<1>8081",
        common,
        count=1,
    )
    if updated_common == common:
        if re.search(r"(?m)^[ \t]+port:\s*8081\s*$", common):
            print("Port already set to 8081")
        else:
            sys.exit("ERROR: Could not find common.port")
    else:
        values = values.replace(common, updated_common, 1)
        print("Updated common.port to 8081")

    # 2. Bind RoleBinding to the configured reporter ServiceAccount.
    rbac = replace_once(
        rbac,
        "    name: default\n",
        "    name: {{ .Values.reporter.serviceAccountName }}\n",
        "Reporter RoleBinding subject",
    ) if "    name: default\n" in rbac else rbac

    # Confirm that the reporter RoleBinding uses the expected subject.
    rolebinding = rbac.split("kind: RoleBinding", 1)
    if len(rolebinding) != 2:
        sys.exit("ERROR: RoleBinding not found in rbac.yaml")

    if "{{ .Values.reporter.serviceAccountName }}" not in rolebinding[1]:
        sys.exit(
            "ERROR: RoleBinding subject is not configured for reporter"
        )

    if "namespace: {{ .Release.Namespace }}" not in rolebinding[1]:
        sys.exit(
            "ERROR: RoleBinding subject namespace is not release namespace"
        )

    # 3. Ensure reporter runs as a numeric non-root UID.
    if "runAsUser: 10001" not in reporter:
        reporter = replace_once(
            reporter,
            "            runAsNonRoot: true\n",
            "            runAsNonRoot: true\n"
            "            runAsUser: 10001\n",
            "Reporter securityContext",
        )

    # Back up and write only files that changed.
    updates = {
        VALUES: values,
        RBAC: rbac,
        REPORTER: reporter,
    }

    for path, updated in updates.items():
        original = path.read_text()
        if original != updated:
            backup(path)
            path.write_text(updated)
            print(f"Updated: {path}")
        else:
            print(f"No change needed: {path}")

    print("\nChart YAML edits completed.")
    print("Next: helm upgrade debug-lab ./broken-chart -n debug-lab")


if __name__ == "__main__":
    main()
