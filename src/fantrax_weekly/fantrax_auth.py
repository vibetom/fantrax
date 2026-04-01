"""Authenticated Fantrax API client using the internal /fxpa/req endpoint.

The public API (/fxea/general) doesn't expose player stats, transactions, or
matchup scoring. The internal API that the Fantrax web app uses (/fxpa/req)
has all of this, but requires session cookies from a logged-in browser session.

Authentication uses cookies extracted from the user's browser. The critical
cookies are FX_RM (remember-me token) and JSESSIONID (session). Set them
via FANTRAX_COOKIES env var as "name1=value1; name2=value2" format, or
set individual FANTRAX_FX_RM and/or FANTRAX_JSESSIONID env vars.

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
        fx_rm: str = "",
        jsessionid: str = "",
        raw_cookies: str = "",
    ) -> None:
        self.league_id = league_id
        cookies = httpx.Cookies()

        # Parse raw cookie string (e.g. "FX_RM=abc123; JSESSIONID=xyz789")
        if raw_cookies:
            for part in raw_cookies.split(";"):
                part = part.strip()
                if "=" in part:
                    name, value = part.split("=", 1)
                    cookies.set(name.strip(), value.strip(), domain=".fantrax.com")

        # Individual cookie overrides
        if fx_rm:
            cookies.set("FX_RM", fx_rm, domain=".fantrax.com")
        if jsessionid:
            cookies.set("JSESSIONID", jsessionid, domain=".fantrax.com")

        self._client = httpx.Client(
            timeout=60,
            follow_redirects=True,
            cookies=cookies,
        )
        self._has_cookies = bool(fx_rm or jsessionid or raw_cookies)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FantraxAuthAPI:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def is_logged_in(self) -> bool:
        return self._has_cookies

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

        logger.debug("Calling %s with keys: %s", method, list(msg_data.keys()))

        resp = self._client.post(
            f"{FXPA_URL}?leagueId={self.league_id}",
            json={"msgs": [{"method": method, "data": msg_data}]},
        )
        resp.raise_for_status()
        result = resp.json()

        responses = result.get("responses", [])
        if not responses:
            logger.warning("%s returned no responses", method)
            return {}
        if responses[0].get("error"):
            raise RuntimeError(f"Fantrax API error in {method}: {responses[0]['error']}")

        response_data = responses[0].get("data", {})
        if isinstance(response_data, dict):
            logger.info(
                "%s response: %d top-level keys: %s",
                method,
                len(response_data),
                list(response_data.keys())[:20],
            )
        return response_data

    # ── Player Stats & Scoring ───────────────────────────────────────

    def get_live_scoring(
        self,
        period: str | None = None,
        scoring_date: str | None = None,
        status_or_pos: str | None = None,
        max_results: int = 100,
        page: int = 1,
    ) -> dict:
        """Get detailed player stats and scoring.

        Core parameters match the known-working FantraxAPI library.
        Additional params (maxResultsPerPage, statusOrPos) are needed
        to ensure the response includes actual player rows with stats.
        """
        data: dict = {
            "newView": "True",
            "period": period or "1",
            "playerViewType": "1",
            "sppId": "-1",
            "viewType": "1",
            "maxResultsPerPage": str(max_results),
            "pageNumber": str(page),
            "scoringCategoryType": "5",
            "timeframeTypeCode": "BY_PERIOD",
            "miscDisplayType": "1",
            "adminMode": "False",
        }
        if status_or_pos:
            data["statusOrPos"] = status_or_pos
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
        return self.get_live_scoring(period=period)

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
