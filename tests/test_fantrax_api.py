"""Tests for the Fantrax API client using mocked HTTP responses."""

import httpx
import pytest

from fantrax_weekly.fantrax_api import BASE_URL, FantraxAPI


def _mock_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code=status_code, json=json_data)


@pytest.fixture
def api():
    client = FantraxAPI(user_secret_id="test_secret", league_id="test_league")
    yield client
    client.close()


class TestFantraxAPIConstruction:
    def test_init_stores_config(self, api: FantraxAPI):
        assert api.user_secret_id == "test_secret"
        assert api.league_id == "test_league"

    def test_context_manager(self):
        with FantraxAPI("s", "l") as api:
            assert api.user_secret_id == "s"
        # Should not raise after close


class TestGetPlayerIds:
    def test_sends_correct_request(self, api: FantraxAPI, httpx_mock):
        httpx_mock.add_response(
            url=f"{BASE_URL}/getPlayerIds?sport=MLB",
            json={"players": {"id1": "Player One"}},
        )
        result = api.get_player_ids()
        assert result == {"players": {"id1": "Player One"}}

    def test_custom_sport(self, api: FantraxAPI, httpx_mock):
        httpx_mock.add_response(
            url=f"{BASE_URL}/getPlayerIds?sport=NFL",
            json={"players": {}},
        )
        result = api.get_player_ids(sport="NFL")
        assert result == {"players": {}}


class TestGetAdp:
    def test_minimal_request(self, api: FantraxAPI, httpx_mock):
        httpx_mock.add_response(url=f"{BASE_URL}/getAdp", json={"rows": []})
        result = api.get_adp()
        assert result == {"rows": []}
        request = httpx_mock.get_request()
        assert request.method == "POST"

    def test_with_all_params(self, api: FantraxAPI, httpx_mock):
        httpx_mock.add_response(url=f"{BASE_URL}/getAdp", json={"rows": [{"name": "Ohtani"}]})
        result = api.get_adp(
            sport="MLB",
            position="SP",
            start=1,
            limit=5,
            order="NAME",
            show_all_positions=True,
        )
        assert result["rows"][0]["name"] == "Ohtani"
        import json

        body = json.loads(httpx_mock.get_request().content)
        assert body["sport"] == "MLB"
        assert body["position"] == "SP"
        assert body["start"] == 1
        assert body["limit"] == 5
        assert body["order"] == "NAME"
        assert body["showAllPositions"] == "true"


class TestLeagueEndpoints:
    def test_get_leagues(self, api: FantraxAPI, httpx_mock):
        httpx_mock.add_response(
            url=f"{BASE_URL}/getLeagues?userSecretId=test_secret",
            json={"leagues": [{"name": "My League"}]},
        )
        result = api.get_leagues()
        assert len(result["leagues"]) == 1

    def test_get_league_info(self, api: FantraxAPI, httpx_mock):
        httpx_mock.add_response(
            url=f"{BASE_URL}/getLeagueInfo?leagueId=test_league",
            json={"teams": [], "matchups": []},
        )
        result = api.get_league_info()
        assert "teams" in result

    def test_get_standings(self, api: FantraxAPI, httpx_mock):
        httpx_mock.add_response(
            url=f"{BASE_URL}/getStandings?leagueId=test_league",
            json={"standings": [{"rank": 1, "team": "Champs"}]},
        )
        result = api.get_standings()
        assert result["standings"][0]["rank"] == 1

    def test_get_team_rosters_default_period(self, api: FantraxAPI, httpx_mock):
        httpx_mock.add_response(
            url=f"{BASE_URL}/getTeamRosters?leagueId=test_league",
            json={"rosters": []},
        )
        result = api.get_team_rosters()
        assert result == {"rosters": []}

    def test_get_team_rosters_specific_period(self, api: FantraxAPI, httpx_mock):
        httpx_mock.add_response(
            url=f"{BASE_URL}/getTeamRosters?leagueId=test_league&period=6",
            json={"rosters": [{"team": "A"}]},
        )
        result = api.get_team_rosters(period=6)
        assert len(result["rosters"]) == 1

    def test_get_draft_picks(self, api: FantraxAPI, httpx_mock):
        httpx_mock.add_response(
            url=f"{BASE_URL}/getDraftPicks?leagueId=test_league",
            json={"picks": []},
        )
        result = api.get_draft_picks()
        assert "picks" in result

    def test_get_draft_results(self, api: FantraxAPI, httpx_mock):
        httpx_mock.add_response(
            url=f"{BASE_URL}/getDraftResults?leagueId=test_league",
            json={"results": []},
        )
        result = api.get_draft_results()
        assert "results" in result


class TestErrorHandling:
    def test_http_error_raises(self, api: FantraxAPI, httpx_mock):
        httpx_mock.add_response(
            url=f"{BASE_URL}/getStandings?leagueId=test_league",
            status_code=500,
            json={"error": "server error"},
        )
        with pytest.raises(httpx.HTTPStatusError):
            api.get_standings()

    def test_404_raises(self, api: FantraxAPI, httpx_mock):
        httpx_mock.add_response(
            url=f"{BASE_URL}/getLeagueInfo?leagueId=test_league",
            status_code=404,
            json={"error": "not found"},
        )
        with pytest.raises(httpx.HTTPStatusError):
            api.get_league_info()
