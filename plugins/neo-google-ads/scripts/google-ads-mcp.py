#!/usr/bin/env python3
"""An MCP server that gives an agent read and write access to Google Ads.

It speaks JSON-RPC over stdin and stdout and offers twenty-five tools:
fourteen that read, ten that write, and one that shows what was written.
The reading half covers accounts, arbitrary GAQL queries, prepared
reports, the Keyword Planner and the field catalogue — and, since 2.5.0,
Google Search Console (properties, search performance, URL inspection,
sitemaps) and Google Analytics 4 (properties, reports, field catalogue,
since 2.6.0 the property settings). The writing half covers keywords,
negative keywords, status, budgets, bids, and — for everything the six do
not cover — the raw mutate endpoint; since 2.6.0 also sitemaps in Search
Console and key events and custom dimensions in Analytics. Settings that
decide how much is collected about visitors have no tool, on purpose.

TWO PROTOCOL GENERATIONS. MCP dropped the initialize handshake in the
2026-07-28 revision and replaced it with server/discover. Clients in the
field speak both, so this server answers both and mirrors back whichever
protocol version the client asked for.

WRITING IS A DECISION, NOT A DEFAULT. Every write tool starts as a dry
run, which changes nothing. For Google Ads that is the API's validateOnly,
which runs the change through every rule Google would apply; Search
Console and Analytics have no such thing, so their dry run reads the
current state and describes the change. Passing dry_run=false is what
makes it real, and even then the guardrails in google_ads_client.py have
the last word.

No dependencies beyond the standard library.

    google-ads-mcp.py                 speak MCP on stdin/stdout
    google-ads-mcp.py --list-tools    print the tool catalogue and exit

Diagnostics go to stderr; stdout carries nothing but protocol.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import traceback
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google_ads_client import (  # noqa: E402
    CHANGE_LOG,
    PORTAL_NAME,
    Client,
    GoogleAdsError,
    load_config,
    normalize_customer_id,
)

SERVER_NAME = "neo-google-ads"
SERVER_VERSION = "2.6.0"

# Protocol revisions this server can answer, newest first. The 2026-07-28
# revision replaced initialize with server/discover; the older ones are
# still what most installed clients speak.
PROTOCOL_VERSIONS = ("2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

# How many rows a single answer may carry. A GAQL query can return ten
# thousand rows; an agent that receives them cannot think about anything
# else afterwards. The cap is a parameter, this is only the default.
DEFAULT_ROW_LIMIT = 200

DATE_RANGES = (
    "TODAY", "YESTERDAY", "LAST_7_DAYS", "LAST_14_DAYS", "LAST_30_DAYS",
    "THIS_MONTH", "LAST_MONTH", "THIS_WEEK_MON_TODAY", "LAST_BUSINESS_WEEK",
)

MATCH_TYPES = ("EXACT", "PHRASE", "BROAD")


# --------------------------------------------------------------------------
# Prepared reports
#
# Every one of these is a GAQL query somebody would otherwise have to write
# by hand and get subtly wrong. `date` says whether a date range belongs in
# the WHERE clause: a budget has no daily metrics, a search term has nothing
# else. `order` is the column that makes the report answer its own question.
# --------------------------------------------------------------------------

REPORTS = {
    "campaigns": {
        "fields": [
            "campaign.id", "campaign.name", "campaign.status",
            "campaign.advertising_channel_type", "campaign.bidding_strategy_type",
            "campaign_budget.amount_micros", "campaign.optimization_score",
            "metrics.impressions", "metrics.clicks", "metrics.ctr",
            "metrics.average_cpc", "metrics.cost_micros", "metrics.conversions",
            "metrics.conversions_value", "metrics.cost_per_conversion",
            "metrics.search_impression_share",
        ],
        "from": "campaign", "date": True, "order": "metrics.cost_micros DESC",
        "help": "Campaigns with spend, clicks, conversions and impression share.",
    },
    "ad_groups": {
        "fields": [
            "campaign.name", "ad_group.id", "ad_group.name", "ad_group.status",
            "ad_group.cpc_bid_micros", "metrics.impressions", "metrics.clicks",
            "metrics.ctr", "metrics.average_cpc", "metrics.cost_micros",
            "metrics.conversions", "metrics.cost_per_conversion",
        ],
        "from": "ad_group", "date": True, "order": "metrics.cost_micros DESC",
        "help": "Ad groups with spend and conversions.",
    },
    "keywords": {
        "fields": [
            "campaign.name", "ad_group.name", "ad_group_criterion.criterion_id",
            "ad_group_criterion.keyword.text", "ad_group_criterion.keyword.match_type",
            "ad_group_criterion.status", "ad_group_criterion.effective_cpc_bid_micros",
            "ad_group_criterion.quality_info.quality_score",
            "ad_group_criterion.quality_info.creative_quality_score",
            "ad_group_criterion.quality_info.post_click_quality_score",
            "ad_group_criterion.quality_info.search_predicted_ctr",
            "metrics.impressions", "metrics.clicks", "metrics.ctr",
            "metrics.average_cpc", "metrics.cost_micros", "metrics.conversions",
            "metrics.cost_per_conversion",
        ],
        "from": "keyword_view", "date": True, "order": "metrics.cost_micros DESC",
        "help": "Positive keywords with quality score and cost per conversion.",
    },
    "search_terms": {
        "fields": [
            "campaign.name", "ad_group.name", "search_term_view.search_term",
            "search_term_view.status", "segments.keyword.info.text",
            "segments.keyword.info.match_type", "metrics.impressions", "metrics.clicks",
            "metrics.ctr", "metrics.cost_micros", "metrics.conversions",
        ],
        "from": "search_term_view", "date": True, "order": "metrics.cost_micros DESC",
        "help": "What people actually typed. The source for negative keywords.",
    },
    "negative_keywords_campaign": {
        "fields": [
            "campaign.name", "campaign_criterion.criterion_id",
            "campaign_criterion.keyword.text", "campaign_criterion.keyword.match_type",
            "campaign_criterion.type", "campaign_criterion.status",
        ],
        "from": "campaign_criterion", "date": False,
        "where": "campaign_criterion.negative = TRUE AND campaign_criterion.type = 'KEYWORD'",
        "help": "Negative keywords on campaign level.",
    },
    "negative_keywords_ad_group": {
        "fields": [
            "campaign.name", "ad_group.name", "ad_group_criterion.criterion_id",
            "ad_group_criterion.keyword.text", "ad_group_criterion.keyword.match_type",
            "ad_group_criterion.status",
        ],
        "from": "ad_group_criterion", "date": False,
        "where": "ad_group_criterion.negative = TRUE AND ad_group_criterion.type = 'KEYWORD'",
        "help": "Negative keywords on ad group level.",
    },
    "shared_negative_lists": {
        "fields": [
            "shared_set.id", "shared_set.name", "shared_set.type",
            "shared_set.status", "shared_set.member_count",
        ],
        "from": "shared_set", "date": False,
        "help": "Shared negative keyword lists in the account.",
    },
    "ads": {
        "fields": [
            "campaign.name", "ad_group.name", "ad_group_ad.ad.id",
            "ad_group_ad.ad.type", "ad_group_ad.status",
            "ad_group_ad.ad_strength", "ad_group_ad.policy_summary.approval_status",
            "ad_group_ad.ad.final_urls",
            "ad_group_ad.ad.responsive_search_ad.headlines",
            "ad_group_ad.ad.responsive_search_ad.descriptions",
            "metrics.impressions", "metrics.clicks", "metrics.ctr",
            "metrics.cost_micros", "metrics.conversions",
        ],
        "from": "ad_group_ad", "date": True, "order": "metrics.impressions DESC",
        "help": "Ads with ad strength, approval status and headlines.",
    },
    "budgets": {
        "fields": [
            "campaign_budget.id", "campaign_budget.name", "campaign_budget.resource_name",
            "campaign_budget.amount_micros", "campaign_budget.delivery_method",
            "campaign_budget.explicitly_shared", "campaign_budget.status",
            "campaign_budget.has_recommended_budget",
            "campaign_budget.recommended_budget_amount_micros",
        ],
        "from": "campaign_budget", "date": False,
        "help": "Budgets with the resource name a budget change needs.",
    },
    "landing_pages": {
        "fields": [
            "campaign.name", "landing_page_view.unexpanded_final_url",
            "metrics.impressions", "metrics.clicks", "metrics.ctr",
            "metrics.cost_micros", "metrics.conversions",
        ],
        "from": "landing_page_view", "date": True, "order": "metrics.clicks DESC",
        "help": "Landing pages behind the ads, with their performance.",
    },
    "devices": {
        "fields": [
            "campaign.name", "segments.device", "metrics.impressions", "metrics.clicks",
            "metrics.ctr", "metrics.cost_micros", "metrics.conversions",
            "metrics.cost_per_conversion",
        ],
        "from": "campaign", "date": True, "order": "metrics.cost_micros DESC",
        "help": "Performance split by device.",
    },
    "locations": {
        "fields": [
            "campaign.name", "campaign_criterion.location.geo_target_constant",
            "campaign_criterion.negative", "campaign_criterion.bid_modifier",
            "campaign_criterion.status",
        ],
        "from": "campaign_criterion", "date": False,
        "where": "campaign_criterion.type = 'LOCATION'",
        "help": "Targeted and excluded locations per campaign.",
    },
    "hours": {
        "fields": [
            "campaign.name", "segments.day_of_week", "segments.hour",
            "metrics.impressions", "metrics.clicks", "metrics.cost_micros",
            "metrics.conversions",
        ],
        "from": "campaign", "date": True, "order": "metrics.cost_micros DESC",
        "help": "Performance by weekday and hour.",
    },
    "conversion_actions": {
        "fields": [
            "conversion_action.id", "conversion_action.name", "conversion_action.type",
            "conversion_action.category", "conversion_action.status",
            "conversion_action.primary_for_goal",
            "conversion_action.attribution_model_settings.attribution_model",
        ],
        "from": "conversion_action", "date": False,
        "help": "Which conversions are counted. Read this before judging any number.",
    },
    "recommendations": {
        "fields": [
            "recommendation.type", "recommendation.resource_name", "campaign.name",
            "recommendation.impact.base_metrics.clicks",
            "recommendation.impact.potential_metrics.clicks",
            "recommendation.impact.base_metrics.cost_micros",
            "recommendation.impact.potential_metrics.cost_micros",
        ],
        "from": "recommendation", "date": False,
        "help": "What Google itself suggests for this account.",
    },
    "change_history": {
        "fields": [
            "change_event.change_date_time", "change_event.change_resource_type",
            "change_event.changed_fields", "change_event.client_type",
            "change_event.user_email", "change_event.resource_change_operation",
            "campaign.name",
        ],
        "from": "change_event", "date": True, "order": "change_event.change_date_time DESC",
        "help": "Who changed what in the account, up to 30 days back.",
    },
    "account": {
        "fields": [
            "customer.id", "customer.descriptive_name", "customer.currency_code",
            "customer.time_zone", "customer.manager", "customer.test_account",
            "customer.auto_tagging_enabled", "customer.optimization_score",
        ],
        "from": "customer", "date": False,
        "help": "Account settings: currency, time zone, whether it is a manager.",
    },
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def gaql_string(value: str) -> str:
    """Quotes a literal for a GAQL WHERE clause."""
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def snake(name: str) -> str:
    """costMicros -> cost_micros. Digits stay attached to what precedes them."""
    out = []
    for index, char in enumerate(name):
        if char.isupper() and index and not name[index - 1].isupper():
            out.append("_")
        out.append(char.lower())
    return "".join(out)


def flatten(row: dict, prefix: str = "") -> dict:
    """Turns the API's nested answer into the field names GAQL uses.

    The query asks for metrics.cost_micros; the REST answer carries
    {"metrics": {"costMicros": ...}}. Flattening and un-camel-casing gives
    back exactly the names that were asked for, so an answer can be read
    against the query that produced it without translating in between.
    Lists stay lists.
    """
    flat: dict = {}
    for key, value in row.items():
        name = f"{prefix}{snake(key)}"
        if isinstance(value, dict):
            flat.update(flatten(value, f"{name}."))
        else:
            flat[name] = value
    return flat


def add_currency(row: dict) -> dict:
    """Adds a readable amount next to every micros field.

    Google counts money in millionths. Six zeros are easy to lose, and
    losing them is the difference between a 5 euro budget and a 5 million
    euro one, so the readable value travels alongside the raw one.
    """
    extra = {}
    for key, value in row.items():
        if key.endswith("_micros"):
            try:
                extra[key[: -len("_micros")] + "_amount"] = round(int(value) / 1_000_000, 2)
            except (TypeError, ValueError):
                pass
    row.update(extra)
    return row


def shape(rows: list[dict], limit: int) -> dict:
    """Flattens, converts and truncates a result set for an agent to read."""
    prepared = [add_currency(flatten(r)) for r in rows[:limit]]
    answer: dict = {"row_count": len(prepared), "rows": prepared}
    if len(rows) > limit:
        answer["truncated"] = True
        answer["note"] = (f"{len(rows)} rows matched, {limit} shown. Raise `limit` or "
                          "narrow the query.")
    return answer


def date_clause(date_range: str, start: str, end: str) -> str:
    """Builds the segments.date condition from either a range or two dates."""
    if start and end:
        return f"segments.date BETWEEN {gaql_string(start)} AND {gaql_string(end)}"
    return f"segments.date DURING {date_range or 'LAST_30_DAYS'}"


# --------------------------------------------------------------------------
# Tool catalogue
#
# Order is fixed and deterministic: clients cache this list, and a stable
# order keeps their prompt caches warm.
# --------------------------------------------------------------------------

CUSTOMER_ID = {
    "type": "string",
    "description": "Ten-digit Google Ads customer ID, hyphens allowed (123-456-7890).",
}
DRY_RUN = {
    "type": "boolean",
    "default": True,
    "description": ("true validates the change against every Google rule and changes "
                    "NOTHING. Set false only after the account owner approved the plan."),
}
GOOGLE_DRY_RUN = {
    "type": "boolean",
    "default": True,
    "description": ("true shows what would change — built from the current state, because "
                    "Search Console and Analytics cannot validate without writing — and sends "
                    "NOTHING. Set false only after the owner approved the plan."),
}
REASON = {
    "type": "string",
    "description": "Why this change is being made. Goes into the change log verbatim.",
}


def tool_catalogue() -> list[dict]:
    return [
        {
            "name": "google_ads_accounts",
            "description": ("Lists the Google Ads accounts this connection may use, with "
                            "name, currency, time zone and whether the account is a "
                            "manager. Start here: everything else needs a customer ID."),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "google_ads_report",
            "description": ("Runs a prepared report. Covers campaigns, ad_groups, keywords, "
                            "search_terms, negative keywords, ads, budgets, landing_pages, "
                            "devices, locations, hours, conversion_actions, recommendations, "
                            "change_history and account settings. Use this before writing a "
                            "GAQL query by hand."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "customer_id": CUSTOMER_ID,
                    "report": {"type": "string", "enum": sorted(REPORTS),
                               "description": "Which report to run."},
                    "date_range": {"type": "string", "enum": list(DATE_RANGES),
                                   "default": "LAST_30_DAYS",
                                   "description": "Ignored by reports without metrics."},
                    "start_date": {"type": "string",
                                   "description": "YYYY-MM-DD. Overrides date_range with end_date."},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD."},
                    "filter": {"type": "string",
                               "description": ("Extra GAQL WHERE condition, ANDed to the "
                                               "report's own, e.g. \"campaign.status = 'ENABLED'\".")},
                    "limit": {"type": "integer", "default": DEFAULT_ROW_LIMIT,
                              "description": f"Rows to return. Default {DEFAULT_ROW_LIMIT}."},
                    "login_customer_id": {"type": "string",
                                          "description": "Manager account ID, if not the configured one."},
                },
                "required": ["customer_id", "report"],
                "additionalProperties": False,
            },
        },
        {
            "name": "google_ads_query",
            "description": ("Runs any GAQL query. Use it for what the prepared reports do "
                            "not cover. Read-only: GAQL cannot change anything."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "customer_id": CUSTOMER_ID,
                    "query": {"type": "string",
                              "description": "Full GAQL, e.g. SELECT campaign.name FROM campaign."},
                    "limit": {"type": "integer", "default": DEFAULT_ROW_LIMIT},
                    "login_customer_id": {"type": "string"},
                },
                "required": ["customer_id", "query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "google_ads_fields",
            "description": ("Looks up which fields exist, what they may be combined with, "
                            "and whether they are selectable or filterable. Use it when a "
                            "GAQL query is rejected for an unknown field."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name_contains": {"type": "string",
                                      "description": "Substring of the field name, e.g. 'quality'."},
                    "resource": {"type": "string",
                                 "description": "Restrict to one resource, e.g. 'keyword_view'."},
                    "limit": {"type": "integer", "default": 100},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "google_ads_keyword_ideas",
            "description": ("Keyword Planner. Returns keyword ideas with monthly search "
                            "volume, competition and bid estimates. Seed it with keywords, "
                            "a page URL, a whole site, or keywords plus a URL. Needs a "
                            "developer token with BASIC access; EXPLORER has the planning "
                            "tools switched off."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "customer_id": CUSTOMER_ID,
                    "keywords": {"type": "array", "items": {"type": "string"},
                                 "description": "Seed keywords, up to 20."},
                    "url": {"type": "string", "description": "Seed page URL."},
                    "site": {"type": "string",
                             "description": "Seed whole site (domain), ideas from all its pages."},
                    "language_id": {"type": "string", "default": "1001",
                                    "description": "Language constant ID. 1001 German, 1000 English."},
                    "geo_target_ids": {"type": "array", "items": {"type": "string"},
                                       "default": ["2040"],
                                       "description": ("Geo target constant IDs. 2040 Austria, "
                                                       "2276 Germany, 2756 Switzerland, 2036 Australia.")},
                    "network": {"type": "string",
                                "enum": ["GOOGLE_SEARCH", "GOOGLE_SEARCH_AND_PARTNERS"],
                                "default": "GOOGLE_SEARCH"},
                    "include_adult": {"type": "boolean", "default": False},
                    "limit": {"type": "integer", "default": DEFAULT_ROW_LIMIT},
                    "login_customer_id": {"type": "string"},
                },
                "required": ["customer_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "google_ads_keyword_metrics",
            "description": ("Historical search volume, competition and bid range for "
                            "keywords you already have. Unlike keyword_ideas it invents "
                            "nothing, it only measures the list you pass in. Needs BASIC "
                            "access, same as keyword_ideas."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "customer_id": CUSTOMER_ID,
                    "keywords": {"type": "array", "items": {"type": "string"},
                                 "description": "The keywords to measure, up to 10000."},
                    "language_id": {"type": "string", "default": "1001"},
                    "geo_target_ids": {"type": "array", "items": {"type": "string"},
                                       "default": ["2040"]},
                    "network": {"type": "string",
                                "enum": ["GOOGLE_SEARCH", "GOOGLE_SEARCH_AND_PARTNERS"],
                                "default": "GOOGLE_SEARCH"},
                    "limit": {"type": "integer", "default": DEFAULT_ROW_LIMIT},
                    "login_customer_id": {"type": "string"},
                },
                "required": ["customer_id", "keywords"],
                "additionalProperties": False,
            },
        },
        {
            "name": "google_ads_add_keywords",
            "description": ("Adds positive keywords to an ad group. Dry run by default. "
                            "Needs the ad group ID from google_ads_report ad_groups."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "customer_id": CUSTOMER_ID,
                    "ad_group_id": {"type": "string", "description": "Numeric ad group ID."},
                    "keywords": {
                        "type": "array",
                        "description": "The keywords to add.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "match_type": {"type": "string", "enum": list(MATCH_TYPES),
                                               "default": "PHRASE"},
                                "cpc_bid_micros": {"type": "integer",
                                                   "description": "Optional bid in micros (1 EUR = 1000000)."},
                                "final_url": {"type": "string",
                                              "description": "Optional landing page for this keyword."},
                            },
                            "required": ["text"],
                            "additionalProperties": False,
                        },
                    },
                    "status": {"type": "string", "enum": ["ENABLED", "PAUSED"],
                               "default": "ENABLED"},
                    "dry_run": DRY_RUN,
                    "reason": REASON,
                    "login_customer_id": {"type": "string"},
                },
                "required": ["customer_id", "ad_group_id", "keywords"],
                "additionalProperties": False,
            },
        },
        {
            "name": "google_ads_add_negative_keywords",
            "description": ("Excludes keywords, on campaign level, ad group level or in a "
                            "shared negative list. Dry run by default. The usual source is "
                            "the search_terms report."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "customer_id": CUSTOMER_ID,
                    "level": {"type": "string", "enum": ["campaign", "ad_group", "shared_set"],
                              "description": "Where the exclusion applies."},
                    "campaign_id": {"type": "string", "description": "Required for level=campaign."},
                    "ad_group_id": {"type": "string", "description": "Required for level=ad_group."},
                    "shared_set_id": {"type": "string",
                                      "description": ("Required for level=shared_set. From the "
                                                      "shared_negative_lists report.")},
                    "keywords": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "match_type": {"type": "string", "enum": list(MATCH_TYPES),
                                               "default": "PHRASE"},
                            },
                            "required": ["text"],
                            "additionalProperties": False,
                        },
                    },
                    "dry_run": DRY_RUN,
                    "reason": REASON,
                    "login_customer_id": {"type": "string"},
                },
                "required": ["customer_id", "level", "keywords"],
                "additionalProperties": False,
            },
        },
        {
            "name": "google_ads_set_status",
            "description": ("Enables, pauses or removes campaigns, ad groups, keywords or "
                            "ads. Dry run by default. REMOVED cannot be undone."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "customer_id": CUSTOMER_ID,
                    "entity": {"type": "string",
                               "enum": ["campaign", "ad_group", "ad_group_criterion", "ad_group_ad"]},
                    "resource_names": {
                        "type": "array", "items": {"type": "string"},
                        "description": ("Full resource names, e.g. "
                                        "customers/123/campaigns/456. Reports return them."),
                    },
                    "status": {"type": "string", "enum": ["ENABLED", "PAUSED", "REMOVED"]},
                    "dry_run": DRY_RUN,
                    "reason": REASON,
                    "login_customer_id": {"type": "string"},
                },
                "required": ["customer_id", "entity", "resource_names", "status"],
                "additionalProperties": False,
            },
        },
        {
            "name": "google_ads_set_budget",
            "description": ("Changes the daily budget of a campaign budget. Dry run by "
                            "default, and the guardrails cap both the amount and how far "
                            "it may move in one step. Resource name from the budgets report."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "customer_id": CUSTOMER_ID,
                    "budget_resource_name": {
                        "type": "string",
                        "description": "e.g. customers/1234567890/campaignBudgets/987654",
                    },
                    "amount": {"type": "number",
                               "description": "New daily budget in account currency, e.g. 25.50."},
                    "amount_micros": {"type": "integer",
                                      "description": "Alternative to amount, in micros."},
                    "dry_run": DRY_RUN,
                    "reason": REASON,
                    "login_customer_id": {"type": "string"},
                },
                "required": ["customer_id", "budget_resource_name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "google_ads_set_bid",
            "description": ("Sets the CPC bid on keywords or ad groups. Only has an effect "
                            "where bidding is manual. Dry run by default."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "customer_id": CUSTOMER_ID,
                    "entity": {"type": "string", "enum": ["ad_group_criterion", "ad_group"]},
                    "bids": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "resource_name": {"type": "string"},
                                "cpc_bid_micros": {"type": "integer"},
                            },
                            "required": ["resource_name", "cpc_bid_micros"],
                            "additionalProperties": False,
                        },
                    },
                    "dry_run": DRY_RUN,
                    "reason": REASON,
                    "login_customer_id": {"type": "string"},
                },
                "required": ["customer_id", "entity", "bids"],
                "additionalProperties": False,
            },
        },
        {
            "name": "google_ads_mutate",
            "description": ("The raw mutate endpoint, for everything the specific write "
                            "tools do not cover: creating campaigns, ad groups, responsive "
                            "search ads, bid modifiers, shared sets, labels. Takes the "
                            "API's own mutateOperations array. Dry run by default."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "customer_id": CUSTOMER_ID,
                    "operations": {
                        "type": "array",
                        "description": ("Google Ads MutateOperation objects, e.g. "
                                        "[{\"campaignOperation\": {\"create\": {...}}}]. "
                                        "Temporary IDs (-1, -2) chain operations in one call."),
                        "items": {"type": "object"},
                    },
                    "partial_failure": {
                        "type": "boolean", "default": False,
                        "description": "true applies the operations that pass and reports the rest.",
                    },
                    "response_content_type": {
                        "type": "string",
                        "enum": ["RESOURCE_NAME_ONLY", "MUTABLE_RESOURCE"],
                        "default": "RESOURCE_NAME_ONLY",
                    },
                    "dry_run": DRY_RUN,
                    "reason": REASON,
                    "login_customer_id": {"type": "string"},
                },
                "required": ["customer_id", "operations"],
                "additionalProperties": False,
            },
        },
        {
            "name": "search_console_sites",
            "description": ("Lists the Google Search Console properties this login can read, "
                            "with the permission level. Start here for anything organic."),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "search_console_performance",
            "description": ("Organic Google search performance from Search Console: clicks, "
                            "impressions, CTR and average position, grouped by query, page, "
                            "country, device, date or search appearance. Read-only."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "site_url": SITE_URL,
                    "dimensions": {"type": "array", "items": {"type": "string", "enum": list(GSC_DIMENSIONS)},
                                   "default": ["query"],
                                   "description": "Group by these, in this order. Default: query."},
                    "date_range": {"type": "string", "enum": list(GSC_DATE_RANGES), "default": "LAST_28_DAYS",
                                   "description": ("Ends the day before yesterday — the latest two "
                                                   "days are still incomplete in Search Console.")},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, together with end_date."},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, together with start_date."},
                    "search_type": {"type": "string", "enum": list(GSC_SEARCH_TYPES), "default": "web"},
                    "query_contains": {"type": "string", "description": "Only queries containing this text."},
                    "page_contains": {"type": "string", "description": "Only pages whose URL contains this."},
                    "country": {"type": "string", "description": "ISO 3166-1 alpha-3, e.g. aut, deu."},
                    "device": {"type": "string", "enum": ["DESKTOP", "MOBILE", "TABLET"]},
                    "filters": {"type": "array", "description": "Further filters, all ANDed.",
                                "items": {"type": "object", "properties": {
                                    "dimension": {"type": "string", "enum": list(GSC_DIMENSIONS)},
                                    "operator": {"type": "string", "enum": list(GSC_OPERATORS)},
                                    "expression": {"type": "string"}},
                                    "required": ["dimension", "operator", "expression"],
                                    "additionalProperties": False}},
                    "fresh": {"type": "boolean", "default": False,
                              "description": "Include the latest, still incomplete data."},
                    "limit": {"type": "integer", "default": DEFAULT_ROW_LIMIT,
                              "description": f"Rows to return, up to {GSC_MAX_ROWS}."},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "search_console_inspect_url",
            "description": ("Asks Search Console what Google knows about one URL: indexed or "
                            "not and why, last crawl, canonical, robots.txt, rich results. "
                            "Read-only — it does not request a new crawl."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "site_url": SITE_URL,
                    "url": {"type": "string", "description": "The full URL to inspect."},
                    "language": {"type": "string", "default": "de-AT",
                                 "description": "Language of Google's explanations."},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
        {
            "name": "search_console_sitemaps",
            "description": ("Lists the sitemaps submitted for a property, when Google last "
                            "read them and how many errors and warnings it found."),
            "inputSchema": {
                "type": "object",
                "properties": {"site_url": SITE_URL},
                "additionalProperties": False,
            },
        },
        {
            "name": "analytics_properties",
            "description": ("Lists the Google Analytics 4 properties this login can read, "
                            "with account. Start here for anything about visitors on the site."),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "analytics_report",
            "description": ("Runs a Google Analytics 4 report: any dimensions and metrics, e.g. "
                            "pagePath with screenPageViews, sessionSource with sessions, date with "
                            "activeUsers. Read-only. Counts only visitors who consented to statistics."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "property_id": PROPERTY_ID,
                    "dimensions": {"type": "array", "items": {"type": "string"}, "default": ["date"],
                                   "description": "GA4 API names, e.g. pagePath, sessionDefaultChannelGroup."},
                    "metrics": {"type": "array", "items": {"type": "string"},
                                "default": ["activeUsers", "sessions"],
                                "description": "GA4 API names, e.g. screenPageViews, engagementRate, keyEvents."},
                    "date_range": {"type": "string", "enum": list(GA_DATE_RANGES), "default": "LAST_28_DAYS",
                                   "description": "Ends yesterday — today is still incomplete."},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, together with end_date."},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, together with start_date."},
                    "filters": {"type": "array", "description": "Dimension filters, all ANDed.",
                                "items": {"type": "object", "properties": {
                                    "dimension": {"type": "string"},
                                    "match": {"type": "string", "enum": list(GA_MATCH_TYPES)},
                                    "value": {"type": "string"}},
                                    "required": ["dimension", "value"],
                                    "additionalProperties": False}},
                    "order_by": {"type": "string",
                                 "description": "A metric (descending) or dimension (ascending). Default: first metric."},
                    "limit": {"type": "integer", "default": DEFAULT_ROW_LIMIT},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "analytics_metadata",
            "description": ("Lists the dimensions and metrics a GA4 property offers, including "
                            "its own custom ones. Use it when a report is refused for an unknown field."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "property_id": PROPERTY_ID,
                    "contains": {"type": "string", "description": "Only fields whose name contains this."},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "analytics_settings",
            "description": ("Shows how a GA4 property is set up: time zone, currency, how long "
                            "Google keeps the data, which events count as key events and which "
                            "custom dimensions exist. Read-only. Use it before changing anything."),
            "inputSchema": {
                "type": "object",
                "properties": {"property_id": PROPERTY_ID},
                "additionalProperties": False,
            },
        },
        {
            "name": "search_console_submit_sitemap",
            "description": ("Submits (or resubmits) a sitemap to Search Console, so Google reads "
                            "it again. Starts as a dry run that shows the current state; nothing "
                            "is sent before dry_run=false."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "site_url": SITE_URL,
                    "sitemap_url": {"type": "string",
                                    "description": "Full URL of the sitemap, inside the property."},
                    "dry_run": GOOGLE_DRY_RUN,
                    "reason": REASON,
                },
                "required": ["sitemap_url"],
                "additionalProperties": False,
            },
        },
        {
            "name": "search_console_delete_sitemap",
            "description": ("Removes a submitted sitemap from Search Console, e.g. an outdated "
                            "one. The pages stay in Google's index. Starts as a dry run."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "site_url": SITE_URL,
                    "sitemap_url": {"type": "string",
                                    "description": "Exactly as search_console_sitemaps lists it."},
                    "dry_run": GOOGLE_DRY_RUN,
                    "reason": REASON,
                },
                "required": ["sitemap_url"],
                "additionalProperties": False,
            },
        },
        {
            "name": "analytics_key_event",
            "description": ("Marks a GA4 event as a key event (create) or takes the mark away "
                            "(delete), e.g. generate_lead. Collected data stays. Starts as a dry run."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "property_id": PROPERTY_ID,
                    "action": {"type": "string", "enum": ["create", "delete"]},
                    "event_name": {"type": "string",
                                   "description": "The event name exactly as the site sends it."},
                    "counting_method": {"type": "string", "enum": ["ONCE_PER_EVENT", "ONCE_PER_SESSION"],
                                        "default": "ONCE_PER_EVENT",
                                        "description": "create only: count every event or one per session."},
                    "dry_run": GOOGLE_DRY_RUN,
                    "reason": REASON,
                },
                "required": ["action", "event_name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "analytics_custom_dimension",
            "description": ("Registers an event parameter as a GA4 custom dimension (create) so "
                            "reports can use it, or archives one (archive — Google offers no way "
                            "back). Refuses parameters that look like personal data. Starts as a dry run."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "property_id": PROPERTY_ID,
                    "action": {"type": "string", "enum": ["create", "archive"]},
                    "parameter_name": {"type": "string",
                                       "description": "The event parameter, e.g. form_location."},
                    "display_name": {"type": "string",
                                     "description": ("create only: name in reports. Letters, digits, "
                                                     "spaces, underscores; starts with a letter.")},
                    "description": {"type": "string", "description": "create only, optional, up to 150 characters."},
                    "scope": {"type": "string", "enum": list(GA_DIMENSION_SCOPES), "default": "EVENT"},
                    "dry_run": GOOGLE_DRY_RUN,
                    "reason": REASON,
                },
                "required": ["action", "parameter_name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "google_ads_change_log",
            "description": ("Shows what this server wrote, newest first: time, account or "
                            "property, whether it was a dry run, the reason given and the result. "
                            "Covers Google Ads, Search Console and Analytics. This is the local "
                            "log, separate from Google's change history."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20},
                    "customer_id": {"type": "string",
                                    "description": ("Filter: an Ads account, or part of a Search "
                                                    "Console / Analytics target such as analytics "
                                                    "or a property ID.")},
                    "include_operations": {
                        "type": "boolean", "default": False,
                        "description": "true includes the full operation payloads.",
                    },
                },
                "additionalProperties": False,
            },
        },
    ]


# --------------------------------------------------------------------------
# Tool implementations
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Search Console (reading)
#
# The organic side next to the paid one: which searches showed the site, at
# what position, with how many clicks — and whether Google has indexed a
# page at all. The two sitemap write tools further down are the only ones
# that change anything in Search Console.
# --------------------------------------------------------------------------

GSC_DATE_RANGES = {
    "LAST_7_DAYS": 7, "LAST_28_DAYS": 28, "LAST_3_MONTHS": 91,
    "LAST_6_MONTHS": 182, "LAST_12_MONTHS": 365, "LAST_16_MONTHS": 486,
}
GSC_DIMENSIONS = ("query", "page", "country", "device", "date", "searchAppearance")
GSC_SEARCH_TYPES = ("web", "image", "video", "news", "discover", "googleNews")
GSC_OPERATORS = ("equals", "notEquals", "contains", "notContains", "includingRegex", "excludingRegex")
GSC_MAX_ROWS = 25000

# Search Console publishes a day two to three days late. A window that ends
# today reads as a collapse in the last days that is really just missing
# data — so the default window ends the day before yesterday, as the
# Search Console interface does.
GSC_DELAY_DAYS = 2

SITE_URL = {"type": "string",
            "description": ("Property exactly as Search Console names it: sc-domain:example.at "
                            "for a domain property, https://example.at/ for a URL prefix. "
                            "May be omitted when the login can read exactly one property.")}


def gsc_dates(args: dict, today: datetime.date | None = None) -> tuple[str, str]:
    """(start, end) as YYYY-MM-DD. Explicit dates win over date_range."""
    if args.get("start_date") or args.get("end_date"):
        if not (args.get("start_date") and args.get("end_date")):
            raise GoogleAdsError("start_date and end_date go together — pass both or neither.")
        return args["start_date"], args["end_date"]
    name = args.get("date_range") or "LAST_28_DAYS"
    if name not in GSC_DATE_RANGES:
        raise GoogleAdsError(f"Unknown date_range '{name}'. Known: {', '.join(GSC_DATE_RANGES)}.")
    end = (today or datetime.date.today()) - datetime.timedelta(days=GSC_DELAY_DAYS)
    start = end - datetime.timedelta(days=GSC_DATE_RANGES[name] - 1)
    return start.isoformat(), end.isoformat()


def gsc_query_body(args: dict, today: datetime.date | None = None) -> dict:
    """The searchAnalytics.query body for the performance tool's arguments."""
    dimensions = list(args.get("dimensions") or ["query"])
    unknown = [d for d in dimensions if d not in GSC_DIMENSIONS]
    if unknown:
        raise GoogleAdsError(f"Unknown dimension(s) {', '.join(unknown)}. Known: {', '.join(GSC_DIMENSIONS)}.")
    search_type = args.get("search_type") or "web"
    if search_type not in GSC_SEARCH_TYPES:
        raise GoogleAdsError(f"Unknown search_type '{search_type}'. Known: {', '.join(GSC_SEARCH_TYPES)}.")

    start, end = gsc_dates(args, today)
    limit = max(1, min(int(args.get("limit") or DEFAULT_ROW_LIMIT), GSC_MAX_ROWS))
    body: dict = {"startDate": start, "endDate": end, "dimensions": dimensions,
                  "type": search_type, "rowLimit": limit}
    if args.get("fresh"):
        body["dataState"] = "all"

    filters = []
    for key, dimension in (("query_contains", "query"), ("page_contains", "page")):
        if args.get(key):
            filters.append({"dimension": dimension, "operator": "contains", "expression": args[key]})
    if args.get("country"):
        filters.append({"dimension": "country", "operator": "equals",
                        "expression": str(args["country"]).lower()})
    if args.get("device"):
        filters.append({"dimension": "device", "operator": "equals",
                        "expression": str(args["device"]).upper()})
    for extra in args.get("filters") or []:
        if extra.get("dimension") not in GSC_DIMENSIONS or extra.get("operator") not in GSC_OPERATORS:
            raise GoogleAdsError(f"Filter {extra} needs a known dimension and one of: {', '.join(GSC_OPERATORS)}.")
        filters.append({"dimension": extra["dimension"], "operator": extra["operator"],
                        "expression": str(extra.get("expression", ""))})
    if filters:
        body["dimensionFilterGroups"] = [{"groupType": "and", "filters": filters}]
    return body


