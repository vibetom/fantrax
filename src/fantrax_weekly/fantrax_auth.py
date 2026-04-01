"""Authenticated Fantrax API client using the internal /fxpa/req endpoint.

The public API (/fxea/general) doesn't expose player stats, transactions, or
matchup scoring. The internal API that the Fantrax web app uses (/fxpa/req)
has all of this, but requires session cookies from a logged-in browser session.

This module handles programmatic login and provides methods for all the
rich data endpoints.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

LOGIN_URL = "https://www.fantrax.com/fxpa/req"
FXPA_URL = "https://www.fantrax.com/fxpa/req"


class FantraxAuthAPI:
    """Authenticated client for Fantrax internal API."""

    def __init__(
        self,
        league_id: str,
        username: str = "",
        password: str = "",
    ) -> None:
        self.league_id = league_id
        self._username = username
        self._password = password
        self._client = httpx.Client(
            timeout=60,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; FantraxWeekly/0.1)",
                "Content-Type": "application/json",
            },
        )
        self._logged_in = False

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FantraxAuthAPI:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ── Authentication ───────────────────────────────────────────────

    def login(self) -> bool:
        """Log in to Fantrax and store session cookies.

        Returns True if login succeeded.
        """
        if not self._username or not self._password:
            logger.warning("No credentials provided, skipping login")
            return False

        resp = self._client.post(
            LOGIN_URL,
            json={
                "msgs": [
                    {
                        "method": "login",
                        "data": {
                            "username": self._username,
                            "password": self._password,
                        },
                    }
                ]
            },
        )
        resp.raise_for_status()
        data = resp.json()

        # Check if login succeeded — the response contains session info
        responses = data.get("responses", [])
        if responses and not responses[0].get("error"):
            self._logged_in = True
            logger.info("Fantrax login successful")
            return True

        error = responses[0].get("error", "Unknown error") if responses else "No response"
        logger.warning("Fantrax login failed: %s", error)
        return False

    @property
    def is_logged_in(self) -> bool:
        return self._logged_in

    # ── Internal API helper ──────────────────────────────────────────

    def _call(self, method: str, data: dict | None = None) -> dict:
        """Call a /fxpa/req method."""
        msg_data = {"leagueId": self.league_id}
        if data:
            msg_data.update(data)

        resp = self._client.post(
            f"{FXPA_URL}?leagueId={self.league_id}",
            json={"msgs": [{"method": method, "data": msg_data}]},
        )
        resp.raise_for_status()
        result = resp.json()

        responses = result.get("responses", [])
        if not responses:
            return {}
        if responses[0].get("error"):
            raise RuntimeError(f"Fantrax API error: {responses[0]['error']}")
        return responses[0].get("data", {})

    # ── Player Stats & Scoring ───────────────────────────────────────

    def get_live_scoring(
        self,
        period: str | None = None,
        scoring_period_id: str | None = None,
        view_type: str = "STATS",
    ) -> dict:
        """Get detailed player stats and scoring for a period.

        This is the main endpoint for player performance data.
        view_type can be: STATS, STANDINGS, MATCHUP
        """
        data: dict = {"viewType": view_type}
        if period is not None:
            data["period"] = str(period)
        if scoring_period_id:
            data["sppId"] = scoring_period_id
        return self._call("getLiveScoringStats", data)

    def get_team_roster_info(
        self,
        team_id: str,
        period: str | None = None,
        view: str = "STATS",
    ) -> dict:
        """Get detailed roster with scoring data for a specific team."""
        data: dict = {"teamId": team_id, "view": view}
        if period is not None:
            data["scoringPeriod"] = str(period)
            data["period"] = str(period)
        return self._call("getTeamRosterInfo", data)

    # ── Transactions ─────────────────────────────────────────────────

    def get_transaction_history(self, max_results: int = 100) -> dict:
        """Get transaction history (trades, adds, drops, waivers)."""
        return self._call(
            "getTransactionDetailsHistory",
            {"maxResultsPerPage": str(max_results)},
        )

    def get_pending_transactions(self) -> dict:
        """Get pending transactions (waivers, trade offers)."""
        return self._call("getPendingTransactions")

    # ── Matchups & Standings ─────────────────────────────────────────

    def get_matchup_scoring(self, period: str | None = None) -> dict:
        """Get matchup-level scoring breakdown."""
        return self.get_live_scoring(period=period, view_type="MATCHUP")

    def get_rich_standings(self) -> dict:
        """Get detailed standings with more data than the public API."""
        return self._call("getStandings", {"view": "STANDINGS"})

    # ── Other ────────────────────────────────────────────────────────

    def get_trade_blocks(self) -> dict:
        """Get current trade block listings."""
        return self._call("getTradeBlocks")

    def get_league_info(self) -> dict:
        """Get league configuration via authenticated API."""
        return self._call("getFantasyLeagueInfo")
