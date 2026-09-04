#!/usr/bin/env python3
"""Serves the same Google Ads tools over HTTP, for Claude in the browser.

google-ads-mcp.py speaks stdio, which is what Claude Code and the Claude
desktop app launch. Claude on the web and on a phone cannot launch a local
process — it reaches a URL. This script wraps the identical tool handlers
in a Streamable HTTP endpoint so the same thirteen tools appear in
claude.ai as a custom connector.

Nothing about the tools changes. The guardrails, the dry runs and the
change log are the ones in google_ads_client.py, because this is the same
code with a different door.

THE DOOR IS ON THE INTERNET, so it is locked three ways:

    Bearer token    a shared secret, compared in constant time
    Address filter  optionally only Anthropic's published egress range
    Body limit      a request larger than the limit is refused unread

The address filter reads X-Forwarded-For only when the connection itself
comes from a trusted proxy address — otherwise anyone could claim to be
Anthropic in a header and walk past the filter.

A missing or wrong token gets a 401 and nothing else — no tool list, no
hint about what is behind it.

TLS IS NOT THIS SCRIPT'S JOB. Claude requires https, and a certificate
belongs to a reverse proxy that already renews it (nginx, Caddy, Traefik).
Run this on localhost, put the proxy in front. --tls-cert exists for the
case where there is no proxy, and it is the second choice.

    google-ads-http.py --token-file ~/.config/neo-google-ads/http-token
    google-ads-http.py --port 8788 --anthropic-only
    google-ads-http.py --new-token           print a fresh token and exit

No dependencies beyond the standard library.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import hmac
import http.server
import ipaddress
import json
import os
import pathlib
import secrets
import socketserver
import ssl
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import importlib.util  # noqa: E402


def load_mcp():
    """Imports the stdio server despite the hyphen in its file name."""
    path = pathlib.Path(__file__).parent / "google-ads-mcp.py"
    spec = importlib.util.spec_from_file_location("google_ads_mcp", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mcp = load_mcp()

# Anthropic publishes the range its servers call out from. Restricting to it
# turns a guessed token into a useless one, because the guess has to come
# from the right address as well.
ANTHROPIC_EGRESS = ipaddress.ip_network("160.79.104.0/21")

MAX_BODY = 1_000_000          # A JSON-RPC call for this API never approaches this.
TOKEN_FILE = mcp.CHANGE_LOG.parent / "http-token"


def load_token(path: pathlib.Path) -> str:
    if not path.exists():
        raise SystemExit(
            f"No token at {path}.\n"
            f"Create one:  google-ads-http.py --new-token --token-file {path}"
        )
    token = path.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise SystemExit(f"The token in {path} is shorter than 32 characters. "
                         "Generate one with --new-token.")
    return token


def write_token(path: pathlib.Path) -> str:
    token = secrets.token_urlsafe(48)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return token


class Handler(http.server.BaseHTTPRequestHandler):
    """One request. Authenticate, hand to the JSON-RPC layer, answer."""

    protocol_version = "HTTP/1.1"
    server_version = "neo-google-ads/1.2"
    sys_version = ""            # Do not advertise the Python version.

    token = ""
    anthropic_only = False
    path_prefix = "/mcp"
    # A reverse proxy sits on a private address: the loopback interface, or
    # a container network. Nothing on the public internet is trusted to
    # describe who it is forwarding for.
    trusted_proxies = (
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("fd00::/8"),
    )

    # -- helpers -----------------------------------------------------------

    def _client_ip(self):
        """The caller's address — trusting X-Forwarded-For only from a proxy.

        A header can say anything. If the address filter believed every
        X-Forwarded-For it saw, an attacker would simply claim to be
        Anthropic and the filter would be decoration. So the header counts
        only when the connection itself comes from an address in
        trusted_proxies; from anywhere else the socket address wins.
        """
        try:
            direct = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return None

        forwarded = self.headers.get("X-Forwarded-For", "")
        if not forwarded:
            return direct
        if not any(direct in network for network in self.trusted_proxies):
            self.log_line(f"ignoring X-Forwarded-For from untrusted {direct}")
            return direct
        try:
            return ipaddress.ip_address(forwarded.split(",")[0].strip())
        except ValueError:
            return direct

    def _send(self, status: int, payload: dict | None = None, *, headers: dict | None = None):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8") \
            if payload is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _authorized(self) -> bool:
        """Address first, then token — both in constant time where it matters."""
        if self.anthropic_only:
            address = self._client_ip()
            if address is None or address not in ANTHROPIC_EGRESS:
                self.log_line(f"refused: address {address} outside the Anthropic range")
                return False
        header = self.headers.get("Authorization", "")
        presented = header[7:].strip() if header.lower().startswith("bearer ") else ""
        if not presented:
            presented = self.headers.get("X-Api-Key", "").strip()
        if not presented or not hmac.compare_digest(presented, self.token):
            self.log_line("refused: bad or missing token")
            return False
        return True

    def _unauthorized(self):
        # The 401 carries the WWW-Authenticate header the MCP spec asks for,
        # so a client that wants to negotiate knows what it is looking at.
        self._send(401, {"error": "unauthorized"},
                   headers={"WWW-Authenticate": 'Bearer realm="neo-google-ads"'})

    def log_line(self, text: str) -> None:
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        print(f"{stamp} {self.client_address[0]} {text}", file=sys.stderr, flush=True)

    def log_message(self, *args):
        pass  # Replaced by log_line, so the access log stays one line per call.

    # -- verbs -------------------------------------------------------------

    def do_GET(self):  # noqa: N802
        """Only a health check. The MCP endpoint itself answers POST."""
        if self.path.rstrip("/") in ("/health", "/healthz"):
            self._send(200, {"status": "ok", "server": mcp.SERVER_NAME,
                             "version": mcp.SERVER_VERSION,
                             "protocol_versions": list(mcp.PROTOCOL_VERSIONS)})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") not in (self.path_prefix.rstrip("/"), ""):
            self._send(404, {"error": "not found"})
            return
        if not self._authorized():
            self._unauthorized()
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send(400, {"error": "bad Content-Length"})
            return
        if length > MAX_BODY:
            self._send(413, {"error": f"body larger than {MAX_BODY} bytes"})
            return

        raw = self.rfile.read(length) if length else b""
        try:
            message = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send(400, {"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": f"Parse error: {exc}"}})
            return

        # A batch is a list; the spec allows it and Claude does not send one,
        # but answering it is three lines and refusing it would be a surprise.
        if isinstance(message, list):
            answers = [a for a in (self._one(m) for m in message) if a is not None]
            if not answers:
                self._send(202)
                return
            self._send(200, answers)
            return

        answer = self._one(message)
        if answer is None:
            self._send(202)          # notification: accepted, nothing to say
            return
        self._send(200, answer)

    def _one(self, message: dict) -> dict | None:
        """Runs one JSON-RPC message through the same handler stdio uses."""
        if not isinstance(message, dict):
            return {"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32600, "message": "Invalid Request"}}
        request_id = message.get("id")
        method = message.get("method", "")
        self.log_line(f"{method} id={request_id}")
        try:
            result = mcp.handle(method, message.get("params") or {})
        except LookupError:
            if request_id is None:
                return None
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}}
        except Exception as exc:  # noqa: BLE001
            print(traceback.format_exc(), file=sys.stderr)
            if request_id is None:
                return None
            # The type and message, never the traceback: this answer leaves the machine.
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32603,
                              "message": f"Internal error: {type(exc).__name__}"}}
        if request_id is None or result is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Serve the Google Ads MCP tools over HTTP for claude.ai.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="address to bind (default 127.0.0.1, for a reverse proxy)")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--path", default="/mcp", help="path of the MCP endpoint")
    parser.add_argument("--token-file", default=str(TOKEN_FILE),
                        help=f"file holding the bearer token (default {TOKEN_FILE})")
    parser.add_argument("--new-token", action="store_true",
                        help="write a fresh token to --token-file and exit")
    parser.add_argument("--anthropic-only", action="store_true",
                        help="refuse callers outside Anthropic's published egress range")
    parser.add_argument("--trusted-proxy", action="append", default=[], metavar="CIDR",
                        help=("address or network whose X-Forwarded-For header is believed. "
                              "Repeatable. Defaults to the loopback and private ranges, "
                              "which is where a reverse proxy sits."))
    parser.add_argument("--tls-cert", help="certificate file, if no reverse proxy terminates TLS")
    parser.add_argument("--tls-key", help="private key file, with --tls-cert")
    options = parser.parse_args()

    token_path = pathlib.Path(options.token_file).expanduser()
    if options.new_token:
        token = write_token(token_path)
        print(f"Token written to {token_path} (readable by you only).\n")
        print(token)
        print("\nEnter it in claude.ai when adding the connector, as the header")
        print("  Authorization: Bearer <token>")
        return 0

    # Fail before binding a port if the credentials are not usable.
    try:
        mcp.load_config()
    except mcp.GoogleAdsError as exc:
        print(exc.message, file=sys.stderr)
        return 1

    Handler.token = load_token(token_path)
    Handler.anthropic_only = options.anthropic_only
    Handler.path_prefix = options.path
    if options.trusted_proxy:
        try:
            Handler.trusted_proxies = tuple(
                ipaddress.ip_network(entry, strict=False) for entry in options.trusted_proxy)
        except ValueError as exc:
            print(f"--trusted-proxy: {exc}", file=sys.stderr)
            return 1

    server = ThreadingServer((options.host, options.port), Handler)
    scheme = "http"
    if options.tls_cert:
        if not options.tls_key:
            print("--tls-cert needs --tls-key.", file=sys.stderr)
            return 1
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(options.tls_cert, options.tls_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"

    print(f"neo-google-ads over HTTP on {scheme}://{options.host}:{options.port}{options.path}",
          file=sys.stderr)
    print(f"  token:      {token_path}", file=sys.stderr)
    print(f"  callers:    {'Anthropic egress range only' if options.anthropic_only else 'any'}",
          file=sys.stderr)
    print(f"  proxies:    {', '.join(str(n) for n in Handler.trusted_proxies)}",
          file=sys.stderr)
    print(f"  TLS:        {'this process' if options.tls_cert else 'expected from a proxy'}",
          file=sys.stderr)
    print("  health:     GET /health", file=sys.stderr)
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