def gsc_shape(dimensions: list[str], response: dict) -> dict:
    rows = []
    for row in response.get("rows") or []:
        entry = dict(zip(dimensions, row.get("keys") or []))
        entry.update({
            "clicks": int(row.get("clicks", 0)),
            "impressions": int(row.get("impressions", 0)),
            "ctr_percent": round(float(row.get("ctr", 0)) * 100, 2),
            "position": round(float(row.get("position", 0)), 1),
        })
        rows.append(entry)
    return {
        "row_count": len(rows),
        "rows": rows,
        "sum_of_rows": {"clicks": sum(r["clicks"] for r in rows),
                        "impressions": sum(r["impressions"] for r in rows)},
        "note": ("position is the AVERAGE position (1 = top of page one; 11 and worse is page "
                 "two or later). Google leaves out rare queries for privacy, so the sum of the "
                 "rows is lower than the totals in the Search Console interface."),
    }


def _site(client: Client, args: dict) -> str:
    site = (args.get("site_url") or "").strip()
    if site:
        return site
    readable = [e.get("siteUrl", "") for e in client.search_console_sites()
                if e.get("permissionLevel") != "siteUnverifiedUser"]
    if len(readable) == 1:
        return readable[0]
    if not readable:
        raise GoogleAdsError("This login can read no Search Console property. Check that the Google "
                             "account behind it has access in Search Console.")
    raise GoogleAdsError("Several properties are readable — pass site_url. Readable: "
                         + ", ".join(readable) + ".")


