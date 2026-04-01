"""Collects and structures all Fantrax league data for AI commentary.

Pulls from both the public API (basic league data) and the authenticated
internal API (detailed player stats, transactions, matchup scoring).
Assembles everything into a single structured document that an AI can
read and immediately use to write weekly fantasy baseball commentary.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fantrax_weekly.fantrax_api import FantraxAPI
from fantrax_weekly.fantrax_auth import FantraxAuthAPI

logger = logging.getLogger(__name__)

# ── AI Instructions (embedded in the output file) ────────────────────

AI_INSTRUCTIONS = """
=============================================================================
FANTASY BASEBALL WEEKLY COMMENTARY — DATA BUNDLE
=============================================================================

You are an AI sports journalist writing a weekly fantasy baseball newsletter.
This file contains EVERYTHING you need to write an entertaining, insightful,
and detailed weekly recap for a fantasy baseball league.

YOUR TASK:
Write a fun, engaging weekly article covering:

1. MATCHUP RECAPS — For each head-to-head matchup this week:
   - Who won and by how much
   - The key players that made the difference
   - Any surprising performances (benchwarmer going off, star flopping)
   - Close matchups that came down to the wire

2. PLAYER SPOTLIGHTS — Standout individual performances:
   - Best hitter of the week (HR, RBI, AVG, OPS)
   - Best pitcher of the week (W, K, ERA, WHIP)
   - Biggest disappointments / busts
   - Sleeper picks who are outperforming their draft position (compare to ADP data)

3. STANDINGS & POWER RANKINGS — The big picture:
   - Who's on top and why
   - Hot streaks and cold streaks
   - Playoff race implications
   - Teams on the rise vs. teams in freefall

4. TRANSACTION REPORT — Roster moves that matter:
   - Notable trades and what they mean for both sides
   - Waiver wire pickups that could change the race
   - Players who got dropped that others should grab

5. LOOKING AHEAD — Next week preview:
   - Key matchups to watch
   - Players with favorable/unfavorable schedules

STYLE GUIDELINES:
- Be entertaining and witty — this should be fun to read
- Use team owner names when available, not just team names
- Include specific stats to back up your takes
- Add trash talk, hot takes, and bold predictions
- Reference the draft (who's living up to their pick, who's a bust)
- Keep it feeling like a newsletter between friends

