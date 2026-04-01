"""Debug endpoint to test authenticated API calls and see raw responses."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from http.server import BaseHTTPRequestHandler

from fantrax_weekly.fantrax_auth import FantraxAuthAPI


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            league_id = os.environ.get("FANTRAX_LEAGUE_ID", "")
            username = os.environ.get("FANTRAX_USERNAME", "")
            password = os.environ.get("FANTRAX_PASSWORD", "")

            report = {
                "credentials_present": {
                    "league_id": bool(league_id),
                    "username": bool(username),
                    "password": bool(password),
                },
                "login_result": None,
                "cookies_after_login": [],
                "test_calls": {},
            }

            api = FantraxAuthAPI(league_id, username, password)
            try:
                login_ok = api.login()
                report["login_result"] = login_ok
                report["cookies_after_login"] = [
                    {"name": c.name, "domain": c.domain}
                    for c in api._client.cookies.jar
                ]

                if login_ok:
                    # Test getLiveScoringStats with correct params
                    report["test_calls"]["getLiveScoringStats"] = api.debug_call(
                        "getLiveScoringStats",
                        {
                            "newView": "True",
                            "period": "1",
                            "playerViewType": "1",
                            "sppId": "-1",
                            "viewType": "1",
                        },
                    )

                    # Test getTransactionDetailsHistory
                    report["test_calls"]["getTransactionDetailsHistory"] = api.debug_call(
                        "getTransactionDetailsHistory",
                        {"maxResultsPerPage": "20"},
                    )

                    # Test getStandings
                    report["test_calls"]["getStandings"] = api.debug_call(
                        "getStandings",
                        {"view": "STANDINGS"},
                    )
            finally:
                api.close()

            # Truncate large responses for readability
            output = json.dumps(report, indent=2, default=str)
            if len(output) > 500000:
                output = output[:500000] + "\n... (truncated)"

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(output.encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e), "type": type(e).__name__}).encode())