def tool_gsc_sites(args: dict) -> dict:
    sites = [{"site_url": e.get("siteUrl", ""), "permission": e.get("permissionLevel", "")}
             for e in _client(args).search_console_sites()]
    return {"site_count": len(sites), "sites": sites,
            "note": ("siteUnverifiedUser means: listed, but no data readable. "
                     "sc-domain: is a domain property and covers every protocol and subdomain.")}


def tool_gsc_performance(args: dict) -> dict:
    client = _client(args)
    site = _site(client, args)
    body = gsc_query_body(args)
    answer = gsc_shape(body["dimensions"], client.search_console_query(site, body))
    answer.update({"site_url": site, "start_date": body["startDate"], "end_date": body["endDate"],
                   "search_type": body["type"]})
    return answer


def tool_gsc_inspect_url(args: dict) -> dict:
    client = _client(args)
    site = _site(client, args)
    raw = client.search_console_inspect(site, args["url"], args.get("language") or "de-AT")
    result = raw.get("inspectionResult") or {}
    index = result.get("indexStatusResult") or {}
    rich = result.get("richResultsResult") or {}
    return {
        "url": args["url"],
        "site_url": site,
        "verdict": index.get("verdict", ""),
        "coverage": index.get("coverageState", ""),
        "indexing_allowed": index.get("indexingState", ""),
        "robots_txt": index.get("robotsTxtState", ""),
        "page_fetch": index.get("pageFetchState", ""),
        "last_crawl": index.get("lastCrawlTime", ""),
        "crawled_as": index.get("crawledAs", ""),
        "google_canonical": index.get("googleCanonical", ""),
        "user_canonical": index.get("userCanonical", ""),
        "sitemaps": index.get("sitemap") or [],
        "referring_urls": (index.get("referringUrls") or [])[:5],
        "rich_results": {"verdict": rich.get("verdict", ""),
                         "types": [d.get("richResultType", "") for d in rich.get("detectedItems") or []]},
        "report_link": result.get("inspectionResultLink", ""),
        "note": ("Reads what Google has stored — it does not ask Google to crawl again. "
                 "Quota: about 2,000 inspections per property and day."),
    }


