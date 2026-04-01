"""Fantrax REST API client."""

from __future__ import annotations

import httpx

BASE_URL = "https://www.fantrax.com/fxea/general"


class FantraxAPI:
    """Client for the Fantrax REST API.

    No API key required. User-specific endpoints use a `user_secret_id`
    found on the Fantrax User Profile page.
    """

    def __init__(self, user_secret_id: str, league_id: str) -> None:
        self.user_secret_id = user_secret_id
        self.league_id = league_id
        self._client = httpx.Client(base_url=BASE_URL, timeout=30)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FantraxAPI:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ── Generic request helper ───────────────────────────────────────

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        resp = self._client.get(endpoint, params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint: str, body: dict) -> dict:
        resp = self._client.post(endpoint, json=body)
        resp.raise_for_status()
        return resp.json()

    # ── Public endpoints ─────────────────────────────────────────────

    def get_player_ids(self, sport: str = "MLB") -> dict:
        """Retrieve Fantrax player IDs for a sport."""
        return self._get("/getPlayerIds", {"sport": sport})

    def get_adp(
        self,
        sport: str = "MLB",
        position: str | None = None,
        start: int | None = None,
        limit: int | None = None,
        order: str | None = None,
        show_all_positions: bool = False,
    ) -> dict:
        """Retrieve Average Draft Pick info."""
        body: dict = {"sport": sport}
        if position:
            body["position"] = position
        if start is not None:
            body["start"] = start
        if limit is not None:
            body["limit"] = limit
        if order:
            body["order"] = order
        if show_all_positions:
            body["showAllPositions"] = "true"
        return self._post("/getAdp", body)

    # ── League-specific endpoints ────────────────────────────────────

    def get_leagues(self) -> dict:
        """Retrieve leagues for the configured user."""
        return self._get("/getLeagues", {"userSecretId": self.user_secret_id})

    def get_league_info(self) -> dict:
        """Retrieve full league info (teams, matchups, players, settings)."""
        return self._get("/getLeagueInfo", {"leagueId": self.league_id})

    def get_team_rosters(self, period: int | None = None) -> dict:
        """Retrieve all team rosters for current or specified period."""
        params: dict = {"leagueId": self.league_id}
        if period is not None:
            params["period"] = period
        return self._get("/getTeamRosters", params)

    def get_standings(self) -> dict:
        """Retrieve current league standings."""
        return self._get("/getStandings", {"leagueId": self.league_id})

    def get_draft_picks(self) -> dict:
        """Retrieve future and current draft picks."""
        return self._get("/getDraftPicks", {"leagueId": self.league_id})

    def get_draft_results(self) -> dict:
        """Retrieve draft results (can be called live during a draft)."""
        return self._get("/getDraftResults", {"leagueId": self.league_id})
