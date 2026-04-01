import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from http.server import BaseHTTPRequestHandler

from fantrax_weekly.fantrax_api import FantraxAPI


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            with FantraxAPI(
                os.environ["FANTRAX_USER_SECRET_ID"],
                os.environ["FANTRAX_LEAGUE_ID"],
            ) as api:
                data = api.get_standings()
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