def tool_gsc_sitemaps(args: dict) -> dict:
    client = _client(args)
    site = _site(client, args)
    maps = []
    for entry in client.search_console_sitemaps(site):
        maps.append({
            "path": entry.get("path", ""),
            "last_submitted": entry.get("lastSubmitted", ""),
            "last_downloaded": entry.get("lastDownloaded", ""),
            "pending": bool(entry.get("isPending")),
            "warnings": int(entry.get("warnings", 0) or 0),
            "errors": int(entry.get("errors", 0) or 0),
            "contents": [{"type": c.get("type", ""), "submitted": int(c.get("submitted", 0) or 0)}
                         for c in entry.get("contents") or []],
        })
    return {"site_url": site, "sitemap_count": len(maps), "sitemaps": maps}


# --------------------------------------------------------------------------
# Google Analytics 4 (reading)
#
# What the visitors did once they were on the site. Every number here comes
# only from visitors who allowed statistics in the cookie banner — with
# consent mode "basic" nobody else is counted or modelled. The tools say so
# in every answer, because a low number otherwise reads as low traffic.
# --------------------------------------------------------------------------

GA_DATE_RANGES = {
    "TODAY": ("today", "today"), "YESTERDAY": ("yesterday", "yesterday"),
    "LAST_7_DAYS": ("7daysAgo", "yesterday"), "LAST_28_DAYS": ("28daysAgo", "yesterday"),
    "LAST_90_DAYS": ("90daysAgo", "yesterday"), "LAST_12_MONTHS": ("365daysAgo", "yesterday"),
}
GA_MATCH_TYPES = ("EXACT", "BEGINS_WITH", "ENDS_WITH", "CONTAINS", "FULL_REGEXP", "PARTIAL_REGEXP")
GA_MAX_ROWS = 100000

