"""Collects and structures all Fantrax league data for AI commentary.

Pulls from both the public API and authenticated internal API, then
TRANSLATES all raw data into human-readable format. The AI receives
clean, decoded data — not raw Fantrax API responses.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fantrax_weekly.fantrax_api import FantraxAPI
from fantrax_weekly.fantrax_auth import FantraxAuthAPI
from fantrax_weekly.translator import (
    translate_live_scoring,
    translate_standings,
    translate_transactions,
)

logger = logging.getLogger(__name__)

# ── AI Instructions ──────────────────────────────────────────────────

AI_INSTRUCTIONS = """\
=============================================================================
FANTASY BASEBALL WEEKLY COMMENTARY — DATA BUNDLE
=============================================================================

You are an AI sports journalist writing a weekly fantasy baseball newsletter.
This file contains EVERYTHING you need — all data has been pre-decoded into
human-readable format. No Fantrax-specific knowledge is needed.

=== LEAGUE FORMAT ===
This is a HEAD-TO-HEAD ROTISSERIE (H2H Categories) league. Each week:
- Two teams face off in a matchup
- They compete across multiple statistical categories (e.g., HR, RBI, AVG, ERA, K, etc.)
- Each category is scored independently — the team with the better stat WINS that category
- The matchup score is the number of categories won vs lost (e.g., 5-4-1 means 5 wins, 4 losses, 1 tie)
- Standings track total category wins/losses/ties across the season, NOT head-to-head matchup wins

=== HOW TO READ THE DATA ===

STANDINGS section:
- "rank" = current league position
- "win/loss/tie" = total CATEGORY wins/losses/ties for the season (NOT matchup W/L)
- "cpf" (Category Points For) = total categories won this season
- "cpa" (Category Points Against) = total categories lost this season
- "gb" = games back from 1st place
- "wwOrder" = waiver wire priority (lower = picks first)

PLAYER STATS section (most important for commentary):
- "player_stats" is organized by team name
- Each team has a "players" list with every rostered player
- Each player has individual stats like HR, RBI, AVG, SB, ERA, WHIP, K, W, SV, etc.
- "fantasy_points" = total fantasy points for the period
- "category_points" shows how many points each team earned per category
  - "period_points" = points for this week/period
  - "season_points" = cumulative points for the year

MATCHUPS section:
- Shows each head-to-head matchup this period
- Category-by-category results when available
- The matchup score = categories won vs lost (NOT runs scored)

TRANSACTIONS section:
- "Claimed (FA)" = picked up as a free agent
- "Claimed (WW)" = picked up via waiver wire
- "Dropped" = released from roster
- Transactions grouped by team and date

=== YOUR TASK ===
Write a fun, engaging weekly article covering:

1. MATCHUP RECAPS — For each matchup:
   - Who won and the category score (e.g., "BigtexX took down Roman Empire 6-3-1")
   - Which categories each team won
   - Key players that swung categories

2. PLAYER SPOTLIGHTS:
   - Best hitter (most HR, RBI, highest AVG)
   - Best pitcher (most K, wins, lowest ERA/WHIP)
   - Biggest busts (stars who put up zeros)
   - Sleeper performances

3. STANDINGS & POWER RANKINGS:
   - Current rankings with records
   - Who's rising, who's falling
   - Playoff implications

4. TRANSACTION REPORT:
   - Notable pickups and drops
   - Savvy moves vs. desperation drops

5. LOOKING AHEAD:
   - Next week's key matchups
   - Bold predictions

