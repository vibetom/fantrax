"""Debug endpoint — lazy imports so Vercel doesn't crash at load time."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        report = {"steps": []}

        try:
            league_id = os.environ.get("FANTRAX_LEAGUE_ID", "")
            username = os.environ.get("FANTRAX_USERNAME", "")
            password = os.environ.get("FANTRAX_PASSWORD", "")

            report["credentials_present"] = {
                "league_id": bool(league_id),
                "username": bool(username),
                "password": bool(password),
            }

            if not (username and password and league_id):
                report["error"] = "Missing one or more credentials in env vars"
                return self._send(200, report)

            # Lazy import to catch import errors
            report["steps"].append("importing fantrax_auth")
            try:
                from fantrax_weekly.fantrax_auth import FantraxAuthAPI
            except Exception as e:
                report["import_error"] = f"{type(e).__name__}: {e}"
                return self._send(200, report)

            report["steps"].append("creating client")
            api = FantraxAuthAPI(league_id, username, password)

            try:
                report["steps"].append("logging in")
                login_ok = api.login()
                report["login_result"] = login_ok
                report["cookies"] = [
                    {"name": c.name, "domain": c.domain}
                    for c in api._client.cookies.jar
                ]

                if login_ok:
                    report["steps"].append("calling getLiveScoringStats")
                    try:
                        result = api.get_live_scoring(period="1")
                        s = json.dumps(result, default=str)
                        report["live_scoring"] = {
                            "ok": True,
                            "keys": list(result.keys()) if isinstance(result, dict) else str(type(result)),
                            "size_bytes": len(s),
                            "preview": s[:3000],
                        }
                    except Exception as e:
                        report["live_scoring"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

                    report["steps"].append("calling getTransactionDetailsHistory")
                    try:
                        result = api.get_transaction_history(max_results=5)
                        s = json.dumps(result, default=str)
                        report["transactions"] = {
                            "ok": True,
                            "keys": list(result.keys()) if isinstance(result, dict) else str(type(result)),
                            "size_bytes": len(s),
                            "preview": s[:3000],
                        }
                    except Exception as e:
                        report["transactions"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

                report["steps"].append("done")
            finally:
                api.close()

            self._send(200, report)

        except Exception as e:
            report["fatal_error"] = f"{type(e).__name__}: {e}"
            self._send(500, report)

    def _send(self, status, data):
        body = json.dumps(data, indent=2, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
