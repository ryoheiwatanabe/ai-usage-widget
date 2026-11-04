#!/usr/bin/env python3
"""Serve only the quota dashboard and snapshot on a trusted local Wi-Fi network."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
import subprocess
from pathlib import Path


def make_handler(source, page, allowed, hosts):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.client_address[0] not in allowed or self.headers.get("Host") not in hosts:
                self.send_error(403)
                return
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.send_error(403)
                return
            if self.path == "/":
                data, kind = page.read_bytes(), "text/html; charset=utf-8"
            elif self.path == "/usage.json":
                try:
                    if source.stat().st_size > 131072:
                        raise ValueError("too large")
                    snapshot = json.loads(source.read_text())
                    if snapshot.get("schemaVersion") != 1 or not isinstance(snapshot.get("providers"), list):
                        raise ValueError("invalid snapshot")
                    # Export only documented quota fields, even if a source gains unrelated data.
                    providers = []
                    for p in snapshot["providers"]:
                        if p.get("id") not in ("codex", "claude"):
                            continue
                        item = {k: p.get(k) for k in ("id", "name", "status", "measuredAt", "credits")}
                        item["windows"] = [{k: w.get(k) for k in ("id", "label", "remainingPercent", "resetsAt", "resetLabel")}
                                           for w in p.get("windows", [])]
                        providers.append(item)
                    data = json.dumps({"schemaVersion": 1, "generatedAt": snapshot.get("generatedAt"),
                                       "providers": providers}, allow_nan=False).encode()
                except (OSError, ValueError, TypeError, KeyError, AttributeError):
                    self.send_error(503, "Snapshot unavailable")
                    return
                kind = "application/json; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--bind", default="127.0.0.1", type=ipaddress.IPv4Address)
    parser.add_argument("--allow", action="append", default=[], type=ipaddress.IPv4Address)
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    if args.bind.is_unspecified or (not args.bind.is_loopback and not args.bind.is_private):
        parser.error("特定のLANアドレスまたはlocalhostを指定してください。")
    if not args.bind.is_loopback and not args.allow:
        parser.error("Wi-Fiで使うFire HDのIPアドレスを --allow で指定してください。")
    allowed = {"127.0.0.1", *(str(ip) for ip in args.allow)}
    hosts = {str(args.bind) + ":" + str(args.port), "127.0.0.1:" + str(args.port)}
    page = Path(__file__).resolve().parent.parent / "firehd/index.html"
    server = ThreadingHTTPServer((str(args.bind), args.port), make_handler(args.source.expanduser(), page, allowed, hosts))
    print("Fire HD: http://" + str(args.bind) + ":" + str(args.port), flush=True)
    # Keep Python as the responsible app for iCloud permissions, rather than caffeinate.
    awake = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        server.serve_forever()
    finally:
        awake.terminate()
        awake.wait()
        server.server_close()


if __name__ == "__main__":
    main()