STYLE: Entertaining, witty, like a newsletter between friends. Use specific
stats. Reference owner names. Add trash talk and hot takes.
=============================================================================
"""


def collect_full_bundle(
    public_api: FantraxAPI,
    auth_api: FantraxAuthAPI | None = None,
    period: int | None = None,
) -> dict:
    """Pull everything from Fantrax, translate it, and assemble the AI bundle."""
    bundle: dict = {
        "ai_instructions": AI_INSTRUCTIONS,
        "_meta": {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "period_requested": period,
            "has_authenticated_data": auth_api is not None and auth_api.is_logged_in,
            "sections": [],
        },
    }

    sections = []

    # ── Public API data ──────────────────────────────────────────────

    bundle["league_info"] = _safe_collect(
        "league_info",
        "League configuration: team names, matchup schedule, scoring settings.",
        lambda: public_api.get_league_info(),
    )
    sections.append("league_info")

    bundle["rosters"] = _safe_collect(
        "rosters",
        "All team rosters: players, positions, lineup slots, injury status.",
        lambda: public_api.get_team_rosters(period=period),
    )
    sections.append("rosters")

    bundle["adp"] = _safe_collect(
        "adp",
        "Average Draft Position — compare to actual performance for sleeper/bust analysis.",
        lambda: public_api.get_adp(sport="MLB"),
    )
    sections.append("adp")

    bundle["draft_results"] = _safe_collect(
        "draft_results",
        "This league's draft results: who picked whom and when.",
        lambda: public_api.get_draft_results(),
    )
    sections.append("draft_results")

    # ── Authenticated API data (translated to human-readable) ────────

    if auth_api and auth_api.is_logged_in:
        # Player stats — THE most important section
        raw_scoring = _safe_call(auth_api.get_live_scoring, period=str(period) if period else None)
        if raw_scoring:
            translated = translate_live_scoring(raw_scoring)

            # Diagnostic: check if translation produced actual player data
            team_stats = translated.get("player_stats", {})
            total_players = sum(
                len(t.get("players", [])) for t in team_stats.values() if isinstance(t, dict)
            )
            if total_players == 0:
                logger.warning(
                    "Translation produced 0 players. Raw response keys: %s, "
                    "statsPerTeam keys: %s, scorerMap keys: %s",
                    list(raw_scoring.keys())[:20],
                    list(raw_scoring.get("statsPerTeam", {}).get("allTeamsStats", {}).keys())[:10],
                    list(raw_scoring.get("scorerMap", {}).keys())[:10],
                )

            bundle["standings"] = {
                "_tag": "standings",
                "_description": (
                    "Current league standings. 'win/loss/tie' = total CATEGORY "
                    "wins/losses/ties for the season. 'cpf' = categories won, "
                    "'cpa' = categories lost."
                ),
                "data": translate_standings(
                    _safe_call(auth_api.get_rich_standings) or {}
                ),
            }
            sections.append("standings")

            player_stats_data = {
                "period": translated.get("display_period", ""),
                "date": translated.get("date", ""),
                "scoring_categories": translated.get("scoring_categories", {}),
                "stat_legend": translated.get("stat_id_to_name", {}),
                "team_stats": team_stats,
            }
            # If translation produced no players, include raw response keys
            # so we can diagnose the response shape
            if total_players == 0:
                player_stats_data["_diagnostic"] = {
                    "raw_top_level_keys": list(raw_scoring.keys()),
                    "has_statsPerTeam": "statsPerTeam" in raw_scoring,
                    "statsPerTeam_keys": list(
                        raw_scoring.get("statsPerTeam", {}).keys()
                    ),
                    "allTeamsStats_team_count": len(
                        raw_scoring.get("statsPerTeam", {}).get("allTeamsStats", {})
                    ),
                    "scorerMap_count": len(raw_scoring.get("scorerMap", {})),
                    "fantasyTeamInfo_count": len(
                        raw_scoring.get("fantasyTeamInfo", {})
                    ),
                    "note": (
                        "Player stats came back empty after translation. "
                        "The raw API response keys above can help diagnose "
                        "whether the Fantrax API returned data in an unexpected format."
                    ),
                }

            bundle["player_stats"] = {
                "_tag": "player_stats",
                "_description": (
                    "DETAILED PLAYER STATISTICS for this scoring period. Organized by "
                    "team. Each player has individual stats (HR, RBI, AVG, ERA, K, etc.) "
                    "and fantasy points. 'category_points' shows each team's category "
                    "standings for the period and season."
                ),
                "data": player_stats_data,
            }
            sections.append("player_stats")

            bundle["matchups"] = {
                "_tag": "matchups",
                "_description": (
                    "Head-to-head matchups for this period. Each matchup shows the "
                    "two teams and category-by-category results. The score is CATEGORIES "
                    "WON vs LOST (e.g., 5-4-1 = 5 categories won, 4 lost, 1 tied), "
                    "NOT runs or points."
                ),
                "data": {
                    "period": translated.get("display_period", ""),
                    "matchups": translated.get("matchups", []),
                    "teams": translated.get("teams", {}),
                },
            }
            sections.append("matchups")
        else:
            bundle["player_stats"] = {"_tag": "player_stats", "error": "Failed to fetch"}
            bundle["matchups"] = {"_tag": "matchups", "error": "Failed to fetch"}

        # Transactions
        raw_tx = _safe_call(auth_api.get_transaction_history, max_results=50)
        if raw_tx:
            bundle["transactions"] = {
                "_tag": "transactions",
                "_description": (
                    "Recent transactions: claims (FA = free agent, WW = waiver wire), "
                    "drops, and trades. Grouped by transaction with team name and date."
                ),
                "data": translate_transactions(raw_tx),
            }
            sections.append("transactions")

        # Pending transactions
        bundle["pending_transactions"] = _safe_collect(
            "pending_transactions",
            "Open waiver claims and trade offers in progress.",
            lambda: auth_api.get_pending_transactions(),
        )
        sections.append("pending_transactions")

        # Trade blocks
        bundle["trade_blocks"] = _safe_collect(
            "trade_blocks",
            "Players on the trade block — who's shopping whom.",
            lambda: auth_api.get_trade_blocks(),
        )
        sections.append("trade_blocks")

    else:
        # Fallback to public standings
        raw_pub_standings = _safe_call(public_api.get_standings)
        if raw_pub_standings:
            bundle["standings"] = {
                "_tag": "standings",
                "_description": "League standings from public API (basic).",
                "data": raw_pub_standings,
            }
            sections.append("standings")

        bundle["_auth_note"] = (
            "WARNING: Authenticated data not available. Player stats, matchup scoring, "
            "and transactions are missing. Set FANTRAX_FX_RM and/or FANTRAX_JSESSIONID "
            "environment variables with cookies from your Fantrax browser session."
        )

    bundle["_meta"]["sections"] = sections
    return bundle


def bundle_to_text(bundle: dict) -> str:
    """Convert the bundle to a text file optimized for AI consumption."""
    lines = [bundle.get("ai_instructions", "")]

    meta = bundle.get("_meta", {})
    lines.append(f"Data collected: {meta.get('collected_at', 'unknown')}")
    lines.append(f"Period: {meta.get('period_requested', 'current')}")
    lines.append(
        f"Authenticated data: {'YES' if meta.get('has_authenticated_data') else 'NO (limited data)'}"
    )
    lines.append(f"Sections included: {', '.join(meta.get('sections', []))}")
    lines.append(f"Auth status: {meta.get('auth_status', 'unknown')}")
    lines.append("")

    if bundle.get("_auth_note"):
        lines.append(bundle["_auth_note"])
        lines.append("")

    # Surface errors
    errors = []
    for key, value in bundle.items():
        if isinstance(value, dict) and "error" in value:
            errors.append(f"  - {value.get('_tag', key)}: {value['error']}")
    if errors:
        lines.append("ERRORS ENCOUNTERED:")
        lines.extend(errors)
        lines.append("")

    for key, value in bundle.items():
        if key in ("ai_instructions", "_meta", "_auth_note"):
            continue

        lines.append("=" * 80)

        if isinstance(value, dict):
            tag = value.get("_tag", key)
            desc = value.get("_description", "")
            lines.append(f"SECTION: {tag.upper()}")
            if desc:
                lines.append(f"DESCRIPTION: {desc}")
            lines.append("=" * 80)
            data = value.get("data", value)
            lines.append(json.dumps(data, indent=2, default=str))
        else:
            lines.append(f"SECTION: {key.upper()}")
            lines.append("=" * 80)
            lines.append(json.dumps(value, indent=2, default=str))

        lines.append("")

    return "\n".join(lines)


# ── Helpers ──────────────────────────────────────────────────────────


def _safe_collect(tag: str, description: str, fn: callable) -> dict:
    """Call fn() and wrap the result with tag/description, catching errors."""
    try:
        data = fn()
        return {"_tag": tag, "_description": description, "data": data}
    except Exception as e:
        logger.warning("Failed to collect %s: %s", tag, e)
        return {"_tag": tag, "_description": description, "error": str(e)}


def _safe_call(fn: callable, **kwargs) -> dict | None:
    """Call fn and return result, or None on error."""
    try:
        return fn(**kwargs)
    except Exception as e:
        logger.warning("API call failed: %s", e)
        return None
