#!/usr/bin/env python3
"""Connects a Google account to the Google Ads tools, once.

It asks for the four things Google requires, opens a browser so the
account owner can grant access, trades the resulting code for a refresh
token, and writes everything to ~/.config/neo-google-ads/config.json
with owner-only permissions.

WHAT GOOGLE REQUIRES AND WHY IT CANNOT BE AUTOMATED. Two of the four
items are issued by Google to a named person and cannot be created by a
script:

    OAuth client ID + secret   Google Cloud Console, type "Desktop app".
                               Identifies the program asking for access.
    Developer token            API Center of a Google Ads MANAGER account.
                               Identifies who is allowed to call the API
                               at all. A fresh token has test access: it
                               works against test accounts only until
                               Google grants basic access on application.

The other two this script handles: the refresh token (through the browser
consent screen) and the manager account ID.

The flow is the loopback redirect with PKCE, which is what Google
prescribes for installed applications. The out-of-band copy-paste flow
Google used to offer was switched off in 2022, so there has to be a
browser somewhere — on this machine, or on another one with --paste-url.

    google-ads-auth.py                    ask, open a browser, write the file
    google-ads-auth.py --paste-url        no browser here: paste the URL back
    google-ads-auth.py --show             print the current configuration
    google-ads-auth.py --allow-write      switch writing on (asks first)
    google-ads-auth.py --env              print it as a .env block for a cloud session

Exit code 0 on success, 1 on a failed or abandoned connection.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import http.server
import json
import os
import secrets
import socket
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google_ads_client import (  # noqa: E402
    CONFIG_FILE,
    DEFAULT_API_VERSION,
    DEFAULT_GUARDRAILS,
    Client,
    GoogleAdsError,
    OAUTH_SCOPE,
    TOKEN_URL,
    load_config,
    normalize_customer_id,
    save_config,
)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

CONSOLE_HINT = """
Before this can run you need two things from Google. Both are one-time.

  1. An OAuth client (client ID and client secret)
     https://console.cloud.google.com/apis/credentials
     Create a project, enable the "Google Ads API", then
     Credentials -> Create credentials -> OAuth client ID -> Desktop app.

  2. A developer token
     https://ads.google.com/aw/apicenter  (needs a MANAGER account)
     Tools -> API Center. A new token starts with TEST access, which only
     works against test accounts. Apply for basic access in the same place
     to use it on live accounts.

