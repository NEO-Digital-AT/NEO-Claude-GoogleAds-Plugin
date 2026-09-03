#!/usr/bin/env python3
"""An MCP server that gives an agent read and write access to Google Ads.

It speaks JSON-RPC over stdin and stdout and offers thirteen tools: six
that read, six that write, and one that shows what was written. The
reading half covers accounts, arbitrary GAQL queries, prepared reports,
the Keyword Planner and the field catalogue. The writing half covers
keywords, negative keywords, status, budgets, bids, and — for everything
the six do not cover — the raw mutate endpoint.

TWO PROTOCOL GENERATIONS. MCP dropped the initialize handshake in the
2026-07-28 revision and replaced it with server/discover. Clients in the
field speak both, so this server answers both and mirrors back whichever
protocol version the client asked for.

WRITING IS A DECISION, NOT A DEFAULT. Every write tool starts as a dry
run (the API's validateOnly), which runs the change through every rule
Google would apply and changes nothing. Passing dry_run=false is what
makes it real, and even then the guardrails in google_ads_client.py have
the last word.

No dependencies beyond the standard library.

    google-ads-mcp.py                 speak MCP on stdin/stdout
    google-ads-mcp.py --list-tools    print the tool catalogue and exit

Diagnostics go to stderr; stdout carries nothing but protocol.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google_ads_client import (  # noqa: E402
    CHANGE_LOG,
    Client,
    GoogleAdsError,
    load_config,
    normalize_customer_id,
)

SERVER_NAME = "neo-google-ads"
SERVER_VERSION = "1.0.0"

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
                            "a page URL, a whole site, or keywords plus a URL."),
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
                            "nothing, it only measures the list you pass in."),
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
            "name": "google_ads_change_log",
            "description": ("Shows what this server wrote, newest first: time, account, "
                            "whether it was a dry run, the reason given and the result. "
                            "This is the local log, separate from Google's change history."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20},
                    "customer_id": {"type": "string", "description": "Filter to one account."},
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

def _client(args: dict) -> Client:
    return Client()


def _login(args: dict) -> str:
    return args.get("login_customer_id") or ""


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
                "customer.status FROM customer",
                page_size=1, max_rows=1,
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
    client = _client(args)
    answer = client.call("POST", f"customers/{customer_id}:generateKeywordIdeas", body,
                         login_customer_id=_login(args))
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
    client = _client(args)
    answer = client.call("POST", f"customers/{customer_id}:generateKeywordHistoricalMetrics",
                         body, login_customer_id=_login(args))
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
    entries = []
    for line in CHANGE_LOG.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if args.get("customer_id") and entry.get("customer_id") != normalize_customer_id(
                args["customer_id"]):
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
    "google_ads_change_log": tool_change_log,
}


# --------------------------------------------------------------------------
# JSON-RPC plumbing
# --------------------------------------------------------------------------

def server_info() -> dict:
    return {"name": SERVER_NAME, "version": SERVER_VERSION,
            "title": "NEO Google Ads"}


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
