#!/usr/bin/env bash
# One-command setup: kind cluster + ingress-nginx + image + helm release.
# Idempotent: safe to run repeatedly.
set -euo pipefail

CLUSTER="${CLUSTER:-demo}"
NAMESPACE="${NAMESPACE:-demo}"
RELEASE="${RELEASE:-demo}"
IMAGE_REPO="${IMAGE_REPO:-demo-app}"
IMAGE_TAG="${IMAGE_TAG:-1.0.0}"
# Pinned for reproducibility (never track a moving branch).
INGRESS_NGINX_VERSION="${INGRESS_NGINX_VERSION:-controller-v1.11.2}"
INGRESS_MANIFEST="https://raw.githubusercontent.com/kubernetes/ingress-nginx/${INGRESS_NGINX_VERSION}/deploy/static/provider/kind/deploy.yaml"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# --- 0. preflight ------------------------------------------------------------
for tool in docker kind kubectl helm; do
  command -v "$tool" >/dev/null 2>&1 || die "'$tool' is required but not installed"
done
docker info >/dev/null 2>&1 || die "docker daemon is not running"

# --- 1. kind cluster (create or reuse) ---------------------------------------
if kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  log "kind cluster '$CLUSTER' already exists - reusing"
else
  log "creating kind cluster '$CLUSTER'"
  cat <<KINDCFG | kind create cluster --name "$CLUSTER" --wait 120s --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - containerPort: 80
        hostPort: 80
        protocol: TCP
      - containerPort: 443
        hostPort: 443
        protocol: TCP
KINDCFG
fi
kubectl config use-context "kind-${CLUSTER}" >/dev/null

# --- 2. ingress-nginx --------------------------------------------------------
log "installing ingress-nginx (${INGRESS_NGINX_VERSION})"
kubectl apply -f "$INGRESS_MANIFEST"
# Wait for the controller AND the admission webhook cert job. Skipping this is
# the classic cause of "second/first helm install fails on webhook".
kubectl -n ingress-nginx wait --for=condition=complete job/ingress-nginx-admission-create --timeout=180s || true
kubectl -n ingress-nginx rollout status deployment/ingress-nginx-controller --timeout=240s
kubectl -n ingress-nginx wait --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller --timeout=240s

# --- 3. build + load image ---------------------------------------------------
IMAGE="${IMAGE_REPO}:${IMAGE_TAG}"
log "building image ${IMAGE}"
docker build -t "$IMAGE" "$ROOT/lab/service"
log "loading image into kind cluster '${CLUSTER}'"
kind load docker-image "$IMAGE" --name "$CLUSTER"

# --- 4. helm release ---------------------------------------------------------
log "installing chart as release '${RELEASE}' in namespace '${NAMESPACE}'"
attempt=1
until helm upgrade --install "$RELEASE" "$ROOT/chart" \
        --namespace "$NAMESPACE" --create-namespace \
        --set image.repository="$IMAGE_REPO" --set image.tag="$IMAGE_TAG" \
        --wait --timeout 180s; do
  [ "$attempt" -ge 5 ] && die "helm install failed after $attempt attempts"
  echo "helm failed (attempt $attempt) - ingress webhook may still be warming up; retrying in 10s"
  attempt=$((attempt + 1)); sleep 10
done

log "done"
cat <<MSG

Verify:
  kubectl -n ${NAMESPACE} get pods,svc,ingress
  curl -s -H 'Host: demo.local' http://localhost/
  # or add '127.0.0.1 demo.local' to /etc/hosts and: curl http://demo.local/
MSG