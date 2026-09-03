#!/usr/bin/env python3
"""Talks to the Google Ads API over REST, with a hand brake on writing.

This module is the shared layer under the MCP server, the setup helper
and the self-check. It does four things and nothing else:

    Configuration   read credentials from a file or the environment
    Access token    trade the refresh token for a short-lived token
    Requests        call the REST endpoints and translate the errors
    Guardrails      refuse writes that were not explicitly permitted

WHY THE GUARDRAILS EXIST. Every other call in this module spends real
money on someone's advertising account. A wrong budget field is not a
failed test, it is an invoice. So writing is off until it is switched
on, a write names the account it is allowed to touch, a budget cannot
jump further than a configured factor, and every write that goes out is
written to a log file before the answer comes back.

No dependencies beyond the standard library, so it runs in any CI and in
any Claude Code installation without an install step.

Configuration is read in this order, first hit wins:

    1. environment variables (GOOGLE_ADS_*), for CI
    2. the file named by GOOGLE_ADS_CONFIG
    3. ~/.config/neo-google-ads/config.json

Written by google-ads-auth.py, never by hand if it can be helped.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------
# Constants. The API version is pinned on purpose: Google sunsets versions
# roughly a year after release, and a silent jump to a newer one changes
# field names underneath a running configuration. Override it in the
# configuration when the pinned version reaches its sunset date.
# --------------------------------------------------------------------------

DEFAULT_API_VERSION = "v25"
API_HOST = "https://googleads.googleapis.com"
TOKEN_URL = "https://oauth2.googleapis.com/token"
OAUTH_SCOPE = "https://www.googleapis.com/auth/adwords"

CONFIG_DIR = pathlib.Path(
    os.environ.get("GOOGLE_ADS_HOME")
    or pathlib.Path.home() / ".config" / "neo-google-ads"
)
CONFIG_FILE = pathlib.Path(os.environ.get("GOOGLE_ADS_CONFIG") or CONFIG_DIR / "config.json")
CHANGE_LOG = CONFIG_DIR / "changes.jsonl"

# Fields that may come from the environment instead of the file.
ENV_FIELDS = {
    "client_id": "GOOGLE_ADS_CLIENT_ID",
    "client_secret": "GOOGLE_ADS_CLIENT_SECRET",
    "refresh_token": "GOOGLE_ADS_REFRESH_TOKEN",
    "developer_token": "GOOGLE_ADS_DEVELOPER_TOKEN",
    "login_customer_id": "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
    "api_version": "GOOGLE_ADS_API_VERSION",
}

# Defaults for the guardrails. Deliberately restrictive: a fresh install
# reads but does not write, and switching writing on is a decision the
# account owner makes once, in writing, in the configuration file.
DEFAULT_GUARDRAILS = {
    "write_enabled": False,
    "allowed_customer_ids": [],       # empty means: every accessible account
    "max_daily_budget_micros": 0,     # 0 means: no ceiling
    "max_budget_increase_factor": 3.0,
    "max_operations_per_call": 200,
    "log_changes": True,
}


class GoogleAdsError(Exception):
    """An error the caller is meant to read, not a stack trace."""

    def __init__(self, message: str, *, detail: object = None, status: int = 0):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.status = status


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

def load_config(path: pathlib.Path | None = None) -> dict:
    """Reads the configuration, environment first, and checks it is complete."""
    path = path or CONFIG_FILE
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise GoogleAdsError(f"Configuration file {path} is not valid JSON: {exc}") from exc

    for field, env_name in ENV_FIELDS.items():
        value = os.environ.get(env_name)
        if value:
            data[field] = value

    guardrails = dict(DEFAULT_GUARDRAILS)
    guardrails.update(data.get("guardrails") or {})
    if os.environ.get("GOOGLE_ADS_ALLOW_WRITE") == "1":
        guardrails["write_enabled"] = True
    data["guardrails"] = guardrails
    data.setdefault("api_version", DEFAULT_API_VERSION)

    missing = [f for f in ("client_id", "client_secret", "refresh_token", "developer_token")
               if not data.get(f)]
    if missing:
        raise GoogleAdsError(
            "Configuration incomplete, missing: " + ", ".join(missing)
            + f". Run google-ads-auth.py to create {path}."
        )
    return data


def save_config(data: dict, path: pathlib.Path | None = None) -> pathlib.Path:
    """Writes the configuration readable by its owner only."""
    path = path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)
    return path


def normalize_customer_id(customer_id: str | int) -> str:
    """Strips the hyphens Google writes in the interface but rejects in the API."""
    digits = "".join(c for c in str(customer_id) if c.isdigit())
    if not digits:
        raise GoogleAdsError(f"'{customer_id}' is not a customer ID. Expected ten digits.")
    return digits


# --------------------------------------------------------------------------
# The client
# --------------------------------------------------------------------------

class Client:
    """One configured connection to the Google Ads API."""

    def __init__(self, config: dict | None = None, *, timeout: int = 120):
        self.config = config if config is not None else load_config()
        self.guardrails = self.config["guardrails"]
        self.api_version = self.config.get("api_version") or DEFAULT_API_VERSION
        self.timeout = timeout
        self._token = ""
        self._token_expires = 0.0

    # -- authentication ----------------------------------------------------

    def access_token(self) -> str:
        """Returns a valid access token, refreshing it a minute before it dies."""
        if self._token and time.time() < self._token_expires - 60:
            return self._token

        payload = urllib.parse.urlencode({
            "client_id": self.config["client_id"],
            "client_secret": self.config["client_secret"],
            "refresh_token": self.config["refresh_token"],
            "grant_type": "refresh_token",
        }).encode("utf-8")
        request = urllib.request.Request(TOKEN_URL, data=payload, method="POST")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise GoogleAdsError(
                "Could not refresh the access token. The refresh token is probably "
                "revoked or the OAuth client changed. Run google-ads-auth.py again.",
                detail=detail, status=exc.code,
            ) from exc
        except urllib.error.URLError as exc:
            raise GoogleAdsError(f"Cannot reach {TOKEN_URL}: {exc.reason}") from exc

        self._token = body["access_token"]
        self._token_expires = time.time() + int(body.get("expires_in", 3600))
        return self._token

    # -- transport ---------------------------------------------------------

    def _headers(self, login_customer_id: str = "") -> dict:
        headers = {
            "Authorization": f"Bearer {self.access_token()}",
            "developer-token": self.config["developer_token"],
            "Content-Type": "application/json",
        }
        login = login_customer_id or self.config.get("login_customer_id") or ""
        if login:
            headers["login-customer-id"] = normalize_customer_id(login)
        return headers

    def call(self, method: str, path: str, body: dict | None = None,
             *, login_customer_id: str = "") -> dict:
        """One REST call. Raises GoogleAdsError with the API's own wording."""
        url = f"{API_HOST}/{self.api_version}/{path.lstrip('/')}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        for key, value in self._headers(login_customer_id).items():
            request.add_header(key, value)

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise self._translate(exc) from exc
        except urllib.error.URLError as exc:
            raise GoogleAdsError(f"Cannot reach {url}: {exc.reason}") from exc

    def _translate(self, exc: urllib.error.HTTPError) -> GoogleAdsError:
        """Turns the API's nested error envelope into one readable sentence.

        A Google Ads failure arrives as error.details[].errors[], each with
        an errorCode object whose single key names the failing rule. Read
        raw it is unusable; the message below names rule, wording and the
        field that triggered it.
        """
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return GoogleAdsError(f"HTTP {exc.code} from the Google Ads API: {raw[:800]}",
                                  status=exc.code)

        error = payload.get("error") or {}
        lines: list[str] = []
        for detail in error.get("details") or []:
            for item in detail.get("errors") or []:
                code = item.get("errorCode") or {}
                name = ": ".join(f"{k}={v}" for k, v in code.items()) or "error"
                location = item.get("location") or {}
                where = ".".join(
                    str(f.get("fieldName", "")) for f in location.get("fieldPathElements") or []
                )
                text = item.get("message", "")
                lines.append(f"{name} — {text}" + (f" (field: {where})" if where else ""))

        summary = error.get("message") or f"HTTP {exc.code}"
        if lines:
            summary += "\n  " + "\n  ".join(lines)
        if exc.code == 401:
            summary += "\n  Hint: the access token was rejected. Run google-ads-auth.py again."
        if exc.code == 403 and "developer" in raw.lower():
            summary += ("\n  Hint: the developer token is missing, wrong, or has no access "
                        "to this account. Check the API Center of your manager account.")
        return GoogleAdsError(summary, detail=payload, status=exc.code)

    # -- reading -----------------------------------------------------------

    def list_accessible_customers(self) -> list[str]:
        """The accounts this refresh token may see, as bare customer IDs."""
        answer = self.call("GET", "customers:listAccessibleCustomers")
        return [name.split("/")[-1] for name in answer.get("resourceNames", [])]

    def search(self, customer_id: str, query: str, *, page_size: int = 1000,
               max_rows: int = 10000, login_customer_id: str = "") -> list[dict]:
        """Runs a GAQL query and follows the pages until max_rows is reached."""
        customer_id = normalize_customer_id(customer_id)
        rows: list[dict] = []
        page_token = ""
        while True:
            body: dict = {"query": query, "pageSize": min(page_size, 10000)}
            if page_token:
                body["pageToken"] = page_token
            answer = self.call("POST", f"customers/{customer_id}/googleAds:search", body,
                               login_customer_id=login_customer_id)
            rows.extend(answer.get("results", []))
            page_token = answer.get("nextPageToken", "")
            if not page_token or len(rows) >= max_rows:
                break
        return rows[:max_rows]

    # -- writing -----------------------------------------------------------

    def mutate(self, customer_id: str, operations: list[dict], *, dry_run: bool = True,
               partial_failure: bool = False, login_customer_id: str = "",
               response_content_type: str = "RESOURCE_NAME_ONLY",
               reason: str = "") -> dict:
        """Sends mutate operations. Refuses everything the guardrails forbid.

        dry_run maps to the API's validateOnly: the request is checked
        against every rule Google would apply, and nothing is changed. It
        is the default because the expensive mistake here is a write that
        was meant as a question.
        """
        customer_id = normalize_customer_id(customer_id)
        self.check_write_allowed(customer_id, operations, dry_run=dry_run)

        body = {
            "mutateOperations": operations,
            "validateOnly": bool(dry_run),
            "partialFailure": bool(partial_failure),
            "responseContentType": response_content_type,
        }
        started = time.time()
        try:
            answer = self.call("POST", f"customers/{customer_id}/googleAds:mutate", body,
                               login_customer_id=login_customer_id)
        except GoogleAdsError as exc:
            self.log_change(customer_id, operations, dry_run=dry_run, reason=reason,
                            result="error", detail=exc.message)
            raise
        self.log_change(customer_id, operations, dry_run=dry_run, reason=reason,
                        result="ok", detail=answer,
                        duration_ms=int((time.time() - started) * 1000))
        return answer

    # -- guardrails --------------------------------------------------------

    def check_write_allowed(self, customer_id: str, operations: list[dict],
                            *, dry_run: bool) -> None:
        """Four questions before anything leaves the machine.

        A dry run passes the switch and the account list too: a validation
        that would be refused live must be refused now, otherwise the dry
        run answers a question nobody asked.
        """
        rails = self.guardrails

        if not rails.get("write_enabled") and not dry_run:
            raise GoogleAdsError(
                "Writing is switched off. Set guardrails.write_enabled to true in "
                f"{CONFIG_FILE} (or export GOOGLE_ADS_ALLOW_WRITE=1) once the account "
                "owner has agreed to it."
            )

        allowed = [normalize_customer_id(c) for c in (rails.get("allowed_customer_ids") or [])]
        if allowed and customer_id not in allowed:
            raise GoogleAdsError(
                f"Account {customer_id} is not in guardrails.allowed_customer_ids. "
                "Add it there before changing anything in it."
            )

        limit = int(rails.get("max_operations_per_call") or 0)
        if limit and len(operations) > limit:
            raise GoogleAdsError(
                f"{len(operations)} operations in one call, the limit is {limit}. "
                "Split the change into smaller steps so each one can be reviewed."
            )

        for operation in operations:
            self._check_budget(operation, customer_id)

    def _check_budget(self, operation: dict, customer_id: str) -> None:
        """Stops a budget from leaving the agreed range.

        Two ways to lose money by one keystroke: writing euros where the
        API wants micros (a factor of a million), and raising a budget by
        an order of magnitude in one step. Both are caught here.
        """
        budget_op = operation.get("campaignBudgetOperation")
        if not budget_op:
            return
        resource = budget_op.get("create") or budget_op.get("update") or {}
        amount = resource.get("amountMicros")
        if amount in (None, ""):
            return
        amount = int(amount)

        ceiling = int(self.guardrails.get("max_daily_budget_micros") or 0)
        if ceiling and amount > ceiling:
            raise GoogleAdsError(
                f"Budget {amount / 1_000_000:.2f} per day is above the agreed ceiling of "
                f"{ceiling / 1_000_000:.2f} (guardrails.max_daily_budget_micros). "
                "Raise the ceiling deliberately or lower the budget."
            )

        factor = float(self.guardrails.get("max_budget_increase_factor") or 0)
        name = budget_op.get("update", {}).get("resourceName")
        if not factor or not name:
            return
        current = self._current_budget_micros(customer_id, name)
        if current and amount > current * factor:
            raise GoogleAdsError(
                f"Budget would go from {current / 1_000_000:.2f} to {amount / 1_000_000:.2f} "
                f"per day, more than the agreed factor of {factor}. Take a smaller step, or "
                "raise guardrails.max_budget_increase_factor after agreeing on it."
            )

    def _current_budget_micros(self, customer_id: str, resource_name: str) -> int:
        """Reads the budget that is in place now, so the step can be measured."""
        query = ("SELECT campaign_budget.amount_micros FROM campaign_budget "
                 f"WHERE campaign_budget.resource_name = '{resource_name}'")
        try:
            rows = self.search(customer_id, query, page_size=1, max_rows=1)
        except GoogleAdsError:
            return 0
        if not rows:
            return 0
        return int(rows[0].get("campaignBudget", {}).get("amountMicros") or 0)

    # -- evidence ----------------------------------------------------------

    def log_change(self, customer_id: str, operations: list[dict], *, dry_run: bool,
                   result: str, reason: str = "", detail: object = None,
                   duration_ms: int = 0) -> None:
        """Appends one line per write attempt, dry runs included.

        The log is the answer to 'who changed this and why'. It is written
        before the caller sees the answer, so a crash cannot swallow it.
        """
        if not self.guardrails.get("log_changes", True):
            return
        entry = {
            "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "customer_id": customer_id,
            "dry_run": dry_run,
            "result": result,
            "reason": reason,
            "operation_count": len(operations),
            "operations": operations,
            "duration_ms": duration_ms,
            "detail": detail,
        }
        try:
            CHANGE_LOG.parent.mkdir(parents=True, exist_ok=True)
            with CHANGE_LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            os.chmod(CHANGE_LOG, 0o600)
        except OSError:
            pass  # A log that cannot be written must not stop the change.
