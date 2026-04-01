"""Authenticated Fantrax API client using the internal /fxpa/req endpoint.

The public API (/fxea/general) doesn't expose player stats, transactions, or
matchup scoring. The internal API that the Fantrax web app uses (/fxpa/req)
has all of this, but requires session cookies from a logged-in browser session.

Authentication uses a JSESSIONID cookie extracted from the user's browser.
Set the FANTRAX_JSESSIONID environment variable with the cookie value.

All parameter values must be strings (the Fantrax API expects "True" not true,
"1" not 1). This matches the behavior of the known-working FantraxAPI library.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

FXPA_URL = "https://www.fantrax.com/fxpa/req"


class FantraxAuthAPI:
    """Authenticated client for Fantrax internal API."""

    def __init__(
        self,
        league_id: str,
        jsessionid: str = "",
    ) -> None:
        self.league_id = league_id
        cookies = httpx.Cookies()
        if jsessionid:
            cookies.set("JSESSIONID", jsessionid, domain=".fantrax.com")
        self._client = httpx.Client(
            timeout=60,
            follow_redirects=True,
            cookies=cookies,
        )
        self._logged_in = bool(jsessionid)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FantraxAuthAPI:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def is_logged_in(self) -> bool:
        return self._logged_in

    # ── Internal API helper ──────────────────────────────────────────

    def _call(self, method: str, extra_data: dict | None = None) -> dict:
        """Call a /fxpa/req method.

        All values in extra_data must be strings — the Fantrax internal API
        expects string representations (e.g., "True" not true, "1" not 1).
        """
        msg_data = {"leagueId": self.league_id}
        if extra_data:
            for k, v in extra_data.items():
                if v is not None:
                    msg_data[k] = str(v)

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
            raise RuntimeError(f"Fantrax API error in {method}: {responses[0]['error']}")
        return responses[0].get("data", {})

    # ── Player Stats & Scoring ───────────────────────────────────────

    def get_live_scoring(
        self,
        period: str | None = None,
        scoring_date: str | None = None,
    ) -> dict:
        """Get detailed player stats and scoring.

        Parameters match the known-working FantraxAPI library exactly.
        """
        data: dict = {
            "newView": "True",
            "period": period or "1",
            "playerViewType": "1",
            "sppId": "-1",
            "viewType": "1",
        }
        if scoring_date:
            data["date"] = scoring_date
        return self._call("getLiveScoringStats", data)

    def get_team_roster_info(
        self,
        team_id: str | None = None,
        period: str | None = None,
        view: str = "STATS",
    ) -> dict:
        """Get detailed roster with scoring data for a specific team.

        view options: "STATS", "GAMES_PER_POS", "SCHEDULE_FULL"
        """
        data: dict = {"view": view}
        if team_id:
            data["teamId"] = team_id
        if period is not None:
            data["period"] = period
            data["scoringPeriod"] = period
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
        data: dict = {
            "newView": "True",
            "period": period or "1",
            "playerViewType": "1",
            "sppId": "-1",
            "viewType": "1",
        }
        return self._call("getLiveScoringStats", data)

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