The data sections below are tagged with descriptions to help you understand
what each dataset contains. Use ALL of it.
=============================================================================
"""


def collect_full_bundle(
    public_api: FantraxAPI,
    auth_api: FantraxAuthAPI | None = None,
    period: int | None = None,
) -> dict:
    """Pull absolutely everything from Fantrax and assemble into one AI-ready bundle.

    Args:
        public_api: Public API client (always available)
        auth_api: Authenticated API client (optional, enables rich stats)
        period: Scoring period to focus on (None = current)

    Returns:
        Complete data bundle with AI instructions and all league data.
    """
    bundle: dict = {
        "ai_instructions": AI_INSTRUCTIONS,
        "_meta": {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "period_requested": period,
            "has_authenticated_data": auth_api is not None and auth_api.is_logged_in,
            "sections": [],
        },
    }

    sections_collected = []

    # ── Public API data (always available) ───────────────────────────

    bundle["league_info"] = _safe_collect(
        "league_info",
        "Full league configuration: team names/IDs, matchup schedule, player pool, "
        "scoring categories, roster slot settings. Use team names for all commentary.",
        lambda: public_api.get_league_info(),
    )
    sections_collected.append("league_info")

    bundle["standings"] = _safe_collect(
        "standings",
        "Current league standings: rank, team name, W-L-T record, points scored, "
        "games back, win percentage. Use this for power rankings and playoff race analysis.",
        lambda: public_api.get_standings(),
    )
    sections_collected.append("standings")

    bundle["rosters"] = _safe_collect(
        "rosters",
        "All team rosters for the scoring period. Each team's roster has every "
        "rostered player with position, lineup slot (starter vs bench), injury/status, "
        "and salary/contract data. Use to identify key players, injured stars, "
        "and bench decisions that affected outcomes.",
        lambda: public_api.get_team_rosters(period=period),
    )
    sections_collected.append("rosters")

    bundle["adp"] = _safe_collect(
        "adp",
        "Average Draft Position for MLB players across all Fantrax leagues. "
        "Compare where players were drafted vs. current performance to identify "
        "busts (high ADP, bad stats), sleepers (low ADP, great stats), and value picks.",
        lambda: public_api.get_adp(sport="MLB"),
    )
    sections_collected.append("adp")

    bundle["draft_results"] = _safe_collect(
        "draft_results",
        "This league's actual draft results: which team picked which player and when. "
        "Use to roast owners for bad picks and praise smart ones.",
        lambda: public_api.get_draft_results(),
    )
    sections_collected.append("draft_results")

    bundle["draft_picks"] = _safe_collect(
        "draft_picks",
        "Future draft pick ownership (including traded picks). "
        "Shows which teams are building for the future vs. going all-in now.",
        lambda: public_api.get_draft_picks(),
    )
    sections_collected.append("draft_picks")

    bundle["player_ids"] = _safe_collect(
        "player_ids",
        "Fantrax player ID to name mapping for MLB. "
        "Use to cross-reference player IDs in other datasets.",
        lambda: public_api.get_player_ids(sport="MLB"),
    )
    sections_collected.append("player_ids")

    # ── Authenticated API data (rich stats, requires login) ──────────

    if auth_api and auth_api.is_logged_in:
        bundle["player_stats"] = _safe_collect(
            "player_stats",
            "DETAILED PLAYER STATISTICS AND SCORING for the requested period. "
            "This is the most important dataset for weekly commentary. Contains "
            "every player's stats (HR, RBI, AVG, OPS, ERA, WHIP, K, W, etc.), "
            "fantasy points scored, and scoring category breakdowns. "
            "Use this to identify MVPs, busts, and breakout performers.",
            lambda: auth_api.get_live_scoring(period=str(period) if period else None),
        )
        sections_collected.append("player_stats")

        bundle["matchup_scoring"] = _safe_collect(
            "matchup_scoring",
            "HEAD-TO-HEAD MATCHUP SCORING BREAKDOWN. Shows each matchup pairing "
            "with both teams' scoring totals and category-by-category results. "
            "This is essential for writing matchup recaps — who won, by how much, "
            "and which categories decided it.",
            lambda: auth_api.get_matchup_scoring(
                period=str(period) if period else None
            ),
        )
        sections_collected.append("matchup_scoring")

        bundle["transactions"] = _safe_collect(
            "transaction_history",
            "RECENT TRANSACTION HISTORY: trades, waiver claims, free agent pickups, "
            "and drops. Each transaction shows the players involved, the teams, "
            "and when it happened. Use for the transaction report section — "
            "identify savvy moves, desperate drops, and blockbuster trades.",
            lambda: auth_api.get_transaction_history(max_results=50),
        )
        sections_collected.append("transactions")

        bundle["pending_transactions"] = _safe_collect(
            "pending_transactions",
            "Pending transactions: open waiver claims and trade offers. "
            "Use for 'looking ahead' commentary about moves in progress.",
            lambda: auth_api.get_pending_transactions(),
        )
        sections_collected.append("pending_transactions")

        bundle["trade_blocks"] = _safe_collect(
            "trade_blocks",
            "Players currently on the trade block. Shows which teams are "
            "shopping which players — great for speculation and trade rumors.",
            lambda: auth_api.get_trade_blocks(),
        )
        sections_collected.append("trade_blocks")

        bundle["rich_standings"] = _safe_collect(
            "rich_standings",
            "Detailed standings from the authenticated API with additional "
            "data beyond the public standings (more stats, tiebreakers, etc.).",
            lambda: auth_api.get_rich_standings(),
        )
        sections_collected.append("rich_standings")

        # Pull per-team roster details with scoring
        team_ids = _extract_team_ids(bundle.get("league_info", {}))
        if team_ids:
            team_rosters_detail = {}
            for tid, tname in team_ids.items():
                team_rosters_detail[tid] = _safe_collect(
                    f"team_roster_{tname}",
                    f"Detailed roster and scoring for {tname}. "
                    f"Every player's stats, fantasy points, and lineup position.",
                    lambda tid=tid: auth_api.get_team_roster_info(
                        tid, period=str(period) if period else None
                    ),
                )
            bundle["team_roster_details"] = {
                "_tag": "team_roster_details",
                "_description": (
                    "Per-team detailed rosters with full player scoring breakdowns. "
                    "Each team entry shows every player's individual stats and fantasy points."
                ),
                "teams": team_rosters_detail,
            }
            sections_collected.append("team_roster_details")
    else:
        bundle["_auth_note"] = (
            "NOTE: Authenticated API data is not available. To get detailed player "
            "statistics, matchup scoring breakdowns, and transaction history, set "
            "FANTRAX_USERNAME and FANTRAX_PASSWORD environment variables. "
            "Without these, only basic league data from the public API is included."
        )

    bundle["_meta"]["sections"] = sections_collected
    return bundle


def bundle_to_text(bundle: dict) -> str:
    """Convert the full bundle to a single text file optimized for AI consumption.

    Returns a formatted text document with AI instructions followed by
    each data section clearly labeled and described.
    """
    lines = [bundle.get("ai_instructions", "")]

    meta = bundle.get("_meta", {})
    lines.append(f"Data collected: {meta.get('collected_at', 'unknown')}")
    lines.append(f"Period: {meta.get('period_requested', 'current')}")
    lines.append(
        f"Authenticated data: {'YES' if meta.get('has_authenticated_data') else 'NO (limited data)'}"
    )
    lines.append(f"Sections included: {', '.join(meta.get('sections', []))}")
    lines.append(f"Auth status: {meta.get('auth_status', 'unknown')}")
    lines.append(f"Credentials provided: {meta.get('credentials_provided', False)}")
    lines.append("")

    if bundle.get("_auth_note"):
        lines.append(f"WARNING: {bundle['_auth_note']}")
        lines.append("")

    # Surface any section-level errors prominently
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

            # Output the data portion
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
        return {
            "_tag": tag,
            "_description": description,
            "data": data,
        }
    except Exception as e:
        logger.warning("Failed to collect %s: %s", tag, e)
        return {
            "_tag": tag,
            "_description": description,
            "error": str(e),
        }


def _extract_team_ids(league_info: dict) -> dict[str, str]:
    """Try to extract team ID → team name mapping from league info."""
    if not league_info or "data" not in league_info:
        return {}

    data = league_info["data"]
    teams = {}

    # Try common response shapes
    for key in ("teams", "teamList", "fantasyTeams"):
        if key in data and isinstance(data[key], (list, dict)):
            items = data[key]
            if isinstance(items, dict):
                items = items.values()
            for team in items:
                if isinstance(team, dict):
                    tid = team.get("id", team.get("teamId", ""))
                    tname = team.get("name", team.get("teamName", str(tid)))
                    if tid:
                        teams[str(tid)] = tname

    return teams