The account you grant access to in the browser must be a user on the Google
Ads accounts you want to manage.
"""

DONE_PAGE = b"""<!doctype html><meta charset="utf-8">
<title>Connected</title>
<body style="font-family:system-ui;margin:4rem auto;max-width:32rem">
<h1>Connected.</h1>
<p>The refresh token was handed to google-ads-auth.py. You can close this tab
and go back to the terminal.</p>
"""

FAILED_PAGE = b"""<!doctype html><meta charset="utf-8">
<title>Not connected</title>
<body style="font-family:system-ui;margin:4rem auto;max-width:32rem">
<h1>Not connected.</h1>
<p>Google reported an error instead of a code. The terminal has the details.</p>
"""


# --------------------------------------------------------------------------
# The loopback receiver
# --------------------------------------------------------------------------

class CodeReceiver(http.server.BaseHTTPRequestHandler):
    """Catches the single redirect Google sends back with the code."""

    code = ""
    error = ""

    def do_GET(self):  # noqa: N802 - name fixed by the base class
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        CodeReceiver.code = (query.get("code") or [""])[0]
        CodeReceiver.error = (query.get("error") or [""])[0]
        body = DONE_PAGE if CodeReceiver.code else FAILED_PAGE
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # The browser's own noise is not the operator's problem.


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def pkce_pair() -> tuple[str, str]:
    """Verifier and its S256 challenge, as Google requires for desktop clients."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def authorize(client_id: str, client_secret: str, *, paste_url: bool) -> str:
    """Runs the consent flow and returns the refresh token."""
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)
    port = free_port()
    redirect_uri = f"http://127.0.0.1:{port}"

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": OAUTH_SCOPE,
        "access_type": "offline",
        "prompt": "consent",          # forces a refresh token even on re-consent
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    if paste_url:
        print("\nOpen this URL in a browser on ANY machine:\n")
        print(url)
        print("\nAfter granting access the browser lands on a 127.0.0.1 address that")
        print("will not load. That is expected. Copy the WHOLE address bar and paste")
        print("it here.\n")
        pasted = input("Redirect URL: ").strip()
        query = urllib.parse.parse_qs(urllib.parse.urlparse(pasted).query)
        if (query.get("state") or [""])[0] != state:
            raise GoogleAdsError("The pasted URL carries a different state value. "
                                 "Start over rather than trusting it.")
        code = (query.get("code") or [""])[0]
        if not code:
            raise GoogleAdsError(f"No code in that URL: {(query.get('error') or ['none'])[0]}")
    else:
        server = http.server.HTTPServer(("127.0.0.1", port), CodeReceiver)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        print(f"\nOpening the consent screen. If nothing happens, open this yourself:\n\n{url}\n")
        webbrowser.open(url)
        print("Waiting for Google to redirect back ... (Ctrl-C to abort)")
        thread.join(timeout=300)
        server.server_close()
        if CodeReceiver.error:
            raise GoogleAdsError(f"Google refused the request: {CodeReceiver.error}")
        code = CodeReceiver.code
        if not code:
            raise GoogleAdsError("No code arrived within five minutes. "
                                 "If this machine has no browser, use --paste-url.")

    payload = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }).encode("utf-8")
    request = urllib.request.Request(TOKEN_URL, data=payload, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise GoogleAdsError(
            "Google rejected the code: " + exc.read().decode("utf-8", "replace")
        ) from exc

    token = body.get("refresh_token", "")
    if not token:
        raise GoogleAdsError(
            "Google returned no refresh token. This happens when the account already "
            "granted access to this client. Remove the entry at "
            "https://myaccount.google.com/permissions and run this again."
        )
    return token


# --------------------------------------------------------------------------
# Asking
# --------------------------------------------------------------------------

def ask(prompt: str, current: str = "", *, secret: bool = False) -> str:
    """One question, with the current value as the default.

    A secret is read without echo, so it does not end up on screen, in a
    scrollback buffer, or in a screen share. Nothing visible appears while
    typing or pasting, which looks like a hung prompt — so the length of
    what arrived is confirmed afterwards.
    """
    shown = f" [{'*' * 8 if secret else current}]" if current else ""
    if secret:
        answer = getpass.getpass(f"{prompt}{shown} (input stays hidden): ").strip()
        if answer:
            print(f"  {len(answer)} characters received.")
    else:
        answer = input(f"{prompt}{shown}: ").strip()
    return answer or current


def ask_yes(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    answer = input(f"{prompt}{suffix}: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes", "j", "ja")


def existing_config() -> dict:
    """Reads what is already there, without insisting it is complete."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def verify(config: dict) -> bool:
    """Calls the API once, so 'connected' is measured and not assumed."""
    print("\nChecking the connection ...")
    try:
        client = Client(dict(config, guardrails=dict(DEFAULT_GUARDRAILS,
                                                     **(config.get("guardrails") or {}))))
        ids = client.list_accessible_customers()
    except GoogleAdsError as exc:
        print(f"\n  FAILED: {exc.message}\n", file=sys.stderr)
        return False

    print(f"  OK: {len(ids)} accessible account(s).")
    for customer_id in ids[:25]:
        label = customer_id
        try:
            rows = client.search(
                customer_id,
                "SELECT customer.descriptive_name, customer.currency_code, "
                "customer.manager, customer.test_account FROM customer",
                page_size=1, max_rows=1,
            )
            if rows:
                customer = rows[0].get("customer", {})
                marks = []
                if customer.get("manager"):
                    marks.append("manager")
                if customer.get("testAccount"):
                    marks.append("test account")
                label = (f"{customer_id}  {customer.get('descriptiveName', '')} "
                         f"({customer.get('currencyCode', '?')})"
                         + (f" [{', '.join(marks)}]" if marks else ""))
        except GoogleAdsError as exc:
            label = f"{customer_id}  (not readable: {exc.message.splitlines()[0]})"
        print(f"    {label}")
    if len(ids) > 25:
        print(f"    ... and {len(ids) - 25} more")
    return True


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------

def show() -> int:
    """Prints the configuration without the secrets."""
    try:
        config = load_config()
    except GoogleAdsError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    safe = {
        "config_file": str(CONFIG_FILE),
        "api_version": config["api_version"],
        "login_customer_id": config.get("login_customer_id", ""),
        "client_id": config["client_id"][:24] + "...",
        "client_secret": "set" if config.get("client_secret") else "missing",
        "refresh_token": "set" if config.get("refresh_token") else "missing",
        "developer_token": config["developer_token"][:6] + "..." ,
        "guardrails": config["guardrails"],
    }
    print(json.dumps(safe, indent=2, ensure_ascii=False))
    return 0


def show_env() -> int:
    """Prints the configuration as a .env block, secrets included.

    This is the bridge to a machine that has no browser and keeps no
    files: a cloud session, a CI runner, a container. The browser step
    happens once on a desktop, and the result travels as four variables.

    It prints real secrets on purpose, so it asks first and says where
    they are going. Anyone who can read the block can spend money on the
    connected accounts.
    """
    try:
        config = load_config()
    except GoogleAdsError as exc:
        print(exc.message, file=sys.stderr)
        return 1

    print("\nThis prints the refresh token, the client secret and the developer")
    print("token in clear text. Paste them only into a place that keeps secrets:")
    print("the environment variables of a Claude Code cloud environment, a CI")
    print("secret store. Never into a repository, a chat, or a ticket.\n")
    if not ask_yes("Print them now?", default=False):
        print("Nothing printed.")
        return 0

    lines = [
        f"GOOGLE_ADS_CLIENT_ID={config['client_id']}",
        f"GOOGLE_ADS_CLIENT_SECRET={config['client_secret']}",
        f"GOOGLE_ADS_REFRESH_TOKEN={config['refresh_token']}",
        f"GOOGLE_ADS_DEVELOPER_TOKEN={config['developer_token']}",
    ]
    if config.get("login_customer_id"):
        lines.append(f"GOOGLE_ADS_LOGIN_CUSTOMER_ID={config['login_customer_id']}")
    lines.append(f"GOOGLE_ADS_API_VERSION={config['api_version']}")
    if config["guardrails"].get("write_enabled"):
        lines.append("GOOGLE_ADS_ALLOW_WRITE=1")

    print("-" * 68)
    print("\n".join(lines))
    print("-" * 68)
    print("\nThe guardrails other than the write switch live in the configuration")
    print("file, not in these variables. A machine that only has the variables")
    print("runs with the defaults: no account list, no budget ceiling. Set them")
    print("there deliberately if that machine may write.")
    print("\nThe session also needs to reach these hosts:")
    print("  googleads.googleapis.com    the API itself")
    print("  oauth2.googleapis.com       refreshing the access token")
    return 0


def allow_write() -> int:
    """Switches writing on after saying plainly what that means."""
    config = existing_config()
    if not config:
        print(f"No configuration at {CONFIG_FILE}. Run this script without arguments first.",
              file=sys.stderr)
        return 1
    print("\nSwitching writing on means the agent can change campaigns, budgets, keywords")
    print("and bids in the accounts listed below, and that those changes cost money.")
    print("Every write is still a dry run unless the caller explicitly asks for a real one,")
    print(f"and every attempt is logged. Configuration: {CONFIG_FILE}\n")

    guardrails = dict(DEFAULT_GUARDRAILS, **(config.get("guardrails") or {}))
    if not ask_yes("Switch writing on?", default=False):
        print("Left off.")
        return 0
    guardrails["write_enabled"] = True

    accounts = ask("Accounts that may be changed, comma separated (empty = all accessible)",
                   ",".join(guardrails.get("allowed_customer_ids") or []))
    guardrails["allowed_customer_ids"] = [
        normalize_customer_id(a) for a in accounts.split(",") if a.strip()
    ]

    ceiling = ask("Highest daily budget any single budget may be set to, in your currency "
                  "(0 = no ceiling)",
                  str(int(guardrails.get("max_daily_budget_micros", 0)) // 1_000_000))
    try:
        guardrails["max_daily_budget_micros"] = int(float(ceiling) * 1_000_000)
    except ValueError:
        guardrails["max_daily_budget_micros"] = 0

    factor = ask("Largest budget increase in one step, as a factor",
                 str(guardrails.get("max_budget_increase_factor", 3.0)))
    try:
        guardrails["max_budget_increase_factor"] = float(factor)
    except ValueError:
        pass

    config["guardrails"] = guardrails
    save_config(config)
    print(f"\nWriting is on. {CONFIG_FILE} updated.")
    print(json.dumps(guardrails, indent=2))
    return 0


def setup(paste_url: bool, keep_token: bool) -> int:
    config = existing_config()
    print(CONSOLE_HINT)
    if not ask_yes("Do you have both of those?", default=True):
        print("Get them first, then run this again.")
        return 1

    print("\n-- OAuth client --")
    client_id = ask("Client ID", config.get("client_id", ""))
    client_secret = ask("Client secret", config.get("client_secret", ""), secret=True)
    if not client_id or not client_secret:
        print("Both are required.", file=sys.stderr)
        return 1

    print("\n-- Developer token --")
    developer_token = ask("Developer token", config.get("developer_token", ""), secret=True)
    if not developer_token:
        print("A developer token is required.", file=sys.stderr)
        return 1

    print("\n-- Manager account --")
    print("If you manage other people's accounts, give the manager (MCC) account ID.")
    print("If you only have your own account, leave this empty.")
    login = ask("Manager customer ID", config.get("login_customer_id", ""))
    login = normalize_customer_id(login) if login else ""

    refresh_token = config.get("refresh_token", "")
    if refresh_token and keep_token:
        print("\nKeeping the existing refresh token.")
    else:
        print("\n-- Granting access --")
        try:
            refresh_token = authorize(client_id, client_secret, paste_url=paste_url)
        except GoogleAdsError as exc:
            print(f"\n{exc.message}\n", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("\nAborted.", file=sys.stderr)
            return 1
        print("  Refresh token received.")

    config.update({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "developer_token": developer_token,
        "login_customer_id": login,
        "api_version": config.get("api_version") or DEFAULT_API_VERSION,
    })
    config["guardrails"] = dict(DEFAULT_GUARDRAILS, **(config.get("guardrails") or {}))
    path = save_config(config)
    print(f"\nWritten to {path} (readable by you only).")

    if not verify(config):
        print("The configuration was saved but the API refused it. Fix the reason above "
              "and run this again.", file=sys.stderr)
        return 1

    print("\nDone. Reading works.")
    if not config["guardrails"]["write_enabled"]:
        print("Writing is OFF. Switch it on with:  google-ads-auth.py --allow-write")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Connect a Google account to the Google Ads tools.")
    parser.add_argument("--paste-url", action="store_true",
                        help="no browser on this machine: print the URL and read the redirect back")
    parser.add_argument("--keep-token", action="store_true",
                        help="keep the stored refresh token, only change the other fields")
    parser.add_argument("--show", action="store_true",
                        help="print the current configuration without the secrets")
    parser.add_argument("--allow-write", action="store_true",
                        help="switch writing on and set the guardrails")
    parser.add_argument("--env", action="store_true",
                        help="print the credentials as a .env block, for a cloud session or CI")
    options = parser.parse_args()

    if options.show:
        return show()
    if options.env:
        return show_env()
    if options.allow_write:
        return allow_write()
    try:
        return setup(options.paste_url, options.keep_token)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