PROPERTY_ID = {"type": "string",
               "description": ("Numeric GA4 property ID, e.g. 123456789. May be omitted when "
                               "the login can read exactly one property.")}

GA_CONSENT_NOTE = ("Counts only visitors who allowed statistics in the cookie banner; with "
                   "consent mode basic nobody else is counted or modelled. Small numbers can "
                   "also be withheld by Google's data thresholds.")


def _without(value: str, prefix: str) -> str:
    """str.removeprefix for Pythons before 3.9 — the desktop app runs whatever is installed."""
    return value[len(prefix):] if value.startswith(prefix) else value


def ga_report_body(args: dict) -> dict:
    """The runReport body for the report tool's arguments."""
    dimensions = list(args.get("dimensions") or ["date"])
    metrics = list(args.get("metrics") or ["activeUsers", "sessions"])
    if args.get("start_date") or args.get("end_date"):
        if not (args.get("start_date") and args.get("end_date")):
            raise GoogleAdsError("start_date and end_date go together — pass both or neither.")
        start, end = args["start_date"], args["end_date"]
    else:
        name = args.get("date_range") or "LAST_28_DAYS"
        if name not in GA_DATE_RANGES:
            raise GoogleAdsError(f"Unknown date_range '{name}'. Known: {', '.join(GA_DATE_RANGES)}.")
        start, end = GA_DATE_RANGES[name]

    limit = max(1, min(int(args.get("limit") or DEFAULT_ROW_LIMIT), GA_MAX_ROWS))
    body: dict = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": d} for d in dimensions],
        "metrics": [{"name": m} for m in metrics],
        "limit": limit,
        "metricAggregations": ["TOTAL"],
    }
    order = args.get("order_by") or ("date" if dimensions == ["date"] else metrics[0])
    if order in dimensions:
        body["orderBys"] = [{"dimension": {"dimensionName": order}, "desc": False}]
    else:
        body["orderBys"] = [{"metric": {"metricName": order}, "desc": True}]

    filters = []
    for extra in args.get("filters") or []:
        match = str(extra.get("match") or "CONTAINS").upper()
        if match not in GA_MATCH_TYPES or not extra.get("dimension"):
            raise GoogleAdsError(f"Filter {extra} needs a dimension and one of: {', '.join(GA_MATCH_TYPES)}.")
        filters.append({"filter": {"fieldName": extra["dimension"], "stringFilter": {
            "matchType": match, "value": str(extra.get("value", "")), "caseSensitive": False}}})
    if len(filters) == 1:
        body["dimensionFilter"] = filters[0]
    elif filters:
        body["dimensionFilter"] = {"andGroup": {"expressions": filters}}
    return body


def ga_shape(response: dict) -> dict:
    dims = [h.get("name", "") for h in response.get("dimensionHeaders") or []]
    mets = [h.get("name", "") for h in response.get("metricHeaders") or []]

    def number(value: str):
        try:
            number_ = float(value)
        except (TypeError, ValueError):
            return value
        return int(number_) if number_.is_integer() else round(number_, 4)

    def row_of(row: dict) -> dict:
        entry = {d: v.get("value", "") for d, v in zip(dims, row.get("dimensionValues") or [])}
        entry.update({m: number(v.get("value")) for m, v in zip(mets, row.get("metricValues") or [])})
        return entry

    rows = [row_of(r) for r in response.get("rows") or []]
    totals = [row_of(r) for r in response.get("totals") or []]
    return {"row_count": len(rows), "total_rows_in_report": response.get("rowCount", len(rows)),
            "rows": rows, "totals": {m: totals[0].get(m) for m in mets} if totals else {},
            "note": GA_CONSENT_NOTE}


def _ga_property(client: Client, args: dict) -> str:
    raw = str(args.get("property_id") or "").strip()
    if raw:
        return _without(raw, "properties/")
    props = [_without(p.get("property", ""), "properties/")
             for a in client.analytics_account_summaries() for p in a.get("propertySummaries") or []]
    if len(props) == 1:
        return props[0]
    if not props:
        raise GoogleAdsError("This login can read no Google Analytics property.")
    raise GoogleAdsError("Several properties are readable — pass property_id. Readable: "
                         + ", ".join(props) + ".")


def tool_ga_properties(args: dict) -> dict:
    out = []
    for account in _client(args).analytics_account_summaries():
        for prop in account.get("propertySummaries") or []:
            out.append({"property_id": _without(prop.get("property", ""), "properties/"),
                        "name": prop.get("displayName", ""),
                        "type": prop.get("propertyType", ""),
                        "account": account.get("displayName", ""),
                        "account_id": _without(account.get("account", ""), "accounts/")})
    return {"property_count": len(out), "properties": out}


def tool_ga_report(args: dict) -> dict:
    client = _client(args)
    prop = _ga_property(client, args)
    body = ga_report_body(args)
    answer = ga_shape(client.analytics_report(prop, body))
    answer.update({"property_id": prop, "date_range": body["dateRanges"][0]})
    return answer


def tool_ga_metadata(args: dict) -> dict:
    client = _client(args)
    prop = _ga_property(client, args)
    meta = client.analytics_metadata(prop)
    needle = str(args.get("contains") or "").lower()

    def pick(items: list[dict]) -> list[dict]:
        out = [{"name": i.get("apiName", ""), "label": i.get("uiName", ""),
                "category": i.get("category", "")} for i in items]
        if needle:
            out = [o for o in out if needle in (o["name"] + " " + o["label"]).lower()]
        return out[:DEFAULT_ROW_LIMIT]

    return {"property_id": prop, "dimensions": pick(meta.get("dimensions") or []),
            "metrics": pick(meta.get("metrics") or [])}


# --------------------------------------------------------------------------
# Search Console and Analytics: writing, with a dry run built here
#
# Neither API knows validateOnly — a call either changes something or is
# refused. The dry run is therefore built on this side: read the current
# state, check the request against it, describe the change. Only
# dry_run=false reaches Client.google_write, which checks the master switch
# and logs the attempt.
#
# WHAT IS DELIBERATELY MISSING. Every Analytics setting that decides how
# much is collected about visitors — data retention, Google signals, data
# sharing, user-provided data, user management — has no tool here. Privacy
# comes before measurement: such a change is the owner's decision, made by
# hand in the Analytics interface, not a line in a conversation.
# analytics_settings shows the retention so it can at least be checked.
# --------------------------------------------------------------------------

GA_DIMENSION_SCOPES = ("EVENT", "ITEM")
GA_NAME_RULE = "letters, digits and underscores, starting with a letter"

GOOGLE_PREVIEW = ("PREVIEW — nothing was sent to Google. Search Console and Analytics cannot "
                  "validate a change without making it, so this preview was built from the "
                  "current state. Present it, get approval, then call again with dry_run=false.")

# Parameter names that point at a person. Google's Analytics terms forbid
# sending personal data at all; a custom dimension would put it into every
# report. Parts match anywhere in the name with the underscores taken out
# (so first_name hits firstname), tokens only between underscores (so tel
# does not hide in "hotel"), exact names only as the whole parameter (so
# page_name passes, name does not). A false alarm costs a manual step in
# the Analytics interface; a miss would put personal data in every report.
PII_PARTS = ("mail", "phone", "telefon", "adress", "address", "strasse", "street", "geburt",
             "birth", "iban", "passw", "vorname", "nachname", "firstname", "lastname",
             "fullname", "username")
PII_TOKENS = {"tel", "ip", "plz", "zip", "handy", "mobile", "mobil"}
PII_EXACT = {"name", "user_name", "customer_name", "contact_name", "kunde", "kundenname",
             "person", "user_id", "userid"}


def pii_reason(parameter_name: str) -> str:
    """Why a parameter name looks like personal data, or '' when it does not."""
    low = parameter_name.lower()
    tokens = set(low.split("_"))
    squashed = low.replace("_", "")
    for part in PII_PARTS:
        if part in squashed:
            return f"it contains '{part}'"
    hit = tokens & PII_TOKENS
    if hit:
        return f"it contains '{sorted(hit)[0]}'"
    if low in PII_EXACT:
        return "it names a person"
    return ""


def ga_name_ok(name: str, limit: int) -> bool:
    return (0 < len(name) <= limit and name[0].isascii() and name[0].isalpha()
            and all(c.isascii() and (c.isalnum() or c == "_") for c in name))


