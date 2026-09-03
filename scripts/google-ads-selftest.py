#!/usr/bin/env python3
"""Proves the guardrails hold, without a network and without credentials.

google-ads-check.py answers 'does the connection work'. This script
answers a different question: 'does the hand brake work'. It runs the
write path against a stand-in for the API and asserts that every
deliberately broken call is refused and every clean one gets through.

That distinction matters. A guardrail that has never been shown to refuse
anything is a comment, not a guardrail — and the thing it is supposed to
stop is a five-figure invoice.

Twenty cases in five groups:

    guardrails    switch off, wrong account, budget ceiling, budget jump,
                  too many operations, and the clean case that must pass
    errors        Google's nested error envelope becomes one readable line
    shaping       micros to currency, nested answer to flat field names
    queries       every prepared report produces valid GAQL
    protocol      the MCP handshake, both generations, and tools/list

    google-ads-selftest.py
    google-ads-selftest.py --verbose

Exit code 0 when every case passed, 1 when one failed.
"""
from __future__ import annotations

import argparse
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
# 6. Change log
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove the Google Ads guardrails hold.")
    parser.add_argument("--verbose", action="store_true", help="show the detail of every case")
    options = parser.parse_args()

    print("\nGoogle Ads tools — self test (no network, no credentials)\n")
    for group, run in (("guardrails", test_guardrails), ("errors", test_errors),
                       ("shaping", test_shaping), ("reports", test_reports),
                       ("protocol", test_protocol), ("change log", test_change_log)):
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
