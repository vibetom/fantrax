import json
import os
import sys
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from http.server import BaseHTTPRequestHandler

from fantrax_weekly.collector import collect_weekly_snapshot
from fantrax_weekly.fantrax_api import FantraxAPI


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            period = int(qs["period"][0]) if "period" in qs else None

            with FantraxAPI(
                os.environ["FANTRAX_USER_SECRET_ID"],
                os.environ["FANTRAX_LEAGUE_ID"],
            ) as api:
                data = collect_weekly_snapshot(api, period=period)

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