def sitemap_in_property(site_url: str, sitemap_url: str) -> bool:
    """Whether a sitemap URL lies inside the Search Console property."""
    parsed = urllib.parse.urlparse(sitemap_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    if site_url.startswith("sc-domain:"):
        domain = site_url[len("sc-domain:"):].lower().rstrip(".")
        host = parsed.hostname.lower()
        return host == domain or host.endswith("." + domain)
    return sitemap_url.lower().startswith(site_url.lower())


def _google_answer(client: Client, args: dict, target: str, operation: dict, answer: dict,
                   live) -> dict:
    """The one ending for every Search Console and Analytics write tool."""
    reason = args.get("reason", "")
    if args.get("dry_run", True):
        client.log_change(target, [operation], dry_run=True, reason=reason, result="preview")
        answer.update({"dry_run": True, "status": GOOGLE_PREVIEW})
        if not client.guardrails.get("write_enabled"):
            answer["note"] = ("Writing is switched off in the console — dry_run=false would be "
                              "refused until the owner switches it on.")
        return answer
    live(reason)
    answer.update({"dry_run": False, "status": "APPLIED — Google accepted the change."})
    return answer


def _sitemap_entry(client: Client, site: str, sitemap_url: str) -> dict | None:
    for entry in client.search_console_sitemaps(site):
        if entry.get("path", "") == sitemap_url:
            return entry
    return None


def _sitemap_state(entry: dict | None) -> dict | None:
    if entry is None:
        return None
    return {"path": entry.get("path", ""), "last_submitted": entry.get("lastSubmitted", ""),
            "last_downloaded": entry.get("lastDownloaded", ""),
            "errors": int(entry.get("errors", 0) or 0),
            "warnings": int(entry.get("warnings", 0) or 0)}


def _permission(client: Client, site: str) -> str:
    for entry in client.search_console_sites():
        if entry.get("siteUrl") == site:
            return entry.get("permissionLevel", "")
    return ""


def tool_gsc_submit_sitemap(args: dict) -> dict:
    client = _client(args)
    site = _site(client, args)
    url = str(args.get("sitemap_url") or "").strip()
    if not sitemap_in_property(site, url):
        raise GoogleAdsError(f"'{url}' does not lie inside the property {site}. A sitemap is "
                             "submitted to the property its URL belongs to.")
    before = _sitemap_state(_sitemap_entry(client, site, url))
    answer = {"site_url": site, "sitemap_url": url,
              "action": "resubmit" if before else "submit",
              "before": before,
              "after": "Google reads the sitemap again; search_console_sitemaps shows the "
                       "result once it has (usually within hours, sometimes days).",
              "permission": _permission(client, site)}
    if answer["permission"] in ("siteRestrictedUser", "siteUnverifiedUser"):
        answer["warning"] = ("This login has only restricted access to the property — Google "
                             "will most likely refuse the submission.")
    return _google_answer(client, args, f"search_console:{site}", {"submit_sitemap": url}, answer,
                          lambda reason: client.search_console_submit_sitemap(site, url, reason=reason))


def tool_gsc_delete_sitemap(args: dict) -> dict:
    client = _client(args)
    site = _site(client, args)
    url = str(args.get("sitemap_url") or "").strip()
    before = _sitemap_state(_sitemap_entry(client, site, url))
    if before is None:
        raise GoogleAdsError(f"'{url}' is not submitted for {site} — nothing to remove. "
                             "search_console_sitemaps lists the submitted ones.")
    answer = {"site_url": site, "sitemap_url": url, "action": "delete", "before": before,
              "after": None,
              "note_on_index": "Removing a sitemap does not remove its pages from Google."}
    return _google_answer(client, args, f"search_console:{site}", {"delete_sitemap": url}, answer,
                          lambda reason: client.search_console_delete_sitemap(site, url, reason=reason))


def _key_event_state(event: dict) -> dict:
    return {"event_name": event.get("eventName", ""), "counting_method": event.get("countingMethod", ""),
            "custom": bool(event.get("custom")), "deletable": bool(event.get("deletable")),
            "created": event.get("createTime", "")}


def tool_ga_key_event(args: dict) -> dict:
    client = _client(args)
    prop = _ga_property(client, args)
    action = str(args.get("action") or "").lower()
    name = str(args.get("event_name") or "").strip()
    if action not in ("create", "delete"):
        raise GoogleAdsError("action is create or delete.")
    if not ga_name_ok(name, 40):
        raise GoogleAdsError(f"'{name}' is not a GA4 event name — {GA_NAME_RULE}, at most 40.")

    existing = {e.get("eventName", ""): e for e in client.analytics_key_events(prop)}
    current = existing.get(name)
    target = f"analytics:{prop}"

    if action == "create":
        if current:
            raise GoogleAdsError(f"'{name}' is already a key event in property {prop} — nothing to do.")
        method = str(args.get("counting_method") or "ONCE_PER_EVENT").upper()
        if method not in ("ONCE_PER_EVENT", "ONCE_PER_SESSION"):
            raise GoogleAdsError("counting_method is ONCE_PER_EVENT or ONCE_PER_SESSION.")
        answer = {"property_id": prop, "action": "create", "before": None,
                  "after": {"event_name": name, "counting_method": method},
                  "key_events_now": sorted(existing),
                  "note": ("Counts from now on, not backwards. The event itself must already be "
                           "sent by the site — marking it does not create it.")}
        return _google_answer(client, args, target,
                              {"create_key_event": {"eventName": name, "countingMethod": method}}, answer,
                              lambda reason: client.analytics_create_key_event(prop, name, method,
                                                                              reason=reason))

    if not current:
        raise GoogleAdsError(f"'{name}' is not a key event in property {prop}. Key events: "
                             + (", ".join(sorted(existing)) or "none") + ".")
    if not current.get("deletable"):
        raise GoogleAdsError(f"Google marks '{name}' as not deletable — it is a default key event.")
    answer = {"property_id": prop, "action": "delete", "before": _key_event_state(current),
              "after": None,
              "note": "The event keeps being collected; it only stops counting as a key event."}
    resource = current.get("name", "")
    return _google_answer(client, args, target, {"delete_key_event": resource}, answer,
                          lambda reason: client.analytics_delete_key_event(prop, resource, reason=reason))


def _dimension_state(dimension: dict) -> dict:
    return {"parameter_name": dimension.get("parameterName", ""),
            "display_name": dimension.get("displayName", ""),
            "scope": dimension.get("scope", ""), "description": dimension.get("description", "")}


def tool_ga_custom_dimension(args: dict) -> dict:
    client = _client(args)
    prop = _ga_property(client, args)
    action = str(args.get("action") or "").lower()
    parameter = str(args.get("parameter_name") or "").strip()
    scope = str(args.get("scope") or "EVENT").upper()
    if action not in ("create", "archive"):
        raise GoogleAdsError("action is create or archive.")
    if scope not in GA_DIMENSION_SCOPES:
        raise GoogleAdsError(f"scope is {' or '.join(GA_DIMENSION_SCOPES)}. User-scoped dimensions "
                             "attach a trait to a person — set those up by hand in Analytics, "
                             "if at all.")
    if not ga_name_ok(parameter, 40):
        raise GoogleAdsError(f"'{parameter}' is not a parameter name — {GA_NAME_RULE}, at most 40.")

    existing = [d for d in client.analytics_custom_dimensions(prop)
                if d.get("parameterName") == parameter and d.get("scope") == scope]
    target = f"analytics:{prop}"

    if action == "create":
        why = pii_reason(parameter)
        if why:
            raise GoogleAdsError(f"'{parameter}' looks like personal data ({why}). Google's terms "
                                 "forbid personal data in Analytics, and a custom dimension would "
                                 "show it in every report. Not done. If the parameter really holds "
                                 "nothing personal, the owner can register it by hand.")
        if existing:
            raise GoogleAdsError(f"'{parameter}' ({scope}) is already a custom dimension: "
                                 f"{existing[0].get('displayName', '')}.")
        display = str(args.get("display_name") or parameter).strip()
        if not (0 < len(display) <= 82 and display[0].isalpha()
                and all(c.isalnum() or c in " _" for c in display)):
            raise GoogleAdsError(f"display_name '{display}' — letters, digits, spaces and "
                                 "underscores, starting with a letter, at most 82.")
        description = str(args.get("description") or "").strip()
        if len(description) > 150:
            raise GoogleAdsError(f"description has {len(description)} characters, at most 150.")
        dimension = {"parameterName": parameter, "displayName": display, "scope": scope}
        if description:
            dimension["description"] = description
        answer = {"property_id": prop, "action": "create", "before": None,
                  "after": _dimension_state(dimension),
                  "note": ("Reports show the dimension from now on, not for data collected "
                           "before. Standard properties allow 50 event-scoped custom dimensions.")}
        return _google_answer(client, args, target, {"create_custom_dimension": dimension}, answer,
                              lambda reason: client.analytics_create_custom_dimension(
                                  prop, dimension, reason=reason))

    if not existing:
        raise GoogleAdsError(f"'{parameter}' ({scope}) is not a custom dimension in property {prop}. "
                             "analytics_settings lists the existing ones.")
    current = existing[0]
    answer = {"property_id": prop, "action": "archive", "before": _dimension_state(current),
              "after": None,
              "warning": ("Archiving is final: the API offers no way to restore an archived "
                          "dimension, and reports lose it.")}
    resource = current.get("name", "")
    return _google_answer(client, args, target, {"archive_custom_dimension": resource}, answer,
                          lambda reason: client.analytics_archive_custom_dimension(
                              prop, resource, reason=reason))


RETENTION_TEXT = {"TWO_MONTHS": "2 months", "FOURTEEN_MONTHS": "14 months",
                  "TWENTY_SIX_MONTHS": "26 months", "THIRTY_EIGHT_MONTHS": "38 months",
                  "FIFTY_MONTHS": "50 months"}


def tool_ga_settings(args: dict) -> dict:
    client = _client(args)
    prop = _ga_property(client, args)
    info = client.analytics_property(prop)
    retention = client.analytics_data_retention(prop)
    return {
        "property_id": prop,
        "name": info.get("displayName", ""),
        "time_zone": info.get("timeZone", ""),
        "currency": info.get("currencyCode", ""),
        "industry": info.get("industryCategory", ""),
        "service_level": info.get("serviceLevel", ""),
        "data_retention": {
            "event_data": RETENTION_TEXT.get(retention.get("eventDataRetention", ""),
                                             retention.get("eventDataRetention", "")),
            "user_data": RETENTION_TEXT.get(retention.get("userDataRetention", ""),
                                            retention.get("userDataRetention", "")),
            "reset_on_new_activity": bool(retention.get("resetUserDataOnNewActivity")),
        },
        "key_events": [_key_event_state(e) for e in client.analytics_key_events(prop)],
        "custom_dimensions": [_dimension_state(d) for d in client.analytics_custom_dimensions(prop)],
        "note": ("Privacy settings (data retention, Google signals, data sharing) are shown or "
                 "left to the Analytics interface — no tool here changes them."),
    }


def _client(args: dict) -> Client:
    return Client()


def _login(args: dict) -> str | None:
    """None means: take the manager account from the configuration.

    Not the empty string — that now means "send no manager header at
    all", which is a thing a diagnosis needs to be able to ask for.
    """
    return args.get("login_customer_id") or None


def tool_accounts(args: dict) -> dict:
    client = _client(args)
    ids = client.list_accessible_customers()
    accounts = []
    for customer_id in ids:
        entry: dict = {"customer_id": customer_id}
        try:
            rows = client.search(
                customer_id,
                "SELECT customer.id, customer.descriptive_name, customer.currency_code, "
                "customer.time_zone, customer.manager, customer.test_account, "
                "customer.status FROM customer LIMIT 1",
                max_rows=1,
            )
            if rows:
                entry.update(flatten(rows[0]))
        except GoogleAdsError as exc:
            entry["error"] = exc.message.splitlines()[0]
        accounts.append(entry)
    return {"account_count": len(accounts), "accounts": accounts,
            "note": ("A manager account (customer.manager true) holds no campaigns itself. "
                     "Pass its ID as login_customer_id and a client account as customer_id.")}


def tool_report(args: dict) -> dict:
    report_name = args["report"]
    report = REPORTS.get(report_name)
    if not report:
        raise GoogleAdsError(f"Unknown report '{report_name}'. Known: {', '.join(sorted(REPORTS))}.")

    conditions = []
    if report.get("where"):
        conditions.append(report["where"])
    if report.get("date"):
        conditions.append(date_clause(args.get("date_range", "LAST_30_DAYS"),
                                      args.get("start_date", ""), args.get("end_date", "")))
    if args.get("filter"):
        conditions.append(f"({args['filter']})")

    query = "SELECT " + ", ".join(report["fields"]) + " FROM " + report["from"]
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    if report.get("order"):
        query += " ORDER BY " + report["order"]

    limit = int(args.get("limit") or DEFAULT_ROW_LIMIT)
    client = _client(args)
    rows = client.search(args["customer_id"], query, max_rows=max(limit * 2, limit + 1),
                         login_customer_id=_login(args))
    answer = shape(rows, limit)
    answer["query"] = query
    answer["report"] = report_name
    return answer


def tool_query(args: dict) -> dict:
    limit = int(args.get("limit") or DEFAULT_ROW_LIMIT)
    client = _client(args)
    rows = client.search(args["customer_id"], args["query"], max_rows=max(limit * 2, limit + 1),
                         login_customer_id=_login(args))
    return shape(rows, limit)


def tool_fields(args: dict) -> dict:
    conditions = []
    if args.get("name_contains"):
        conditions.append(f"name LIKE {gaql_string('%' + args['name_contains'] + '%')}")
    if args.get("resource"):
        conditions.append(f"name LIKE {gaql_string(args['resource'] + '.%')}")
    query = ("SELECT name, category, data_type, selectable, filterable, sortable, "
             "is_repeated, type_url, enum_values, selectable_with FROM google_ads_field")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    client = _client(args)
    answer = client.call("POST", "googleAdsFields:search", {"query": query, "pageSize": 1000})
    rows = answer.get("results", [])
    limit = int(args.get("limit") or 100)
    trimmed = []
    for row in rows[:limit]:
        entry = {k: v for k, v in row.items() if k != "selectableWith"}
        # selectable_with is often hundreds of entries; a count plus a sample
        # says what the caller needs without flooding the answer.
        with_list = row.get("selectableWith") or []
        if with_list:
            entry["selectable_with_count"] = len(with_list)
            entry["selectable_with_sample"] = with_list[:15]
        trimmed.append(entry)
    result = {"row_count": len(trimmed), "fields": trimmed}
    if len(rows) > limit:
        result["truncated"] = True
        result["note"] = f"{len(rows)} fields matched, {limit} shown."
    return result


def _keyword_plan_common(args: dict) -> dict:
    return {
        "language": f"languageConstants/{args.get('language_id', '1001')}",
        "geoTargetConstants": [f"geoTargetConstants/{g}" for g in
                               (args.get("geo_target_ids") or ["2040"])],
        "keywordPlanNetwork": args.get("network", "GOOGLE_SEARCH"),
        "includeAdultKeywords": bool(args.get("include_adult", False)),
    }


def _shape_keyword_metrics(entry: dict) -> dict:
    """Pulls the numbers out of a KeywordPlanHistoricalMetrics block."""
    metrics = entry.get("keywordIdeaMetrics") or entry.get("keywordMetrics") or {}
    row = {
        "keyword": entry.get("text"),
        "avg_monthly_searches": metrics.get("avgMonthlySearches"),
        "competition": metrics.get("competition"),
        "competition_index": metrics.get("competitionIndex"),
        "low_top_of_page_bid": _micros_to_amount(metrics.get("lowTopOfPageBidMicros")),
        "high_top_of_page_bid": _micros_to_amount(metrics.get("highTopOfPageBidMicros")),
        "average_cpc": _micros_to_amount(metrics.get("averageCpcMicros")),
    }
    volumes = metrics.get("monthlySearchVolumes") or []
    if volumes:
        row["monthly_volumes"] = [
            {"month": f"{v.get('year')}-{v.get('month')}", "searches": v.get("monthlySearches")}
            for v in volumes[-12:]
        ]
    return {k: v for k, v in row.items() if v is not None}


def _micros_to_amount(value) -> float | None:
    try:
        return round(int(value) / 1_000_000, 2)
    except (TypeError, ValueError):
        return None


def _call_planning(client: Client, path: str, body: dict, login: str) -> dict:
    """Calls a Keyword Planner endpoint and explains the one refusal that surprises.

    A developer token with Explorer access reaches production accounts but
    has the planning tools switched off. Everything else in this server
    keeps working, so the failure looks like a bug in the tool rather than
    a property of the token. It is neither: it is the access level, and
    the message says so.
    """
    try:
        return client.call("POST", path, body, login_customer_id=login)
    except GoogleAdsError as exc:
        if exc.status in (401, 403) or "not_approved" in exc.message.lower() \
                or "permission" in exc.message.lower():
            raise GoogleAdsError(
                exc.message
                + "\n  Hint: the Keyword Planner needs at least BASIC access. A developer "
                  "token with EXPLORER access reaches production accounts but has the "
                  "planning tools switched off, while every other tool here keeps working. "
                  "Check the access level in the API Center of your manager account, and "
                  "apply for Basic there if you need the planner.",
                detail=exc.detail, status=exc.status,
            ) from exc
        raise


def tool_keyword_ideas(args: dict) -> dict:
    body = _keyword_plan_common(args)
    keywords = [k for k in (args.get("keywords") or []) if k.strip()][:20]
    url = (args.get("url") or "").strip()
    site = (args.get("site") or "").strip()

    if keywords and url:
        body["keywordAndUrlSeed"] = {"url": url, "keywords": keywords}
    elif keywords:
        body["keywordSeed"] = {"keywords": keywords}
    elif url:
        body["urlSeed"] = {"url": url}
    elif site:
        body["siteSeed"] = {"site": site}
    else:
        raise GoogleAdsError("Give at least one seed: keywords, url or site.")

    customer_id = normalize_customer_id(args["customer_id"])
    answer = _call_planning(_client(args), f"customers/{customer_id}:generateKeywordIdeas",
                            body, _login(args))
    results = answer.get("results", [])
    limit = int(args.get("limit") or DEFAULT_ROW_LIMIT)
    ideas = [_shape_keyword_metrics(r) for r in results[:limit]]
    out = {"row_count": len(ideas), "ideas": ideas,
           "seed": {"keywords": keywords, "url": url, "site": site}}
    if len(results) > limit:
        out["truncated"] = True
        out["note"] = f"{len(results)} ideas returned, {limit} shown."
    return out


def tool_keyword_metrics(args: dict) -> dict:
    body = _keyword_plan_common(args)
    body["keywords"] = [k for k in (args.get("keywords") or []) if k.strip()]
    if not body["keywords"]:
        raise GoogleAdsError("keywords is empty.")

    customer_id = normalize_customer_id(args["customer_id"])
    answer = _call_planning(_client(args),
                            f"customers/{customer_id}:generateKeywordHistoricalMetrics",
                            body, _login(args))
    results = answer.get("results", [])
    limit = int(args.get("limit") or DEFAULT_ROW_LIMIT)
    rows = [_shape_keyword_metrics(r) for r in results[:limit]]
    return {"row_count": len(rows), "keywords": rows}


def _write(args: dict, operations: list[dict], summary: str) -> dict:
    """Runs the operations and answers the same way for every write tool."""
    client = _client(args)
    dry_run = args.get("dry_run", True)
    answer = client.mutate(
        args["customer_id"], operations,
        dry_run=dry_run,
        partial_failure=bool(args.get("partial_failure", False)),
        login_customer_id=_login(args),
        response_content_type=args.get("response_content_type", "RESOURCE_NAME_ONLY"),
        reason=args.get("reason", ""),
    )
    results = answer.get("mutateOperationResponses", [])
    out: dict = {
        "dry_run": bool(dry_run),
        "operation_count": len(operations),
        "summary": summary,
        "applied": [] if dry_run else [
            list(r.values())[0].get("resourceName") for r in results if r
        ],
    }
    if dry_run:
        out["status"] = ("VALIDATED — Google accepted this change but nothing was written. "
                         "Present the plan, get approval, then call again with dry_run=false.")
    else:
        out["status"] = f"APPLIED — {len(results)} operations written."
    if answer.get("partialFailureError"):
        out["partial_failure_error"] = answer["partialFailureError"]
    return out


def tool_add_keywords(args: dict) -> dict:
    customer_id = normalize_customer_id(args["customer_id"])
    ad_group = f"customers/{customer_id}/adGroups/{args['ad_group_id']}"
    operations = []
    for keyword in args["keywords"]:
        criterion: dict = {
            "adGroup": ad_group,
            "status": args.get("status", "ENABLED"),
            "keyword": {"text": keyword["text"],
                        "matchType": keyword.get("match_type", "PHRASE")},
        }
        if keyword.get("cpc_bid_micros"):
            criterion["cpcBidMicros"] = str(int(keyword["cpc_bid_micros"]))
        if keyword.get("final_url"):
            criterion["finalUrls"] = [keyword["final_url"]]
        operations.append({"adGroupCriterionOperation": {"create": criterion}})
    texts = ", ".join(k["text"] for k in args["keywords"][:5])
    return _write(args, operations,
                  f"Add {len(operations)} keywords to ad group {args['ad_group_id']}: {texts}"
                  + (" ..." if len(args["keywords"]) > 5 else ""))


def tool_add_negative_keywords(args: dict) -> dict:
    customer_id = normalize_customer_id(args["customer_id"])
    level = args["level"]
    operations = []

    for keyword in args["keywords"]:
        info = {"text": keyword["text"], "matchType": keyword.get("match_type", "PHRASE")}
        if level == "campaign":
            if not args.get("campaign_id"):
                raise GoogleAdsError("level=campaign needs campaign_id.")
            operations.append({"campaignCriterionOperation": {"create": {
                "campaign": f"customers/{customer_id}/campaigns/{args['campaign_id']}",
                "negative": True, "keyword": info,
            }}})
        elif level == "ad_group":
            if not args.get("ad_group_id"):
                raise GoogleAdsError("level=ad_group needs ad_group_id.")
            operations.append({"adGroupCriterionOperation": {"create": {
                "adGroup": f"customers/{customer_id}/adGroups/{args['ad_group_id']}",
                "negative": True, "keyword": info,
            }}})
        elif level == "shared_set":
            if not args.get("shared_set_id"):
                raise GoogleAdsError("level=shared_set needs shared_set_id.")
            operations.append({"sharedCriterionOperation": {"create": {
                "sharedSet": f"customers/{customer_id}/sharedSets/{args['shared_set_id']}",
                "keyword": info,
            }}})
        else:
            raise GoogleAdsError(f"Unknown level '{level}'.")

    texts = ", ".join(k["text"] for k in args["keywords"][:5])
    return _write(args, operations,
                  f"Exclude {len(operations)} keywords on {level} level: {texts}"
                  + (" ..." if len(args["keywords"]) > 5 else ""))


STATUS_OPERATION = {
    "campaign": "campaignOperation",
    "ad_group": "adGroupOperation",
    "ad_group_criterion": "adGroupCriterionOperation",
    "ad_group_ad": "adGroupAdOperation",
}


def tool_set_status(args: dict) -> dict:
    entity = args["entity"]
    key = STATUS_OPERATION.get(entity)
    if not key:
        raise GoogleAdsError(f"Unknown entity '{entity}'.")
    status = args["status"]
    operations = []
    for resource_name in args["resource_names"]:
        if status == "REMOVED":
            operations.append({key: {"remove": resource_name}})
        else:
            operations.append({key: {
                "update": {"resourceName": resource_name, "status": status},
                "updateMask": "status",
            }})
    return _write(args, operations,
                  f"Set {len(operations)} {entity} entries to {status}")


def tool_set_budget(args: dict) -> dict:
    if args.get("amount_micros") is not None:
        micros = int(args["amount_micros"])
    elif args.get("amount") is not None:
        micros = int(round(float(args["amount"]) * 1_000_000))
    else:
        raise GoogleAdsError("Give either amount (in currency) or amount_micros.")

    operations = [{"campaignBudgetOperation": {
        "update": {"resourceName": args["budget_resource_name"], "amountMicros": str(micros)},
        "updateMask": "amount_micros",
    }}]
    return _write(args, operations,
                  f"Set daily budget of {args['budget_resource_name']} to "
                  f"{micros / 1_000_000:.2f}")


def tool_set_bid(args: dict) -> dict:
    entity = args["entity"]
    key = STATUS_OPERATION.get(entity)
    if key not in ("adGroupCriterionOperation", "adGroupOperation"):
        raise GoogleAdsError(f"Bids can be set on ad_group_criterion or ad_group, not '{entity}'.")
    operations = []
    for bid in args["bids"]:
        operations.append({key: {
            "update": {"resourceName": bid["resource_name"],
                       "cpcBidMicros": str(int(bid["cpc_bid_micros"]))},
            "updateMask": "cpc_bid_micros",
        }})
    return _write(args, operations, f"Set CPC bid on {len(operations)} {entity} entries")


def tool_mutate(args: dict) -> dict:
    operations = args.get("operations") or []
    if not operations:
        raise GoogleAdsError("operations is empty.")
    kinds = sorted({k for op in operations for k in op})
    return _write(args, operations, f"{len(operations)} raw operations: {', '.join(kinds)}")


def tool_change_log(args: dict) -> dict:
    if not CHANGE_LOG.exists():
        return {"entry_count": 0, "entries": [], "note": f"No log yet at {CHANGE_LOG}."}
    # An Ads account filters exactly; anything else ("analytics",
    # "sc-domain:neo-digital.at", a property ID) matches the logged target.
    wanted, ads_filter = str(args.get("customer_id") or "").strip(), False
    if wanted:
        try:
            wanted, ads_filter = normalize_customer_id(wanted), True
        except GoogleAdsError:
            pass
    entries = []
    for line in CHANGE_LOG.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if wanted and entry.get("customer_id") != wanted and (
                ads_filter or wanted not in str(entry.get("customer_id", ""))):
            continue
        if not args.get("include_operations"):
            entry.pop("operations", None)
            entry.pop("detail", None)
        entries.append(entry)
    entries.reverse()
    limit = int(args.get("limit") or 20)
    return {"entry_count": len(entries[:limit]), "total": len(entries),
            "log_file": str(CHANGE_LOG), "entries": entries[:limit]}


HANDLERS = {
    "google_ads_accounts": tool_accounts,
    "google_ads_report": tool_report,
    "google_ads_query": tool_query,
    "google_ads_fields": tool_fields,
    "google_ads_keyword_ideas": tool_keyword_ideas,
    "google_ads_keyword_metrics": tool_keyword_metrics,
    "google_ads_add_keywords": tool_add_keywords,
    "google_ads_add_negative_keywords": tool_add_negative_keywords,
    "google_ads_set_status": tool_set_status,
    "google_ads_set_budget": tool_set_budget,
    "google_ads_set_bid": tool_set_bid,
    "google_ads_mutate": tool_mutate,
    "search_console_sites": tool_gsc_sites,
    "search_console_performance": tool_gsc_performance,
    "search_console_inspect_url": tool_gsc_inspect_url,
    "search_console_sitemaps": tool_gsc_sitemaps,
    "analytics_properties": tool_ga_properties,
    "analytics_report": tool_ga_report,
    "analytics_metadata": tool_ga_metadata,
    "analytics_settings": tool_ga_settings,
    "search_console_submit_sitemap": tool_gsc_submit_sitemap,
    "search_console_delete_sitemap": tool_gsc_delete_sitemap,
    "analytics_key_event": tool_ga_key_event,
    "analytics_custom_dimension": tool_ga_custom_dimension,
    "google_ads_change_log": tool_change_log,
}


# --------------------------------------------------------------------------
# JSON-RPC plumbing
# --------------------------------------------------------------------------

def server_info() -> dict:
    # name ist die technische Kennung und bleibt; title ist die Aufschrift
    # in der Connector-Liste von claude.ai und traegt deshalb die Marke.
    return {"name": SERVER_NAME, "version": SERVER_VERSION,
            "title": PORTAL_NAME}


def capabilities() -> dict:
    return {"tools": {"listChanged": False}}


def handle(method: str, params: dict) -> dict | None:
    """Answers one request. None means: notification, stay silent."""
    if method == "initialize":
        asked = (params or {}).get("protocolVersion", "")
        version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[1]
        return {"protocolVersion": version, "capabilities": capabilities(),
                "serverInfo": server_info()}

    if method == "server/discover":
        return {"resultType": "complete",
                "protocolVersions": list(PROTOCOL_VERSIONS),
                "capabilities": capabilities(),
                "serverInfo": server_info()}

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return {}

    if method == "tools/list":
        return {"resultType": "complete", "tools": tool_catalogue(),
                "ttlMs": 300000, "cacheScope": "private"}

    if method == "tools/call":
        name = (params or {}).get("name", "")
        arguments = (params or {}).get("arguments") or {}
        handler = HANDLERS.get(name)
        if not handler:
            return error_result(f"Unknown tool '{name}'. Known: {', '.join(HANDLERS)}.")
        try:
            payload = handler(arguments)
        except GoogleAdsError as exc:
            return error_result(exc.message)
        except Exception as exc:  # noqa: BLE001 - an agent needs the reason, not a crash
            print(traceback.format_exc(), file=sys.stderr)
            return error_result(f"{type(exc).__name__}: {exc}")
        return {"resultType": "complete", "isError": False, "content": [
            {"type": "text", "text": json.dumps(payload, indent=2, ensure_ascii=False,
                                                default=str)}
        ]}

    if method in ("resources/list", "prompts/list"):
        key = method.split("/")[0]
        return {"resultType": "complete", key: [], "ttlMs": 300000, "cacheScope": "private"}

    raise LookupError(method)


def error_result(message: str) -> dict:
    """A tool error: reported inside the result so the agent can react to it."""
    return {"resultType": "complete", "isError": True,
            "content": [{"type": "text", "text": message}]}


def serve() -> int:
    """Reads newline-delimited JSON-RPC from stdin until it closes."""
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            respond(out, {"jsonrpc": "2.0", "id": None,
                          "error": {"code": -32700, "message": f"Parse error: {exc}"}})
            continue

        request_id = message.get("id")
        method = message.get("method", "")
        try:
            result = handle(method, message.get("params") or {})
        except LookupError:
            if request_id is not None:
                respond(out, {"jsonrpc": "2.0", "id": request_id,
                              "error": {"code": -32601, "message": f"Method not found: {method}"}})
            continue
        except Exception as exc:  # noqa: BLE001
            print(traceback.format_exc(), file=sys.stderr)
            if request_id is not None:
                respond(out, {"jsonrpc": "2.0", "id": request_id,
                              "error": {"code": -32603, "message": f"Internal error: {exc}"}})
            continue

        if request_id is None or result is None:
            continue
        respond(out, {"jsonrpc": "2.0", "id": request_id, "result": result})
    return 0


def respond(out, message: dict) -> None:
    out.write(json.dumps(message, ensure_ascii=False, default=str) + "\n")
    out.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP server for Google Ads.")
    parser.add_argument("--list-tools", action="store_true",
                        help="print the tool catalogue as JSON and exit")
    parser.add_argument("--check-config", action="store_true",
                        help="load the configuration, report what is missing, and exit")
    options = parser.parse_args()

    if options.list_tools:
        print(json.dumps(tool_catalogue(), indent=2, ensure_ascii=False))
        return 0
    if options.check_config:
        try:
            config = load_config()
        except GoogleAdsError as exc:
            print(exc.message, file=sys.stderr)
            return 1
        print(json.dumps({"api_version": config["api_version"],
                          "login_customer_id": config.get("login_customer_id", ""),
                          "guardrails": config["guardrails"]}, indent=2))
        return 0
    return serve()


if __name__ == "__main__":
    sys.exit(main())
