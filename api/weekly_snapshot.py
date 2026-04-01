import json
import os
import sys
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            from fantrax_weekly.collector import collect_full_bundle
            from fantrax_weekly.fantrax_api import FantraxAPI
            from fantrax_weekly.fantrax_auth import FantraxAuthAPI

            qs = parse_qs(urlparse(self.path).query)
            period = int(qs["period"][0]) if "period" in qs else None

            user_secret = os.environ.get("FANTRAX_USER_SECRET_ID", "")
            league_id = os.environ.get("FANTRAX_LEAGUE_ID", "")
            fx_rm = os.environ.get("FANTRAX_FX_RM", "")
            jsessionid = os.environ.get("FANTRAX_JSESSIONID", "")

            public_api = FantraxAPI(user_secret, league_id)
            auth_api = None
            if fx_rm or jsessionid:
                auth_api = FantraxAuthAPI(league_id, fx_rm=fx_rm, jsessionid=jsessionid)

            try:
                data = collect_full_bundle(public_api, auth_api, period=period)
            finally:
                public_api.close()
                if auth_api:
                    auth_api.close()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
