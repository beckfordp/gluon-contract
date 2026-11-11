# SPDX-License-Identifier: MIT
# Stand-in user-service / order-service / OTLP receiver for the capture.
# Every request is appended to requests.jsonl; trace exports are kept raw.
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

out = sys.argv[1]
U_OK, U_GONE, U_FLAKY = sys.argv[2:5]
O_CUST, O_GUEST, O_NOGUEST, O_GONE = sys.argv[5:9]
users = {
    U_OK: (200, {"userId": U_OK, "email": "ada@example.com", "createdAt": "2026-11-01T09:00:00Z"}),
    U_GONE: (404, {"error": "User not found"}),
    U_FLAKY: (500, None),
}


def order(oid, cust, guest):
    return (
        200,
        {
            "orderId": oid,
            "customerId": cust,
            "guestEmail": guest,
            "status": "confirmed",
            "totalCents": 4999,
            "items": [],
            "createdAt": "2026-11-01T10:00:00Z",
        },
    )


orders = {
    O_CUST: order(O_CUST, U_OK, None),
    O_GUEST: order(O_GUEST, U_GONE, "guest@example.com"),
    O_NOGUEST: order(O_NOGUEST, U_GONE, None),
    O_GONE: (404, {"error": "Order not found"}),
}
lock = threading.Lock()
n = [0]


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def record(self, body):
        entry = {
            "at": time.time(),
            "method": self.command,
            "path": self.path,
            "headers": [[k, v] for k, v in self.headers.items()],
            "body_bytes": len(body),
        }
        with lock, open(f"{out}/requests.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")

    def reply(self, code, body, ctype="application/json"):
        if body is None:
            data = b""
        else:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        if data:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.record(b"")
        parts = self.path.split("?")[0].strip("/").split("/")
        table = {"users": users, "orders": orders}.get(parts[0]) if len(parts) == 2 else None
        if table is None:
            return self.reply(404, None)
        # Unknown ids: 400 for a non-UUID (as user-service does), else 404.
        unknown = (400, {"error": "Invalid id"}) if len(parts[1]) != 36 else (404, None)
        code, body = table.get(parts[1], unknown)
        self.reply(code, body)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.record(body)
        if self.path == "/v1/traces":
            ext = "json" if "json" in self.headers.get("Content-Type", "") else "pb"
            with lock:
                n[0] += 1
                with open(f"{out}/otlp/{n[0]:04d}.{ext}", "wb") as f:
                    f.write(body)
            return self.reply(200, b"", "application/x-protobuf")
        self.reply(404, None)


ThreadingHTTPServer(("127.0.0.1", 18090), H).serve_forever()
