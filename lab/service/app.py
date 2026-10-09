"""Tiny HTTP service for the take-home. Standard library only."""
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8080"))
# Optional: directory where a ConfigMap is mounted as files (one file per key).
# Kubernetes updates mounted files in place when the ConfigMap changes, whereas
# env vars are frozen at container start. Empty/missing dir => use env vars only.
CONFIG_DIR = os.environ.get("CONFIG_DIR", "")


def setting(key: str, default: str = "unknown") -> str:
    """Read a setting at request time: mounted file first, then env var."""
    if CONFIG_DIR:
        try:
            with open(os.path.join(CONFIG_DIR, key), encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            pass
    return os.environ.get(key, default)


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802 (http.server naming)
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._json(200, {
                "app": setting("APP_NAME"),
                "version": setting("VERSION"),
                "pod": socket.gethostname(),
            })
        elif path == "/healthz":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, fmt, *args):  # log to stdout for kubectl logs
        print(f"{self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    print(f"listening on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
