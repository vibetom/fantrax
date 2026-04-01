"""Collects and structures all Fantrax league data for AI commentary."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fantrax_weekly.fantrax_api import FantraxAPI

logger = logging.getLogger(__name__)


def collect_weekly_snapshot(api: FantraxAPI, period: int | None = None) -> dict:
    """Pull all available data from Fantrax and assemble into an AI-friendly snapshot.

    Returns a structured dict designed to be passed directly to an LLM for
    generating weekly fantasy baseball commentary. Every section is tagged
    with a description so the AI understands what it's looking at.
    """
    snapshot: dict = {
        "_meta": {
            "description": (
                "Complete weekly snapshot of a Fantrax fantasy baseball league. "
                "Use this data to write entertaining, insightful weekly commentary. "
                "Cover standings movement, matchup results, standout performances, "
                "roster moves, and any notable storylines."
            ),
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "period_requested": period,
        },
    }

    # 1. League info — teams, matchups, player pool, settings
    snapshot["league_info"] = _collect_league_info(api)

    # 2. Standings — current rankings, W-L-T, points
    snapshot["standings"] = _collect_standings(api)

    # 3. Rosters — full team rosters with player details
    snapshot["rosters"] = _collect_rosters(api, period)

    # 4. Player universe — ID mapping for cross-referencing
    snapshot["player_ids"] = _collect_player_ids(api)

    # 5. ADP context — where players were expected to be drafted vs reality
    snapshot["adp"] = _collect_adp(api)

    # 6. Draft data — how the league's draft played out
    snapshot["draft"] = _collect_draft(api)

    return snapshot


def _collect_league_info(api: FantraxAPI) -> dict:
    """League config, team names, matchups, and player pool."""
    try:
        data = api.get_league_info()
        return {
            "_tag": "league_info",
            "_description": (
                "Full league configuration including all team names and IDs, "
                "current and past matchup pairings, all players in the player pool "
                "with their info, and league scoring/roster settings. "
                "Use team names for commentary. Matchup data shows head-to-head results."
            ),
            "data": data,
        }
    except Exception as e:
        logger.warning("Failed to collect league info: %s", e)
        return {"_tag": "league_info", "error": str(e)}


def _collect_standings(api: FantraxAPI) -> dict:
    """Current league standings with ranks, records, points."""
    try:
        data = api.get_standings()
        return {
            "_tag": "standings",
            "_description": (
                "Current league standings. Includes rank, team name, win-loss-tie record, "
                "points scored, games back, and winning percentage. "
                "Compare week-over-week movement for storylines about rising/falling teams."
            ),
            "data": data,
        }
    except Exception as e:
        logger.warning("Failed to collect standings: %s", e)
        return {"_tag": "standings", "error": str(e)}


def _collect_rosters(api: FantraxAPI, period: int | None) -> dict:
    """Team rosters with player positions, statuses, salary/contract data."""
    try:
        data = api.get_team_rosters(period=period)
        return {
            "_tag": "rosters",
            "_description": (
                "All team rosters for the requested scoring period. Each team's roster "
                "includes every rostered player with their position, lineup slot, "
                "injury/status info, and salary/contract data if the league uses it. "
                "Use this to identify key players on each team, injured stars, "
                "and bench decisions that affected matchup outcomes."
            ),
            "period": period,
            "data": data,
        }
    except Exception as e:
        logger.warning("Failed to collect rosters: %s", e)
        return {"_tag": "rosters", "error": str(e)}


def _collect_player_ids(api: FantraxAPI) -> dict:
    """Fantrax player ID → name mapping for MLB."""
    try:
        data = api.get_player_ids(sport="MLB")
        return {
            "_tag": "player_ids",
            "_description": (
                "Mapping of Fantrax internal player IDs to player names for MLB. "
                "Use this to cross-reference player IDs found in roster and matchup data."
            ),
            "data": data,
        }
    except Exception as e:
        logger.warning("Failed to collect player IDs: %s", e)
        return {"_tag": "player_ids", "error": str(e)}


def _collect_adp(api: FantraxAPI) -> dict:
    """Average Draft Position data — preseason expectations."""
    try:
        data = api.get_adp(sport="MLB")
        return {
            "_tag": "adp",
            "_description": (
                "Average Draft Position (ADP) data for MLB players across Fantrax leagues. "
                "Compare where players were drafted vs. their current performance "
                "to identify busts, sleepers, and value picks for commentary."
            ),
            "data": data,
        }
    except Exception as e:
        logger.warning("Failed to collect ADP: %s", e)
        return {"_tag": "adp", "error": str(e)}


def _collect_draft(api: FantraxAPI) -> dict:
    """Draft picks and results for the league."""
    picks = None
    results = None

    try:
        picks = api.get_draft_picks()
    except Exception as e:
        logger.warning("Failed to collect draft picks: %s", e)

    try:
        results = api.get_draft_results()
    except Exception as e:
        logger.warning("Failed to collect draft results: %s", e)

    return {
        "_tag": "draft",
        "_description": (
            "Draft pick ownership (who owns which picks, including traded picks) "
            "and full draft results showing which team picked which player and when. "
            "Use this to identify trade capital, draft steals/reaches, and team-building strategies."
        ),
        "picks": picks,
        "results": results,
    }
