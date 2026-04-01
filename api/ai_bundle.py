"""Endpoint that collects ALL league data and returns it as one AI-ready file."""

import json
import os
import sys
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from http.server import BaseHTTPRequestHandler

from fantrax_weekly.collector import bundle_to_text, collect_full_bundle
from fantrax_weekly.fantrax_api import FantraxAPI
from fantrax_weekly.fantrax_auth import FantraxAuthAPI


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            period = int(qs["period"][0]) if "period" in qs else None
            fmt = qs.get("format", ["text"])[0]  # "text" or "json"

            user_secret = os.environ.get("FANTRAX_USER_SECRET_ID", "")
            league_id = os.environ.get("FANTRAX_LEAGUE_ID", "")
            username = os.environ.get("FANTRAX_USERNAME", "")
            password = os.environ.get("FANTRAX_PASSWORD", "")

            # Public API (always available)
            public_api = FantraxAPI(user_secret, league_id)

            # Authenticated API (optional, for rich data)
            auth_api = None
            auth_status = "skipped — no FANTRAX_USERNAME/FANTRAX_PASSWORD set"
            if username and password:
                auth_api = FantraxAuthAPI(league_id, username, password)
                try:
                    if auth_api.login():
                        auth_status = "login successful"
                    else:
                        auth_status = "login failed — check username/password"
                        auth_api = None
                except Exception as login_err:
                    auth_status = f"login error: {login_err}"
                    auth_api = None

            try:
                bundle = collect_full_bundle(public_api, auth_api, period=period)
                bundle["_meta"]["auth_status"] = auth_status
                bundle["_meta"]["credentials_provided"] = bool(username and password)
            finally:
                public_api.close()
                if auth_api:
                    auth_api.close()

            if fmt == "json":
                content = json.dumps(bundle, indent=2, default=str).encode()
                content_type = "application/json"
                filename = "fantrax_weekly_bundle.json"
            else:
                content = bundle_to_text(bundle).encode()
                content_type = "text/plain; charset=utf-8"
                filename = "fantrax_weekly_bundle.txt"

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header(
                "Content-Disposition", f'attachment; filename="{filename}"'
            )
            self.end_headers()
            self.wfile.write(content)

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
