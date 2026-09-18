#!/usr/bin/env python3
"""Proves the guardrails hold, without a network and without credentials.

google-ads-check.py answers 'does the connection work'. This script
answers a different question: 'does the hand brake work'. It runs the
write path against a stand-in for the API and asserts that every
deliberately broken call is refused and every clean one gets through.

That distinction matters. A guardrail that has never been shown to refuse
anything is a comment, not a guardrail — and the thing it is supposed to
stop is a five-figure invoice.

The cases fall in fifteen groups:

    guardrails    switch off, wrong account, budget ceiling, budget jump,
                  too many operations, and the clean case that must pass
    request shape what actually lands in the request body
    errors        Google's nested error envelope becomes one readable line
    shaping       micros to currency, nested answer to flat field names
    queries       every prepared report produces valid GAQL
    protocol      the MCP handshake, both generations, and tools/list
    http door     a real server on a real port: token, address filter, paths
    console       the guardrails page edits what the server really reads
    qr code       the codes an authenticator app has to be able to scan
    two factor    RFC 6238, and that a code cannot be used twice
    portal        accounts, sessions, the lockout, recovery codes
    portal door   which requests get in, and how the address is read
    permission    which manager header opens which account — measured

    google-ads-selftest.py
    google-ads-selftest.py --verbose

Exit code 0 when every case passed, 1 when one failed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import google_ads_client as gac  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def case(name: str, passed: bool, detail: str = "") -> None:
    RESULTS.append((name, passed, detail))


def expect_refused(name: str, action, expected: str) -> None:
    """The call must be refused, and the refusal must say why."""
    try:
        action()
    except gac.GoogleAdsError as exc:
        if expected.lower() in exc.message.lower():
            case(name, True, exc.message.splitlines()[0][:100])
        else:
            case(name, False, f"refused, but for the wrong reason: {exc.message[:120]}")
        return
    case(name, False, "NOT REFUSED — the guardrail did not fire")


def expect_allowed(name: str, action) -> None:
    try:
        action()
    except gac.GoogleAdsError as exc:
        case(name, False, f"refused although it should pass: {exc.message[:120]}")
        return
    case(name, True, "passed")


def make_client(**guardrails) -> gac.Client:
    """A client with fake credentials that never reaches the network."""
    config = {
        "client_id": "test", "client_secret": "test", "refresh_token": "test",
        "developer_token": "test", "api_version": "v25",
        "guardrails": dict(gac.DEFAULT_GUARDRAILS, **guardrails),
    }
    client = gac.Client(config)
    client._token = "fake-token"          # noqa: SLF001 - stands in for the OAuth round trip
    client._token_expires = 2 ** 31       # noqa: SLF001
    return client


def budget_operation(micros: int, resource_name: str = "") -> list[dict]:
    key = "update" if resource_name else "create"
    resource = {"amountMicros": str(micros)}
    if resource_name:
        resource["resourceName"] = resource_name
    return [{"campaignBudgetOperation": {key: resource}}]


# --------------------------------------------------------------------------
# 1. Guardrails
# --------------------------------------------------------------------------

def test_guardrails() -> None:
    status_op = [{"campaignOperation": {
        "update": {"resourceName": "customers/1234567890/campaigns/1", "status": "PAUSED"},
        "updateMask": "status"}}]

    expect_refused(
        "write switch off refuses a live write",
        lambda: make_client(write_enabled=False).check_write_allowed(
            "1234567890", status_op, dry_run=False),
        "writing is switched off",
    )
    expect_allowed(
        "write switch off still allows a dry run",
        lambda: make_client(write_enabled=False).check_write_allowed(
            "1234567890", status_op, dry_run=True),
    )
    expect_refused(
        "account outside the allow list is refused",
        lambda: make_client(write_enabled=True,
                            allowed_customer_ids=["9999999999"]).check_write_allowed(
            "1234567890", status_op, dry_run=False),
        "not in guardrails.allowed_customer_ids",
    )
    expect_refused(
        "account outside the allow list is refused in a dry run too",
        lambda: make_client(write_enabled=True,
                            allowed_customer_ids=["9999999999"]).check_write_allowed(
            "1234567890", status_op, dry_run=True),
        "not in guardrails.allowed_customer_ids",
    )
    expect_allowed(
        "account inside the allow list passes",
        lambda: make_client(write_enabled=True,
                            allowed_customer_ids=["123-456-7890"]).check_write_allowed(
            "1234567890", status_op, dry_run=False),
    )
    expect_refused(
        "budget above the ceiling is refused",
        lambda: make_client(write_enabled=True,
                            max_daily_budget_micros=50_000_000).check_write_allowed(
            "1234567890", budget_operation(80_000_000), dry_run=False),
        "above the agreed ceiling",
    )
    expect_allowed(
        "budget below the ceiling passes",
        lambda: make_client(write_enabled=True,
                            max_daily_budget_micros=50_000_000).check_write_allowed(
            "1234567890", budget_operation(40_000_000), dry_run=False),
    )
    expect_refused(
        "the classic euros-as-micros slip is refused",
        # 25 written where 25000000 was meant is harmless; the reverse,
        # 25000000 written where 25 was meant, is a 25 million euro budget.
        lambda: make_client(write_enabled=True,
                            max_daily_budget_micros=100_000_000).check_write_allowed(
            "1234567890", budget_operation(25_000_000_000_000), dry_run=False),
        "above the agreed ceiling",
    )
    expect_refused(
        "too many operations in one call is refused",
        lambda: make_client(write_enabled=True,
                            max_operations_per_call=10).check_write_allowed(
            "1234567890", status_op * 11, dry_run=False),
        "the limit is 10",
    )
    expect_refused(
        "a bad customer ID is refused",
        lambda: gac.normalize_customer_id("keine-nummer"),
        "is not a customer ID",
    )
    case("hyphens in a customer ID are stripped",
         gac.normalize_customer_id("123-456-7890") == "1234567890")

    # The increase factor needs the current budget, which normally comes from
    # the API. Stand in for that read so the step can be measured offline.
    client = make_client(write_enabled=True, max_budget_increase_factor=2.0)
    client._current_budget_micros = lambda *_: 10_000_000  # noqa: SLF001
    expect_refused(
        "budget jump beyond the agreed factor is refused",
        lambda: client.check_write_allowed(
            "1234567890",
            budget_operation(50_000_000, "customers/1234567890/campaignBudgets/1"),
            dry_run=False),
        "more than the agreed factor",
    )
    expect_allowed(
        "budget step within the agreed factor passes",
        lambda: client.check_write_allowed(
            "1234567890",
            budget_operation(18_000_000, "customers/1234567890/campaignBudgets/1"),
            dry_run=False),
    )


def test_guardrails_from_env() -> None:
    """The container case: no configuration file, everything from the environment."""
    import contextlib
    import os

    @contextlib.contextmanager
    def environment(**values):
        vorher = {k: os.environ.get(k) for k in values}
        os.environ.update({k: str(v) for k, v in values.items()})
        try:
            yield
        finally:
            for key, old in vorher.items():
                if old is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old

    base = {"client_id": "x", "client_secret": "x", "refresh_token": "x",
            "developer_token": "x"}

    with environment(GOOGLE_ADS_CONFIG="/does/not/exist.json",
                     GOOGLE_ADS_CLIENT_ID="x", GOOGLE_ADS_CLIENT_SECRET="x",
                     GOOGLE_ADS_REFRESH_TOKEN="x", GOOGLE_ADS_DEVELOPER_TOKEN="x",
                     GOOGLE_ADS_ALLOW_WRITE="true",
                     GOOGLE_ADS_ALLOWED_CUSTOMER_IDS="123-456-7890, 9876543210",
                     GOOGLE_ADS_MAX_DAILY_BUDGET="50",
                     GOOGLE_ADS_MAX_BUDGET_INCREASE_FACTOR="1.5",
                     GOOGLE_ADS_MAX_OPERATIONS_PER_CALL="25"):
        config = gac.load_config()
        rails = config["guardrails"]
        case("the write switch comes from the environment", rails["write_enabled"] is True)
        case("the account list is parsed and the hyphens stripped",
             rails["allowed_customer_ids"] == ["1234567890", "9876543210"],
             str(rails["allowed_customer_ids"]))
        case("the budget ceiling is given in currency and stored in micros",
             rails["max_daily_budget_micros"] == 50_000_000,
             str(rails["max_daily_budget_micros"]))
        case("factor and operation limit come through",
             rails["max_budget_increase_factor"] == 1.5
             and rails["max_operations_per_call"] == 25)

        # And they must actually bite, not merely be present.
        client = gac.Client(config)
        client._token = "fake"                 # noqa: SLF001
        client._token_expires = 2 ** 31        # noqa: SLF001
        expect_refused(
            "an account outside the environment list is refused",
            lambda: client.check_write_allowed("5555555555", [], dry_run=False),
            "not in guardrails.allowed_customer_ids",
        )
        expect_refused(
            "a budget above the environment ceiling is refused",
            lambda: client.check_write_allowed(
                "1234567890", budget_operation(60_000_000), dry_run=False),
            "above the agreed ceiling",
        )

    with environment(GOOGLE_ADS_CONFIG="/does/not/exist.json",
                     GOOGLE_ADS_CLIENT_ID="x", GOOGLE_ADS_CLIENT_SECRET="x",
                     GOOGLE_ADS_REFRESH_TOKEN="x", GOOGLE_ADS_DEVELOPER_TOKEN="x",
                     GOOGLE_ADS_MAX_DAILY_BUDGET="fuenfzig"):
        expect_refused(
            "a budget ceiling that is not a number is refused at startup",
            gac.load_config,
            "is not a number",
        )

    with environment(GOOGLE_ADS_CONFIG="/does/not/exist.json",
                     GOOGLE_ADS_CLIENT_ID="x", GOOGLE_ADS_CLIENT_SECRET="x",
                     GOOGLE_ADS_REFRESH_TOKEN="x", GOOGLE_ADS_DEVELOPER_TOKEN="x"):
        rails = gac.load_config()["guardrails"]
        case("without the variables the restrictive defaults stand",
             rails["write_enabled"] is False and rails["allowed_customer_ids"] == []
             and rails["max_daily_budget_micros"] == 0)


def test_request_shape() -> None:
    """Looks at what actually goes into the request body.

    This group exists because of a bug that every other check waved
    through: search() sent pageSize, which the API documents as removed
    and answers with PAGE_SIZE_NOT_SUPPORTED. It arrives as a bare
    "Request contains an invalid argument" — a message that names neither
    the field nor the request — so it reads like a broken account. No
    test caught it, because no test had ever looked at a request body.
    Now one does.
    """
    sent = {}

    def fake_call(method, path, body=None, *, login_customer_id=""):
        sent["method"], sent["path"], sent["body"] = method, path, body
        sent["login"] = login_customer_id
        return {"results": [{"customer": {"id": "1"}}]}

    client = make_client()
    client.call = fake_call
    client.search("123-456-7890", "SELECT customer.id FROM customer", max_rows=5)

    case("search posts to the documented path",
         sent["path"] == "customers/1234567890/googleAds:search", sent.get("path", ""))
    case("search sends the query and nothing else",
         set(sent["body"]) == {"query"}, str(sorted(sent["body"])))
    case("search does NOT send pageSize — the API refuses it",
         "pageSize" not in sent["body"] and "page_size" not in sent["body"],
         str(sorted(sent["body"])))

    # A second page must carry the token and still no pageSize.
    pages = [
        {"results": [{"customer": {"id": "1"}}], "nextPageToken": "abc"},
        {"results": [{"customer": {"id": "2"}}]},
    ]
    bodies = []

    def paging_call(method, path, body=None, *, login_customer_id=""):
        bodies.append(body)
        return pages[len(bodies) - 1]

    client.call = paging_call
    rows = client.search("1234567890", "SELECT customer.id FROM customer")
    case("paging follows nextPageToken", len(rows) == 2, f"{len(rows)} rows")
    case("the second page sends the token and still no pageSize",
         set(bodies[1]) == {"query", "pageToken"} and bodies[1]["pageToken"] == "abc",
         str(sorted(bodies[1])))

    # max_rows must stop the paging, or a wide query runs until the quota does.
    endless = {"results": [{"customer": {"id": "x"}}] * 50, "nextPageToken": "more"}
    calls = []
    client.call = lambda m, p, b=None, **kw: (calls.append(1), endless)[1]
    rows = client.search("1234567890", "SELECT customer.id FROM customer", max_rows=60)
    case("max_rows stops the paging", len(rows) == 60 and len(calls) == 2,
         f"{len(rows)} rows in {len(calls)} calls")

    # The write path must keep sending validateOnly, or a dry run is not one.
    mutated = {}

    def mutate_call(method, path, body=None, *, login_customer_id=""):
        mutated.update({"path": path, "body": body})
        return {"mutateOperationResponses": []}

    writer = make_client(write_enabled=True)
    writer.call = mutate_call
    writer.mutate("1234567890", [{"campaignOperation": {"remove": "x"}}], dry_run=True)
    case("a dry run really sets validateOnly",
         mutated["body"].get("validateOnly") is True, str(mutated["body"].get("validateOnly")))
    case("mutate posts to the documented path",
         mutated["path"] == "customers/1234567890/googleAds:mutate", mutated.get("path", ""))


# --------------------------------------------------------------------------
# 2. Error translation
# --------------------------------------------------------------------------

class FakeHTTPError(urllib.error.HTTPError):
    """A Google error response, shaped exactly as the API sends it."""

    def __init__(self, code: int, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")
        super().__init__("https://googleads.googleapis.com/v25/x", code, "error", {}, None)

    def read(self):
        return self._body


def test_errors() -> None:
    client = make_client()
    error = client._translate(FakeHTTPError(400, {  # noqa: SLF001
        "error": {
            "code": 400, "message": "Request contains an invalid argument.",
            "details": [{"errors": [{
                "errorCode": {"fieldError": "REQUIRED"},
                "message": "The required field was not present.",
                "location": {"fieldPathElements": [
                    {"fieldName": "operations", "index": 0}, {"fieldName": "create"},
                    {"fieldName": "amount_micros"}]},
            }]}],
        }
    }))
    message = error.message
    case("error names the failing rule", "fieldError=REQUIRED" in message, message[:90])
    case("error names the failing field", "amount_micros" in message)
    case("error keeps Google's own wording",
         "The required field was not present." in message)

    denied = client._translate(FakeHTTPError(403, {  # noqa: SLF001
        "error": {"code": 403, "message": "The caller does not have permission",
                  "details": [{"errors": [{
                      "errorCode": {"authorizationError": "DEVELOPER_TOKEN_NOT_APPROVED"},
                      "message": "The developer token is not approved."}]}]}}))
    case("403 on the developer token points at the API Center",
         "API Center" in denied.message)

    broken = client._translate(FakeHTTPError(500, {}))
    case("an error without the envelope still produces a message",
         bool(broken.message) and broken.status == 500)


# --------------------------------------------------------------------------
# 3. Shaping
# --------------------------------------------------------------------------

def test_shaping() -> None:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    server = load_server()

    flat = server.flatten({"campaign": {"id": "1", "name": "X"},
                           "metrics": {"costMicros": "1500000"},
                           "adGroupCriterion": {"keyword": {"matchType": "PHRASE"}}})
    case("nested camelCase answer becomes the snake_case names GAQL asked for",
         flat == {"campaign.id": "1", "campaign.name": "X",
                  "metrics.cost_micros": "1500000",
                  "ad_group_criterion.keyword.match_type": "PHRASE"}, str(flat))

    with_money = server.add_currency(dict(flat))
    case("micros get a readable amount beside them",
         with_money.get("metrics.cost_amount") == 1.5, str(with_money))
    case("a field that is not micros gets no amount",
         "campaign.name_amount" not in with_money)

    shaped = server.shape([{"a": {"b": i}} for i in range(10)], 3)
    case("too many rows are cut and the cut is reported",
         shaped["row_count"] == 3 and shaped.get("truncated") is True)

    case("a GAQL literal with a quote is escaped",
         server.gaql_string("O'Brien") == "'O\\'Brien'",
         server.gaql_string("O'Brien"))


# --------------------------------------------------------------------------
# 4. Prepared reports
# --------------------------------------------------------------------------

def test_reports() -> None:
    server = load_server()
    broken = []
    for name, report in server.REPORTS.items():
        query = "SELECT " + ", ".join(report["fields"]) + " FROM " + report["from"]
        if not report["fields"] or not report["from"]:
            broken.append(f"{name}: empty")
        if report.get("date") and "metrics." not in query and "change_event" not in query:
            broken.append(f"{name}: date range but no metrics")
        if "  " in query or query.endswith(","):
            broken.append(f"{name}: malformed")
    case(f"all {len(server.REPORTS)} prepared reports produce well-formed GAQL",
         not broken, "; ".join(broken))

    for tool in server.tool_catalogue():
        schema = tool["inputSchema"]
        for required in schema.get("required", []):
            if required not in schema.get("properties", {}):
                case(f"tool {tool['name']} declares required field it does not define",
                     False, required)
                return
    case(f"all {len(server.tool_catalogue())} tools declare a consistent schema", True)


# --------------------------------------------------------------------------
# 5. Protocol
# --------------------------------------------------------------------------

def load_server():
    """Imports the MCP server despite the hyphen in its file name."""
    import importlib.util
    path = pathlib.Path(__file__).parent / "google-ads-mcp.py"
    spec = importlib.util.spec_from_file_location("google_ads_mcp", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_protocol() -> None:
    server = load_server()

    old = server.handle("initialize", {"protocolVersion": "2025-06-18"})
    case("initialize mirrors the version the client asked for",
         old["protocolVersion"] == "2025-06-18", str(old.get("protocolVersion")))

    unknown = server.handle("initialize", {"protocolVersion": "1999-01-01"})
    case("initialize falls back on an unknown version",
         unknown["protocolVersion"] in server.PROTOCOL_VERSIONS)

    discover = server.handle("server/discover", {})
    case("server/discover advertises every supported version",
         discover["protocolVersions"] == list(server.PROTOCOL_VERSIONS))

    tools = server.handle("tools/list", {})
    names = [t["name"] for t in tools["tools"]]
    case("tools/list is complete and deterministic",
         names == list(server.HANDLERS), str(names[:3]))
    case("tools/list carries the caching fields the 2026 spec requires",
         tools.get("ttlMs") and tools.get("cacheScope") and tools.get("resultType"))

    case("notifications get no answer", server.handle("notifications/initialized", {}) is None)

    try:
        server.handle("nonsense/method", {})
        case("an unknown method is rejected", False, "no exception raised")
    except LookupError:
        case("an unknown method is rejected", True)

    unknown_tool = server.handle("tools/call", {"name": "does_not_exist", "arguments": {}})
    case("an unknown tool answers as a tool error, not a crash",
         unknown_tool.get("isError") is True)


# --------------------------------------------------------------------------
# 6. The HTTP door
#
# This transport sits on the internet, so its lock is worth more than a
# reading. The cases below start a real server on a real port and knock.
# --------------------------------------------------------------------------

def load_http():
    import importlib.util
    path = pathlib.Path(__file__).parent / "google-ads-http.py"
    spec = importlib.util.spec_from_file_location("google_ads_http", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_http() -> None:
    import json as _json
    import socket
    import threading
    import urllib.error
    import urllib.request

    http_mod = load_http()
    token = "t" * 60
    http_mod.Handler.token = token
    http_mod.Handler.anthropic_only = False
    http_mod.Handler.path_prefix = "/mcp"

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = http_mod.ThreadingServer(("127.0.0.1", port), http_mod.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"

    def post(payload, bearer=token, path="/mcp"):
        request = urllib.request.Request(base + path, method="POST",
                                         data=_json.dumps(payload).encode())
        request.add_header("Content-Type", "application/json")
        if bearer:
            request.add_header("Authorization", f"Bearer {bearer}")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read()
                return response.status, (_json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers

    try:
        status, _ = post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, bearer=None)
        case("no token is refused with 401", status == 401, f"got {status}")

        status, headers = post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                               bearer="wrong-but-same-length" + "x" * 38)
        case("a wrong token of the same length is refused", status == 401, f"got {status}")
        case("the 401 names the scheme the spec asks for",
             "Bearer" in (headers.get("WWW-Authenticate") or ""))

        status, body = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = (body or {}).get("result", {}).get("tools", [])
        case("the right token reaches the same thirteen tools",
             status == 200 and len(tools) == len(mcp_handlers()), f"{status}, {len(tools)} tools")

        status, body = post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        case("a notification is accepted with 202 and no body",
             status == 202 and body is None, f"got {status}")

        status, _ = post({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, path="/andere")
        case("another path is 404, not the tool list", status == 404, f"got {status}")

        status, body = post({"jsonrpc": "2.0", "id": 4, "method": "keine/methode"})
        code = (body or {}).get("error", {}).get("code")
        case("an unknown method answers -32601", code == -32601, str(code))

        # The address filter is the second lock; it must refuse a caller from
        # outside the range even when the token is right.
        http_mod.Handler.anthropic_only = True
        status, _ = post({"jsonrpc": "2.0", "id": 5, "method": "tools/list"})
        case("with --anthropic-only a local caller is refused despite the right token",
             status == 401, f"got {status}")

        # And it must not be walked past by claiming to be Anthropic in a
        # header. This is the whole point of trusted_proxies: a header is
        # only as trustworthy as the connection that carried it.
        def post_forwarded(claimed, trusted):
            http_mod.Handler.trusted_proxies = trusted
            request = urllib.request.Request(base + "/mcp", method="POST",
                                             data=_json.dumps(
                                                 {"jsonrpc": "2.0", "id": 6,
                                                  "method": "tools/list"}).encode())
            request.add_header("Content-Type", "application/json")
            request.add_header("Authorization", f"Bearer {token}")
            request.add_header("X-Forwarded-For", claimed)
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    return response.status
            except urllib.error.HTTPError as exc:
                return exc.code

        import ipaddress as _ip
        status = post_forwarded("160.79.104.5", trusted=())
        case("a forged X-Forwarded-For does NOT get past the address filter",
             status == 401, f"got {status} — the header was believed")

        status = post_forwarded("160.79.104.5",
                                trusted=(_ip.ip_network("127.0.0.0/8"),))
        case("behind a trusted proxy the forwarded address is used",
             status == 200, f"got {status}")

        status = post_forwarded("8.8.8.8", trusted=(_ip.ip_network("127.0.0.0/8"),))
        case("a trusted proxy forwarding a foreign address is still refused",
             status == 401, f"got {status}")

        http_mod.Handler.anthropic_only = False
        http_mod.Handler.trusted_proxies = ()
    finally:
        server.shutdown()
        server.server_close()


def mcp_handlers():
    return load_server().HANDLERS


# --------------------------------------------------------------------------
# 7. Change log
# --------------------------------------------------------------------------

def test_change_log() -> None:
    with tempfile.TemporaryDirectory() as folder:
        original = gac.CHANGE_LOG
        gac.CHANGE_LOG = pathlib.Path(folder) / "changes.jsonl"
        try:
            client = make_client(write_enabled=True)
            client.log_change("1234567890", [{"campaignOperation": {}}], dry_run=True,
                              result="ok", reason="self test")
            written = gac.CHANGE_LOG.read_text(encoding="utf-8").strip()
            entry = json.loads(written)
            case("a write attempt is logged with account, reason and result",
                 entry["customer_id"] == "1234567890" and entry["reason"] == "self test"
                 and entry["dry_run"] is True, written[:100])
            mode = gac.CHANGE_LOG.stat().st_mode & 0o777
            case("the change log is readable by its owner only", mode == 0o600, oct(mode))
        finally:
            gac.CHANGE_LOG = original


# --------------------------------------------------------------------------
# 10. Management console
# --------------------------------------------------------------------------

def load_setup():
    import importlib.util
    here = pathlib.Path(__file__).parent / "google_ads_setup.py"
    spec = importlib.util.spec_from_file_location("google_ads_setup", here)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONSOLE_ACCOUNTS = [
    {"id": "5691007627", "name": "NEO Digital", "currency": "EUR",
     "manager": False, "problem": ""},
    {"id": "6286913360", "name": "Kunde A", "currency": "EUR",
     "manager": False, "problem": ""},
    {"id": "5303457641", "name": "Verwaltung", "currency": "EUR",
     "manager": True, "problem": ""},
]


def test_console() -> None:
    """The guardrails page must edit what the server actually reads.

    The page is the reason nobody has to touch the .env by hand, so the
    two ways it can lie are what these cases look for: writing a value the
    environment overrides anyway, and turning 'these three accounts' into
    'every account' because the list happened not to load.
    """
    setup = load_setup()

    def mit_konten(accounts, rails, env=None, form=None):
        """Renders the page and optionally saves a form, in an empty home."""
        with tempfile.TemporaryDirectory() as folder:
            heim = pathlib.Path(folder)
            konfig = heim / "config.json"
            konfig.write_text(json.dumps({
                "client_id": "test", "client_secret": "test",
                "refresh_token": "test", "developer_token": "test",
                "api_version": "v25",
                "guardrails": dict(gac.DEFAULT_GUARDRAILS, **rails)}), encoding="utf-8")
            echte_datei, gac.CONFIG_FILE = gac.CONFIG_FILE, konfig
            echter_stand = setup.load_state
            gesetzt = []
            for name, wert in (env or {}).items():
                gesetzt.append(name)
                os.environ[name] = wert
            try:
                setup.load_state = lambda: {
                    "configured": True, "connected": bool(accounts),
                    "error": "" if accounts else "Verbindung nicht möglich",
                    "accounts": list(accounts),
                    "guardrails": gac.load_config()["guardrails"],
                    "config": gac.load_config()}
                html = setup.guardrails_page().decode("utf-8")
                gespeichert, meldung = (None, "")
                if form is not None:
                    gespeichert, meldung = setup.save_guardrails(form)
                    gespeichert = json.loads(
                        konfig.read_text(encoding="utf-8"))["guardrails"]
                return html, gespeichert, meldung
            finally:
                setup.load_state = echter_stand
                gac.CONFIG_FILE = echte_datei
                for name in gesetzt:
                    os.environ.pop(name, None)

    def feld(seite: str, name: str) -> str:
        """The one tag that carries this form field."""
        stelle = seite.index(f'name="{name}"')
        return seite[seite.rindex("<", 0, stelle):seite.index(">", stelle) + 1]

    # Anhaken statt Nummern tippen.
    html, _, _ = mit_konten(CONSOLE_ACCOUNTS, {"allowed_customer_ids": ["5691007627"]})
    case("every accessible account is offered as a checkbox",
         html.count('name="konto"') == 3, f"{html.count(chr(0x22) + chr(0x22))}")
    case("only the authorised account is ticked",
         html.count('value="5691007627" checked') == 1
         and 'value="6286913360" checked' not in html)
    case("the manager account is marked as one", "Verwaltungskonto" in html)

    # Ticking a second account must reach the file the server reads.
    _, rails, _ = mit_konten(
        CONSOLE_ACCOUNTS, {"allowed_customer_ids": ["5691007627"]},
        form={"konten_gestellt": ["1"], "write_enabled": ["on"],
              "konto": ["5691007627", "6286913360"], "max_daily_budget": ["75,50"]})
    case("ticking an account authorises it",
         rails["allowed_customer_ids"] == ["5691007627", "6286913360"],
         str(rails["allowed_customer_ids"]))
    case("a comma is read as a decimal point, and the value is stored in micros",
         rails["max_daily_budget_micros"] == 75_500_000,
         str(rails["max_daily_budget_micros"]))
    case("a guardrail the page does not show is not dropped",
         rails.get("log_changes") is True, str(rails.get("log_changes")))

    # THE DANGEROUS ONE: an empty list means 'every account'.
    html, rails, meldung = mit_konten(
        [], {"allowed_customer_ids": ["5691007627"], "write_enabled": True},
        form={"write_enabled": ["on"], "max_daily_budget": ["10"]})
    case("an unreadable account list still shows what is authorised",
         html.count('value="5691007627" checked') == 1)
    case("and says so instead of pretending there is nothing",
         'class="warnung"' in html)
    case("saving from that page does NOT widen the authorisation to every account",
         rails["allowed_customer_ids"] == ["5691007627"],
         str(rails["allowed_customer_ids"]))
    case("the other settings are saved all the same",
         rails["max_daily_budget_micros"] == 10_000_000,
         str(rails["max_daily_budget_micros"]))
    case("and the page says why the accounts stayed as they were",
         "unverändert" in meldung, meldung[:90])

    # Deliberately unticking everything, from a page that could show them.
    _, rails, _ = mit_konten(CONSOLE_ACCOUNTS, {"allowed_customer_ids": ["5691007627"]},
                             form={"konten_gestellt": ["1"]})
    case("unticking every box from a working page does clear the restriction",
         rails["allowed_customer_ids"] == [], str(rails["allowed_customer_ids"]))

    # What the environment sets, the page must not pretend to own.
    html, rails, meldung = mit_konten(
        CONSOLE_ACCOUNTS, {"allowed_customer_ids": ["5691007627"], "write_enabled": False},
        env={"GOOGLE_ADS_ALLOW_WRITE": "false", "GOOGLE_ADS_MAX_DAILY_BUDGET": "10"},
        form={"konten_gestellt": ["1"], "write_enabled": ["on"],
              "konto": ["5691007627", "6286913360"], "max_daily_budget": ["999"],
              "max_budget_increase_factor": ["3"]})
    case("a guardrail fixed by the environment is shown locked",
         "disabled" in feld(html, "write_enabled")
         and "disabled" in feld(html, "max_daily_budget"),
         feld(html, "write_enabled"))
    case("a guardrail the environment leaves alone stays editable",
         "disabled" not in feld(html, "max_budget_increase_factor"),
         feld(html, "max_budget_increase_factor"))
    case("and the page names the variable it comes from",
         "GOOGLE_ADS_ALLOW_WRITE" in html and "GOOGLE_ADS_MAX_DAILY_BUDGET" in html)
    case("a form that submits a locked field anyway changes nothing",
         rails["write_enabled"] is not True
         and rails["max_daily_budget_micros"] != 999_000_000,
         f"{rails['write_enabled']} / {rails['max_daily_budget_micros']}")
    case("a field the environment does not set is still editable",
         rails["max_budget_increase_factor"] == 3.0,
         str(rails["max_budget_increase_factor"]))
    case("and the page says which values it passed over",
         "Übergangen" in meldung, meldung[:90])

    # Rubbish in the number fields.
    for eingabe, erwartet in (("viel", "ist keine Zahl"), ("-5", "Negative Werte")):
        _, rails, meldung = mit_konten(
            CONSOLE_ACCOUNTS, {"max_daily_budget_micros": 50_000_000},
            form={"konten_gestellt": ["1"], "max_daily_budget": [eingabe]})
        case(f"a budget of {eingabe!r} is refused, and the old value stands",
             erwartet in meldung and rails["max_daily_budget_micros"] == 50_000_000,
             meldung[:80])

    # A customer id that is not one.
    _, _, meldung = mit_konten(CONSOLE_ACCOUNTS, {},
                               form={"konten_gestellt": ["1"], "konto": ["12345"]})
    case("a customer id that is not ten digits is refused",
         "ten digits" in meldung, meldung[:80])


# --------------------------------------------------------------------------
# 11. QR code
# --------------------------------------------------------------------------

# Digests of matrices that were checked module for module against an
# independent encoder (segno) while this was written. They are here so a
# later change to the encoder cannot quietly produce a code that no longer
# scans: the comparison needs no dependency, only these numbers.
QR_FIXTURES = (
    (b"NEO", 21, "8919919fed9f23a9ecf3af5fd8257d38"),
    (b"otpauth://totp/NEO:erich?secret=JBSWY3DPEHPK3PXP&issuer=NEO",
     33, "0777fe2d9f086b20f5236117fc67efea"),
    (b"otpauth://totp/NEO%20Google%20Ads%20(ads.mcp.neo-digital.at):erich.nigg"
     b"%40neo-digital.at?secret=ONSWG4TFOQYTEMZUGU3DOOBZGI2DIMBR"
     b"&issuer=NEO%20Google%20Ads&algorithm=SHA1&digits=6&period=30",
     57, "5d672866c38b7fed0795e757bfca6a70"),
    (bytes(range(256))[:200], 57, "d96588ce64381c2ccd60872f0f2b13e3"),
)


def test_qr() -> None:
    """A QR code nobody scanned is a picture. These cases are the scanner."""
    import portal_qr as qr

    for payload, size, digest in QR_FIXTURES:
        grid = qr.matrix(payload)
        got = hashlib.sha256(b"".join(bytes(row) for row in grid)).hexdigest()[:32]
        case(f"the code for {len(payload)} bytes is the one that was verified",
             len(grid) == size and got == digest, f"{len(grid)}x{len(grid)} {got}")

    grid = qr.matrix(b"NEO")
    size = len(grid)
    finder = [[1, 1, 1, 1, 1, 1, 1], [1, 0, 0, 0, 0, 0, 1], [1, 0, 1, 1, 1, 0, 1],
              [1, 0, 1, 1, 1, 0, 1], [1, 0, 1, 1, 1, 0, 1], [1, 0, 0, 0, 0, 0, 1],
              [1, 1, 1, 1, 1, 1, 1]]
    corners = all(
        [row[left:left + 7] for row in grid[top:top + 7]] == finder
        for top, left in ((0, 0), (0, size - 7), (size - 7, 0)))
    case("all three finder patterns are where a scanner looks", corners)
    case("the timing patterns alternate",
         all(grid[6][i] == (1 if i % 2 == 0 else 0) for i in range(8, size - 8))
         and all(grid[i][6] == (1 if i % 2 == 0 else 0) for i in range(8, size - 8)))
    case("the module that must always be dark is dark", grid[size - 8][8] == 1)

    # The format block must read back as level M and the mask actually used.
    read = 0
    for i in range(7):
        read = (read << 1) | grid[size - 1 - i][8]
    for i in range(8):
        read = (read << 1) | grid[8][size - 8 + i]
    unmasked = read ^ 0b101010000010010
    level, mask = unmasked >> 13, (unmasked >> 10) & 0b111
    case("the format block says error level M", level == qr.EC_INDICATOR_M, bin(unmasked))
    case("and names a mask that exists", 0 <= mask <= 7, str(mask))
    clean = qr.matrix(b"NEO")
    for row in range(size):
        for col in range(size):
            pass
    case("the same input gives the same code twice", clean == grid)

    case("a payload too large is refused, not silently cut",
         _refuses(lambda: qr.matrix(b"x" * 400), ValueError))
    biggest = qr._capacity(12)
    case("the largest payload that fits still produces a code",
         len(qr.matrix(b"x" * biggest)) == 12 * 4 + 17)
    svg = qr.svg(qr.matrix(b"NEO"))
    case("the drawing is one self-contained svg element",
         svg.startswith("<svg") and svg.endswith("</svg>") and "http" not in svg.split(">")[1],
         svg[:60])


def _refuses(action, kind) -> bool:
    try:
        action()
    except kind:
        return True
    except Exception:  # noqa: BLE001
        return False
    return False


# --------------------------------------------------------------------------
# 12. Two factor
# --------------------------------------------------------------------------

def test_two_factor() -> None:
    """RFC 6238, and the two rules that keep a valid code from being reused."""
    import portal_totp as totp

    # RFC 6238, appendix B. The published vectors use eight digits.
    secret = base64.b32encode(b"12345678901234567890").decode()
    for unix_time, expected in ((59, "94287082"), (1111111109, "07081804"),
                                (1111111111, "14050471"), (1234567890, "89005924"),
                                (2000000000, "69279037"), (20000000000, "65353130")):
        case(f"RFC 6238 vector at T={unix_time}",
             totp.code_at(secret, unix_time // totp.STEP, digits=8) == expected,
             totp.code_at(secret, unix_time // totp.STEP, digits=8))

    own = totp.new_secret()
    step = totp.current_step()
    ok, used = totp.check(own, totp.code_at(own, step))
    case("a fresh code is accepted", ok and used == step)
    ok, _ = totp.check(own, totp.code_at(own, step), last_step=used)
    case("THE SAME CODE IS NOT ACCEPTED TWICE", not ok)
    ok, _ = totp.check(own, totp.code_at(own, step - 1))
    case("a code from one step ago still works, for a slow phone", ok)
    ok, _ = totp.check(own, totp.code_at(own, step - 5))
    case("a code from five steps ago does not", not ok)
    ok, _ = totp.check(own, "000000", last_step=-1)
    case("a wrong code is refused", not ok)
    ok, _ = totp.check(own, "12345")
    case("a code of the wrong length is refused", not ok)
    case("spaces and lower case in a pasted secret are tolerated",
         totp.code_at(own, step) == totp.code_at(own.lower()[:8] + " " + own[8:], step))

    uri = totp.provisioning_uri(own, "erich@neo-digital.at", "Beispielmarke")
    case("the app gets an otpauth URI with the secret and the issuer",
         uri.startswith("otpauth://totp/") and f"secret={own}" in uri
         and "issuer=Beispielmarke" in uri, uri[:70])
    case("and the account name is escaped, not left to break the URI",
         " " not in uri and "@" not in uri.split("?")[0].replace("%40", ""))

    codes = totp.recovery_codes(10)
    case("ten recovery codes, all different", len(set(codes)) == 10)
    case("and none of them contains a character you could misread",
         not any(set(code) & set("ilo01") for code in codes), str(codes[:2]))


# --------------------------------------------------------------------------
# 13. Portal accounts
# --------------------------------------------------------------------------

def test_portal() -> None:
    """Accounts, sessions and the lockout — against a real database file."""
    import portal_store as store
    import portal_totp as totp

    with tempfile.TemporaryDirectory() as folder:
        database = pathlib.Path(folder) / "portal.db"
        with store.open_database(database) as db:
            case("a fresh database has no accounts", store.count_users(db) == 0)
            user_id = store.create_user(db, "erich", "Donau-Dampfschiff-2026!",
                                        email="erich@neo-digital.at", must_change=True)
            user = store.user_by_id(db, user_id)
            case("the password is not stored as it was typed",
                 "Donau" not in user["password_hash"]
                 and user["password_hash"].startswith("scrypt$"),
                 user["password_hash"][:20])
            case("the right password verifies",
                 store.verify_password(user["password_hash"], "Donau-Dampfschiff-2026!"))
            case("a wrong one does not",
                 not store.verify_password(user["password_hash"], "Donau-Dampfschiff-2025!"))
            case("two accounts with the same password get different hashes",
                 store.hash_password("gleiches Kennwort")
                 != store.hash_password("gleiches Kennwort"))
            case("the name is matched without regard to case",
                 store.find_user(db, "ERICH")["id"] == user_id)
            case("a short password is refused", bool(store.password_complaint("kurz")))
            case("a long one is not", not store.password_complaint("Donau-Dampfschiff-2026!"))

            # Sessions
            token = store.start_session(db, user_id, address="127.0.0.1", agent="Prüfung")
            row = store.read_session(db, token)
            case("a session can be read back", row is not None and row["user_id"] == user_id)
            case("THE COOKIE ITSELF IS NOT IN THE DATABASE",
                 db.execute("SELECT COUNT(*) AS n FROM sessions WHERE token_hash = ?",
                            (token,)).fetchone()["n"] == 0)
            case("an unknown cookie opens nothing", store.read_session(db, "erfunden") is None)
            case("an empty cookie opens nothing", store.read_session(db, "") is None)
            second = store.start_session(db, user_id, address="10.0.0.9")
            ended = store.end_all_sessions(db, user_id, except_token=token)
            case("ending the other sessions keeps this browser signed in",
                 ended == 1 and store.read_session(db, token) is not None
                 and store.read_session(db, second) is None)
            store.end_session(db, token)
            case("signing out really removes the session",
                 store.read_session(db, token) is None)
            expired = store.start_session(db, user_id)
            db.execute("UPDATE sessions SET expires = '2020-01-01T00:00:00+00:00'"
                       " WHERE user_id = ?", (user_id,))
            case("an expired session is refused and swept away",
                 store.read_session(db, expired) is None)

            # Lockout
            case("no lockout to begin with", store.locked_out(db, "1.2.3.4", "erich") == 0)
            for _ in range(store.LOCKOUT_TRIES):
                store.record_attempt(db, "1.2.3.4", "erich")
            case("the lockout bites after the set number of tries",
                 store.locked_out(db, "1.2.3.4", "erich") > 0)
            case("it also bites the same name from another address",
                 store.locked_out(db, "9.9.9.9", "erich") > 0)
            case("an unrelated name from an unrelated address still gets in",
                 store.locked_out(db, "9.9.9.9", "andere") == 0)
            store.lift_lockout(db)
            case("the server-side reset lifts it",
                 store.locked_out(db, "1.2.3.4", "erich") == 0)

            # Second factor
            secret = totp.new_secret()
            store.begin_totp(db, user_id, secret)
            case("an unconfirmed secret does not count as two factor",
                 store.user_by_id(db, user_id)["totp_confirmed"] == 0)
            codes = totp.recovery_codes(store.RECOVERY_COUNT)
            store.confirm_totp(db, user_id, totp.current_step(), codes)
            case("confirming switches it on",
                 store.user_by_id(db, user_id)["totp_confirmed"] == 1)
            case("and leaves ten recovery codes",
                 store.recovery_left(db, user_id) == store.RECOVERY_COUNT)
            case("the recovery codes are hashed, not kept as text",
                 db.execute("SELECT COUNT(*) AS n FROM recovery_codes WHERE code_hash = ?",
                            (codes[0],)).fetchone()["n"] == 0)
            case("a recovery code works", store.spend_recovery_code(db, user_id, codes[0]))
            case("THE SAME ONE DOES NOT WORK TWICE",
                 not store.spend_recovery_code(db, user_id, codes[0]))
            case("and one that was never issued does not work",
                 not store.spend_recovery_code(db, user_id, "abcde-fghij"))
            case("nine are left", store.recovery_left(db, user_id) == store.RECOVERY_COUNT - 1)
            store.disable_totp(db, user_id)
            case("switching it off clears the secret and the codes",
                 store.user_by_id(db, user_id)["totp_secret"] == ""
                 and store.recovery_left(db, user_id) == 0)

            store.set_password(db, user_id, "Ein-ganz-neues-2026!")
            case("changing the password clears the forced change",
                 store.user_by_id(db, user_id)["must_change"] == 0)
            store.log_event(db, "self test", username="erich", address="127.0.0.1")
            case("events are written and read back",
                 store.recent_events(db)[0]["what"] == "self test")

        mode = database.stat().st_mode & 0o777
        case("the database is readable by its owner only", mode == 0o600, oct(mode))


# --------------------------------------------------------------------------
# 14. The portal door
# --------------------------------------------------------------------------

class FakeHeaders(dict):
    """Just enough of the header mapping the handler asks for."""
    def get(self, name, default=None):
        for key, value in self.items():
            if key.lower() == name.lower():
                return value
        return default


def handler_with(headers: dict, public_url: str = ""):
    """A handler bound to nothing but the headers, for the header logic."""
    http_mod = load_http()
    handler = http_mod.Handler.__new__(http_mod.Handler)
    handler.headers = FakeHeaders(headers)
    handler.connection = type("C", (), {"context": None})()
    handler.public_url = public_url
    return handler


def test_portal_door() -> None:
    """Which requests the portal lets through, and how the address is read.

    Both cases below come from a deployment that did not work: behind
    Plesk's Docker proxy rules the sign-in form was refused every time,
    and no amount of testing over a plain socket found it. A browser did,
    in one screenshot.
    """
    http_mod = load_http()

    # The header that broke it. no-referrer makes a browser drop the
    # Referer AND serialise Origin as "null" on the following form POST,
    # which is exactly what the same-site check refuses.
    source = pathlib.Path(__file__).parent.joinpath("google-ads-http.py").read_text("utf-8")
    case("THE REFERRER POLICY IS NOT no-referrer",
         'send_header("Referrer-Policy", "no-referrer")' not in source
         and 'send_header("Referrer-Policy", "same-origin")' in source,
         "no-referrer turns Origin into the string null on a form POST")

    on_this_host = {"Host": "ads.mcp.neo-digital.at",
                    "Origin": "https://ads.mcp.neo-digital.at"}
    # Plesk's Docker proxy rules do not send X-Forwarded-Proto.
    case("a form is accepted when the proxy forgets X-Forwarded-Proto",
         handler_with(on_this_host)._same_origin())
    case("and when the proxy does send it",
         handler_with(dict(on_this_host, **{"X-Forwarded-Proto": "https"}))._same_origin())
    case("and when the proxy rewrites the host with a port",
         handler_with({"Host": "127.0.0.1:8788",
                       "X-Forwarded-Host": "ads.mcp.neo-digital.at:443",
                       "Origin": "https://ads.mcp.neo-digital.at"})._same_origin())
    case("a Referer is accepted when there is no Origin",
         handler_with({"Host": "ads.mcp.neo-digital.at",
                       "Referer": "https://ads.mcp.neo-digital.at/anmelden"})._same_origin())
    case("A FORM FROM ANOTHER SITE IS STILL REFUSED",
         not handler_with({"Host": "ads.mcp.neo-digital.at",
                           "Origin": "https://boeser.example"})._same_origin())
    case("a look-alike host is refused",
         not handler_with({"Host": "ads.mcp.neo-digital.at",
                           "Origin": "https://ads.mcp.neo-digital.at.boeser.example"
                           })._same_origin())
    case("a request with neither header is refused",
         not handler_with({"Host": "ads.mcp.neo-digital.at"})._same_origin())
    case("an opaque origin falls through to the Referer",
         handler_with({"Host": "ads.mcp.neo-digital.at", "Origin": "null",
                       "Referer": "https://ads.mcp.neo-digital.at/konto"})._same_origin())
    case("and an opaque origin with no Referer is refused",
         not handler_with({"Host": "ads.mcp.neo-digital.at",
                           "Origin": "null"})._same_origin())

    # The scheme, which decides the redirect URI Google is handed.
    for headers, expected, what in (
            ({"Host": "x.at", "X-Forwarded-Proto": "https"}, "https", "X-Forwarded-Proto"),
            ({"Host": "x.at", "X-Forwarded-Proto": "https, http"}, "https",
             "a list in X-Forwarded-Proto"),
            ({"Host": "x.at", "X-Forwarded-Ssl": "on"}, "https", "X-Forwarded-Ssl"),
            ({"Host": "x.at", "X-Forwarded-Port": "443"}, "https", "X-Forwarded-Port"),
            ({"Host": "x.at", "Origin": "https://x.at"}, "https",
             "the browser's own Origin"),
            ({"Host": "x.at"}, "http", "nothing at all")):
        case(f"the scheme is read from {what}",
             handler_with(headers)._scheme() == expected,
             handler_with(headers)._scheme())
    case("an Origin for a DIFFERENT host does not make it https",
         handler_with({"Host": "x.at", "Origin": "https://andere.at"})._scheme() == "http")
    # Die festgenagelte Adresse darf die Herkunftspruefung nicht verengen.
    case("a pinned address does not lock out a second hostname",
         handler_with({"Host": "127.0.0.1:8788", "Origin": "http://127.0.0.1:8788"},
                      public_url="https://ads.mcp.neo-digital.at")._same_origin(),
         "pinning is for the redirect URI, not for deciding what is same-site")
    case("and a form from elsewhere is still refused with one pinned",
         not handler_with({"Host": "127.0.0.1:8788", "Origin": "https://boeser.example"},
                          public_url="https://ads.mcp.neo-digital.at")._same_origin())
    case("--public-url wins over every header",
         handler_with({"Host": "x.at", "X-Forwarded-Proto": "https"},
                      public_url="http://pinned.example")._base_url()
         == "http://pinned.example")

    # The sign-in pages must be reachable without the address filter, or
    # --anthropic-only locks the operator out of their own server.
    case("the portal paths are recognised",
         all(http_mod.Handler._is_portal_path(p) for p in
             ("/anmelden", "/anmelden/code", "/abmelden", "/konto", "/konto/2fa",
              "/setup", "/setup/guardrails")))
    case("and /mcp is not one of them",
         not http_mod.Handler._is_portal_path("/mcp")
         and not http_mod.Handler._is_portal_path("/health"))
    case("the cookie is HttpOnly and SameSite, and Secure over TLS",
         all(bit in handler_with({"X-Forwarded-Proto": "https"})._cookie_header("abc")
             for bit in ("HttpOnly", "SameSite=Lax", "Secure", "abc")))
    case("and drops Secure where there is no TLS to be had",
         "Secure" not in handler_with({"Host": "x.at"})._cookie_header("abc"))
    # Googles OAuth-Pruefung weist einen Anwendungsnamen ab, der eine
    # Google-Marke enthaelt. Der Name stand in fuenf Dateien und kroch von
    # dort zurueck, also wird er hier festgehalten.
    import google_ads_setup as ui_mod
    import portal_pages as pp
    seite = ui_mod.page("Beispiel", "<p>x</p>").decode("utf-8")
    titel = seite.split("<title>")[1].split("</title>")[0]
    case("THE PAGE TITLE CARRIES NO GOOGLE TRADEMARK",
         "google" not in titel.lower(),
         f"<title>{titel}</title> — Google refuses an app name containing 'Google'")
    kopf = seite.split('class="wo">')[1].split("</span>")[0]
    case("nor does the name beside the word mark",
         "google" not in kopf.lower(), kopf)
    anmeldung = pp.login_page().decode("utf-8")
    case("nor the sign-in page's own title",
         "google" not in anmeldung.split("<title>")[1].split("</title>")[0].lower())
    server = load_server()
    case("nor the connector's display name in claude.ai",
         "google" not in server.server_info()["title"].lower(),
         server.server_info()["title"])
    case("but the technical identifier is left alone",
         server.server_info()["name"] == "neo-google-ads",
         server.server_info()["name"])
    case("and the brand is settable without touching the code",
         gac.PORTAL_NAME == (os.environ.get("GOOGLE_ADS_PORTAL_NAME")
                             or "NEO Digital AdsManagment"),
         gac.PORTAL_NAME)

    case("signing out sends an empty cookie that expires at once",
         "Max-Age=0" in handler_with({})._cookie_header(clear=True))

    # Ein Lesezeichen auf die Anmeldeseite ist kein Fehler. Geprüft wird,
    # wohin der Weg führt — indem _redirect und _setup_get mitgeschrieben
    # statt ausgeführt werden.
    handler = handler_with({"Host": "x.at"})
    gegangen = []
    handler._redirect = lambda wohin, **rest: gegangen.append(("redirect", wohin))
    handler._setup_get = lambda pfad: gegangen.append(("setup", pfad))
    handler._setup_post = lambda pfad: gegangen.append(("setup", pfad))
    handler._client_ip = lambda: None
    handler._account = lambda *a: gegangen.append(("account", a[1]))
    fake_user = {"username": "erich", "id": 1, "totp_confirmed": 0, "must_change": 0}
    for pfad in ("/anmelden", "/anmelden/code", "/abbrechen"):
        gegangen.clear()
        handler._portal_closed(None, pfad, "GET", fake_user, {"token_hash": "x"})
        case(f"{pfad} leads somewhere useful once signed in",
             gegangen == [("redirect", "/setup")], str(gegangen))
    gegangen.clear()
    handler._portal_closed(None, "/setup/guardrails", "GET", fake_user, {"token_hash": "x"})
    case("and the Google pages still go where they went",
         gegangen == [("setup", "/setup/guardrails")], str(gegangen))


# --------------------------------------------------------------------------
# 15. Permission matrix
# --------------------------------------------------------------------------

def denied(code: str = "USER_PERMISSION_DENIED") -> gac.GoogleAdsError:
    """The envelope Google actually sends for a refused account."""
    payload = {"error": {"code": 403, "message": "The caller does not have permission",
                         "status": "PERMISSION_DENIED",
                         "details": [{"errors": [{"errorCode": {"authorizationError": code},
                                                  "message": "User doesn't have permission "
                                                             "to access customer."}]}]}}
    return gac.GoogleAdsError("The caller does not have permission\n"
                              f"  authorizationError={code} — User doesn't have permission.",
                              detail=payload, status=403)


def client_answering(rule) -> gac.Client:
    """A client whose search() follows `rule(customer_id, login) -> bool`."""
    client = make_client()
    calls = []

    def fake_search(customer_id, query, *, max_rows=10000, login_customer_id=None):
        effective = (client.config.get("login_customer_id") or ""
                     if login_customer_id is None else login_customer_id)
        calls.append((customer_id, effective))
        if rule(customer_id, effective):
            return [{"customer": {"id": customer_id}}]
        raise denied()

    client.search = fake_search
    client.calls = calls
    return client


def test_permission_matrix() -> None:
    """The measurement that replaced guessing at USER_PERMISSION_DENIED.

    The API refuses an account without saying whether the manager header
    is wrong, the link is missing, or the token is. Reading the message
    cannot tell those apart — trying can.
    """
    MANAGER, A, B, FREMD = "5303457641", "5691007627", "6286913360", "8323427154"
    ALLE = [FREMD, A, B, MANAGER]

    # Die Projektnummer steckt in der Client-ID und benennt das, woran die
    # Zugriffsstufe haengt. Sie abzulesen erspart den Vergleich von Hand.
    for client_id, soll in (
            ("918722857235-im48itrfkr8voe597isdrmc5o7rfi072.apps.googleusercontent.com",
             "918722857235"),
            ("123456789012-abc.apps.googleusercontent.com", "123456789012"),
            ("keine-nummer.apps.googleusercontent.com", ""),
            ("", "")):
        case(f"the cloud project number is read from {client_id[:18] or 'an empty id'!r}",
             gac.project_number_of(client_id) == soll,
             gac.project_number_of(client_id))

    case("the error code is dug back out of the envelope",
         gac.error_code_of(denied()) == "authorizationError=USER_PERMISSION_DENIED",
         gac.error_code_of(denied()))
    case("and out of a message alone, with no envelope",
         gac.error_code_of(gac.GoogleAdsError(
             "The caller does not have permission\n"
             "  authorizationError=USER_PERMISSION_DENIED — nope")) 
         == "authorizationError=USER_PERMISSION_DENIED")

    # The case in front of us: a manager header that fits nothing.
    client = client_answering(lambda cid, login: login == "")
    client.config["login_customer_id"] = MANAGER
    matrix = client.permission_matrix(ALLE)
    case("every account is found readable without the manager header",
         all(row["works_with"] == "" for row in matrix),
         str([(r["id"], r["works_with"]) for r in matrix]))
    case("and the configured header is recorded as the failure",
         all(row["attempts"][0]["label"] == "wie eingestellt"
             and not row["attempts"][0]["ok"] for row in matrix))
    case("the measurement stops at the first setting that works",
         all(len(row["attempts"]) == 2 for row in matrix),
         str([len(r["attempts"]) for r in matrix]))

    # The other shape: the accounts really are under the manager.
    client = client_answering(lambda cid, login: login == MANAGER)
    client.config["login_customer_id"] = MANAGER
    matrix = client.permission_matrix(ALLE)
    case("with the right manager, one call per account is enough",
         all(len(row["attempts"]) == 1 and row["works_with"] is None
             or row["attempts"][0]["ok"] for row in matrix),
         str([(r["id"], len(r["attempts"])) for r in matrix]))

    # A manager that is not the configured one.
    client = client_answering(lambda cid, login: login == FREMD and cid in (A, B))
    client.config["login_customer_id"] = MANAGER
    matrix = client.permission_matrix(ALLE)
    treffer = {row["id"]: row["works_with"] for row in matrix}
    case("an account readable only under ANOTHER manager is found",
         treffer[A] == FREMD and treffer[B] == FREMD, str(treffer))
    case("and one that no header opens is reported as such",
         treffer[MANAGER] is None and treffer[FREMD] is None, str(treffer))
    case("the failing rows carry the API's error code",
         all(row["code"] == "authorizationError=USER_PERMISSION_DENIED"
             for row in matrix if row["works_with"] is None))

    # Nothing works at all — the header is not the problem.
    client = client_answering(lambda cid, login: False)
    client.config["login_customer_id"] = MANAGER
    matrix = client.permission_matrix(ALLE)
    case("when nothing works, every candidate was tried",
         all(len(row["attempts"]) == len(ALLE) + 1 for row in matrix),
         str([len(r["attempts"]) for r in matrix]))
    case("and no duplicate header is tried twice",
         all(len({(a["login"] if a["login"] is not None else "\x00")
                  for a in row["attempts"]}) == len(row["attempts"])
             for row in matrix))

    # The measured mapping, once adopted, must actually be used.
    client = make_client()
    client.config["login_customer_id"] = MANAGER
    client.config["account_logins"] = {A: "", B: FREMD, MANAGER: MANAGER}
    case("an account mapped to no header gets none",
         client.login_for(A) == "" and client.login_for(A.replace("569", "569")) == "")
    case("an account mapped to another manager gets that one",
         client.login_for(B) == FREMD)
    case("an unmapped account falls back to the configuration",
         client.login_for("1234567890") is None)
    case("and an explicit argument beats the mapping",
         client.login_for(A, MANAGER) == MANAGER)
    case("the mapping is matched with hyphens too",
         client.login_for("569-100-7627") == "")

    gesendet = []
    client.call = lambda method, path, body=None, *, login_customer_id=None: (
        gesendet.append((path, login_customer_id)) or {"results": []})
    client.search(A, "SELECT customer.id FROM customer")
    client.search(B, "SELECT customer.id FROM customer")
    client.search("1234567890", "SELECT customer.id FROM customer")
    case("SEARCH USES THE MAPPED HEADER, PER ACCOUNT",
         [g[1] for g in gesendet] == ["", FREMD, None], str(gesendet))

    # A measurement that consults the mapping it is measuring measures
    # itself. Stubbed at call() so login_for really runs.
    client = make_client()
    client.config["login_customer_id"] = MANAGER
    client.config["account_logins"] = {A: FREMD}
    gesehen = []
    client.call = lambda method, path, body=None, *, login_customer_id=None: (
        gesehen.append(login_customer_id) or {"results": [{"customer": {}}]})
    client.probe_account(A, "")
    case("MEASURING WITHOUT A HEADER REALLY SENDS NONE, MAPPING OR NOT",
         gesehen == [""], str(gesehen))
    client.probe_account(A, MANAGER)
    case("and measuring with one sends that one", gesehen[-1] == MANAGER, str(gesehen))
    client.probe_account(A, None)
    case("'as configured' means the configuration, not the stored mapping",
         gesehen[-1] == MANAGER, f"{gesehen[-1]!r} — the mapping says {FREMD}")

    # load_state must not throw the error code away again.
    setup = load_setup()
    with tempfile.TemporaryDirectory() as folder:
        konfig = pathlib.Path(folder) / "config.json"
        konfig.write_text(json.dumps({
            "client_id": "t", "client_secret": "t", "refresh_token": "t",
            "developer_token": "t", "api_version": "v25",
            "login_customer_id": MANAGER}), encoding="utf-8")
        echte_datei, gac.CONFIG_FILE = gac.CONFIG_FILE, konfig
        echt_liste = gac.Client.list_accessible_customers
        echt_suche = gac.Client.search
        echt_token = gac.Client.access_token
        try:
            gac.Client.list_accessible_customers = lambda self: [A]
            gac.Client.access_token = lambda self: "x"

            def weigern(self, customer_id, query, **rest):
                raise denied()
            gac.Client.search = weigern
            zustand = setup.load_state()
            konto = zustand["accounts"][0]
            case("A REFUSED ACCOUNT KEEPS THE API'S ERROR CODE",
                 konto["code"] == "authorizationError=USER_PERMISSION_DENIED",
                 f"code={konto['code']!r} problem={konto['problem']!r}")
            case("and still carries Google's own sentence",
                 "does not have permission" in konto["problem"])
        finally:
            gac.Client.list_accessible_customers = echt_liste
            gac.Client.search = echt_suche
            gac.Client.access_token = echt_token
            gac.CONFIG_FILE = echte_datei

    # The header itself: three states, and the third is the new one.
    client = make_client()
    client.config["login_customer_id"] = MANAGER
    case("no argument means: take the configured manager",
         client._headers().get("login-customer-id") == MANAGER)  # noqa: SLF001
    case("AN EMPTY STRING MEANS: SEND NO MANAGER HEADER",
         "login-customer-id" not in client._headers(""))  # noqa: SLF001
    case("a value means: send exactly that one",
         client._headers("123-456-7890").get("login-customer-id")  # noqa: SLF001
         == "1234567890")
    case("and measuring does not leave the configuration changed",
         client.config["login_customer_id"] == MANAGER)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove the Google Ads guardrails hold.")
    parser.add_argument("--verbose", action="store_true", help="show the detail of every case")
    options = parser.parse_args()

    print("\nGoogle Ads tools — self test (no network, no credentials)\n")
    for group, run in (("guardrails", test_guardrails),
                       ("guardrails from env", test_guardrails_from_env),
                       ("request shape", test_request_shape),
                       ("errors", test_errors),
                       ("shaping", test_shaping), ("reports", test_reports),
                       ("protocol", test_protocol), ("http door", test_http),
                       ("change log", test_change_log),
                       ("management console", test_console),
                       ("qr code", test_qr), ("two factor", test_two_factor),
                       ("portal accounts", test_portal),
                       ("portal door", test_portal_door),
                       ("permission matrix", test_permission_matrix)):
        start = len(RESULTS)
        run()
        failed = sum(1 for _, ok, _ in RESULTS[start:] if not ok)
        print(f"  {group}: {len(RESULTS) - start - failed}/{len(RESULTS) - start} passed")

    print()
    failures = [(n, d) for n, ok, d in RESULTS if not ok]
    if options.verbose or failures:
        for name, ok, detail in RESULTS:
            if not ok or options.verbose:
                mark = "PASS" if ok else "FAIL"
                print(f"  [{mark}] {name}" + (f"\n         {detail}" if detail else ""))
        print()
    if failures:
        print(f"{len(failures)} of {len(RESULTS)} cases FAILED.")
        return 1
    print(f"All {len(RESULTS)} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
