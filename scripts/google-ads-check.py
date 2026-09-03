#!/usr/bin/env python3
"""Measures whether the Google Ads connection actually works.

Seven checks, in the order in which they fail in practice. Each one names
what to do when it fails, because "connection failed" is not a finding
anyone can act on.

    1  Python version         3.9 or newer
    2  Configuration          present, complete, not world-readable
    3  Refresh token          trades for an access token
    4  Developer token        accepted by the API
    5  Accounts               at least one is readable
    6  Guardrails             what writing is currently allowed to do
    7  Write path             a validate-only mutate reaches Google

Check 7 changes nothing: it sends a deliberately harmless operation with
validateOnly, which makes Google run every rule and write nothing. It is
skipped unless an account is given, because it needs one to aim at.

    google-ads-check.py
    google-ads-check.py --customer-id 123-456-7890
    google-ads-check.py --json

Exit code 0 when every run check passed, 1 when one failed, 2 when the
configuration is missing entirely.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google_ads_client import (  # noqa: E402
    CHANGE_LOG,
    CONFIG_FILE,
    Client,
    GoogleAdsError,
    load_config,
    normalize_customer_id,
)

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class Report:
    """Collects the findings so they can be printed as text or as JSON."""

    def __init__(self):
        self.checks: list[dict] = []

    def add(self, name: str, status: str, detail: str, fix: str = "") -> None:
        self.checks.append({"check": name, "status": status, "detail": detail, "fix": fix})

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c["status"] == FAIL)

    def print_text(self) -> None:
        width = max(len(c["check"]) for c in self.checks)
        for check in self.checks:
            print(f"  [{check['status']}] {check['check']:<{width}}  {check['detail']}")
            if check["fix"] and check["status"] == FAIL:
                for line in check["fix"].splitlines():
                    print(f"         -> {line}")
        print()
        if self.failed:
            print(f"{self.failed} of {len(self.checks)} checks failed.")
        else:
            print(f"All {len(self.checks)} checks passed.")


def check_python(report: Report) -> None:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 9):
        report.add("python", PASS, f"Python {version}")
    else:
        report.add("python", FAIL, f"Python {version}",
                   "The scripts need Python 3.9 or newer.")


def check_config(report: Report) -> dict | None:
    if not CONFIG_FILE.exists() and not os.environ.get("GOOGLE_ADS_CLIENT_ID"):
        report.add("configuration", FAIL, f"{CONFIG_FILE} does not exist",
                   "Run google-ads-auth.py to create it.")
        return None
    try:
        config = load_config()
    except GoogleAdsError as exc:
        report.add("configuration", FAIL, exc.message.splitlines()[0],
                   "Run google-ads-auth.py again.")
        return None

    detail = f"{CONFIG_FILE}, API {config['api_version']}"
    if CONFIG_FILE.exists():
        mode = stat.S_IMODE(CONFIG_FILE.stat().st_mode)
        if mode & 0o077:
            report.add("configuration", FAIL,
                       f"{CONFIG_FILE} is readable by others (mode {mode:o})",
                       f"chmod 600 {CONFIG_FILE}  — it holds a refresh token and a secret.")
            return config
    report.add("configuration", PASS, detail)
    return config


def check_token(report: Report, client: Client) -> bool:
    try:
        token = client.access_token()
    except GoogleAdsError as exc:
        report.add("refresh token", FAIL, exc.message.splitlines()[0],
                   "Run google-ads-auth.py to grant access again.")
        return False
    report.add("refresh token", PASS, f"access token received ({len(token)} chars)")
    return True


def check_accounts(report: Report, client: Client) -> list[str]:
    try:
        ids = client.list_accessible_customers()
    except GoogleAdsError as exc:
        first = exc.message.splitlines()[0]
        if exc.status == 403 or "developer" in exc.message.lower():
            report.add("developer token", FAIL, first,
                       "Check the token in the API Center of your manager account.\n"
                       "A token with TEST access only works on test accounts.")
        else:
            report.add("developer token", FAIL, first, "See the message above.")
        return []
    report.add("developer token", PASS, "accepted by the API")

    if not ids:
        report.add("accounts", FAIL, "no accessible accounts",
                   "The connected Google account is not a user on any Ads account.")
        return []

    readable = []
    for customer_id in ids:
        try:
            rows = client.search(customer_id,
                                 "SELECT customer.descriptive_name, customer.currency_code, "
                                 "customer.manager FROM customer",
                                 page_size=1, max_rows=1)
            if rows:
                readable.append(customer_id)
        except GoogleAdsError:
            continue
    if readable:
        report.add("accounts", PASS,
                   f"{len(readable)} of {len(ids)} accessible accounts are readable")
    else:
        report.add("accounts", FAIL, f"{len(ids)} accounts listed, none readable",
                   "A manager account often needs login_customer_id set. "
                   "Run google-ads-auth.py and give the manager ID.")
    return readable


def check_guardrails(report: Report, client: Client) -> None:
    rails = client.guardrails
    if not rails.get("write_enabled"):
        report.add("guardrails", PASS, "writing is OFF (read-only)")
        return
    allowed = rails.get("allowed_customer_ids") or []
    parts = ["writing is ON",
             f"accounts: {', '.join(allowed) if allowed else 'ALL accessible'}"]
    ceiling = int(rails.get("max_daily_budget_micros") or 0)
    parts.append(f"budget ceiling: {ceiling / 1_000_000:.2f}" if ceiling else "no budget ceiling")
    parts.append(f"max increase: x{rails.get('max_budget_increase_factor')}")
    report.add("guardrails", PASS, "; ".join(parts))


def check_write_path(report: Report, client: Client, customer_id: str) -> None:
    """Sends one validate-only operation, which Google checks and discards."""
    if not customer_id:
        report.add("write path", SKIP, "no --customer-id given")
        return
    try:
        rows = client.search(customer_id,
                             "SELECT campaign.resource_name, campaign.name, campaign.status "
                             "FROM campaign WHERE campaign.status != 'REMOVED' LIMIT 1")
    except GoogleAdsError as exc:
        report.add("write path", FAIL, exc.message.splitlines()[0],
                   "The account could not be read, so a write cannot be tested.")
        return
    if not rows:
        report.add("write path", SKIP, "the account has no campaign to aim a dry run at")
        return

    campaign = rows[0]["campaign"]
    operation = [{"campaignOperation": {
        "update": {"resourceName": campaign["resourceName"], "status": campaign["status"]},
        "updateMask": "status",
    }}]
    try:
        client.mutate(customer_id, operation, dry_run=True,
                      reason="google-ads-check.py self test")
    except GoogleAdsError as exc:
        report.add("write path", FAIL, exc.message.splitlines()[0],
                   "The dry run was refused. The message above says by what.")
        return
    report.add("write path", PASS,
               f"validate-only mutate accepted on campaign '{campaign.get('name', '')}' "
               "(nothing changed)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the Google Ads connection.")
    parser.add_argument("--customer-id", default="",
                        help="account to run the write-path check against")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    options = parser.parse_args()

    report = Report()
    check_python(report)
    config = check_config(report)
    if config is None:
        if options.json:
            print(json.dumps({"checks": report.checks, "failed": report.failed}, indent=2))
        else:
            report.print_text()
        return 2

    client = Client(config)
    if check_token(report, client):
        readable = check_accounts(report, client)
        check_guardrails(report, client)
        customer_id = options.customer_id
        if customer_id:
            customer_id = normalize_customer_id(customer_id)
        elif len(readable) == 1:
            customer_id = readable[0]
        check_write_path(report, client, customer_id)

    if options.json:
        print(json.dumps({"config_file": str(CONFIG_FILE), "change_log": str(CHANGE_LOG),
                          "checks": report.checks, "failed": report.failed}, indent=2))
    else:
        print(f"\nGoogle Ads connection — {CONFIG_FILE}\n")
        report.print_text()
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
