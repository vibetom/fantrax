"""Debug endpoint — tests authenticated API with JSESSIONID cookie."""

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
            jsessionid = os.environ.get("FANTRAX_JSESSIONID", "")

            report["credentials_present"] = {
                "league_id": bool(league_id),
                "jsessionid": bool(jsessionid),
                "jsessionid_length": len(jsessionid),
            }

            if not (jsessionid and league_id):
                report["error"] = "Missing FANTRAX_LEAGUE_ID or FANTRAX_JSESSIONID"
                return self._send(200, report)

            report["steps"].append("importing fantrax_auth")
            try:
                from fantrax_weekly.fantrax_auth import FantraxAuthAPI
            except Exception as e:
                report["import_error"] = f"{type(e).__name__}: {e}"
                return self._send(200, report)

            report["steps"].append("creating client with JSESSIONID")
            api = FantraxAuthAPI(league_id, jsessionid=jsessionid)

            try:
                report["steps"].append("calling getLiveScoringStats")
                try:
                    result = api.get_live_scoring(period="1")
                    s = json.dumps(result, default=str)
                    report["live_scoring"] = {
                        "ok": True,
                        "keys": list(result.keys()) if isinstance(result, dict) else str(type(result)),
                        "size_bytes": len(s),
                        "preview": s[:5000],
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
                        "preview": s[:5000],
                    }
                except Exception as e:
                    report["transactions"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

                report["steps"].append("calling getStandings")
                try:
                    result = api.get_rich_standings()
                    s = json.dumps(result, default=str)
                    report["standings"] = {
                        "ok": True,
                        "keys": list(result.keys()) if isinstance(result, dict) else str(type(result)),
                        "size_bytes": len(s),
                        "preview": s[:5000],
                    }
                except Exception as e:
                    report["standings"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

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
