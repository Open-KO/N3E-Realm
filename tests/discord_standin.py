"""Discord's OAuth2 API on loopback for the live suites (N3E_DISCORD_API): codes
bound to a PKCE challenge, the client secret and verifier checked at the token
endpoint, and `/users/@me`. tests/discord_login_live.py and
tests/front_end_flow_live.py use it."""
import base64
import hashlib
import http.server
import json
import secrets
import threading
import time
import urllib.parse


def b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class Discord:
    """The OAuth2 stand-in. `authorize` is the browser step: it issues a code for a
    user, bound to the PKCE challenge and redirect URI the client sent."""

    def __init__(self, client_id, secret, redirect):
        self.redirect = redirect
        self.codes = {}
        self.access = {}
        self.issued = []  # every access token handed out, for the log check
        self.delay = 0.0
        self.lock = threading.Lock()
        discord = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def reply(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                time.sleep(discord.delay)
                if self.path != "/api/oauth2/token":
                    return self.reply(404, {"message": "404: Not Found"})
                form = dict(urllib.parse.parse_qsl(self.rfile.read(int(self.headers["Content-Length"])).decode()))
                if form.get("client_id") != client_id or form.get("client_secret") != secret:
                    return self.reply(401, {"error": "invalid_client"})
                with discord.lock:
                    grant = discord.codes.pop(form.get("code"), None)
                if (grant is None or form.get("grant_type") != "authorization_code"
                        or form.get("redirect_uri") != grant["redirect"]
                        or b64url(hashlib.sha256(form.get("code_verifier", "").encode()).digest()) != grant["challenge"]):
                    return self.reply(400, {"error": "invalid_grant", "error_description": 'Invalid "code" in request.'})
                token = "AT" + secrets.token_urlsafe(24)
                with discord.lock:
                    discord.access[token] = grant["user"]
                    discord.issued.append(token)
                self.reply(200, {"access_token": token, "token_type": "Bearer", "expires_in": 604800,
                                 "refresh_token": "RT" + secrets.token_urlsafe(24), "scope": "identify"})

            def do_GET(self):
                time.sleep(discord.delay)
                token = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
                with discord.lock:
                    user = discord.access.get(token)
                if self.path != "/api/users/@me" or user is None:
                    return self.reply(401, {"message": "401: Unauthorized", "code": 0})
                self.reply(200, user)

        self.http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.http.server_address[1]
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def authorize(self, user, challenge, redirect=None):
        redirect = redirect or self.redirect
        code = secrets.token_urlsafe(20)
        with self.lock:
            self.codes[code] = {"user": user, "challenge": challenge, "redirect": redirect}
        return code


def user(snowflake, global_name, username=None):
    return {"id": snowflake, "username": username or global_name.lower(), "global_name": global_name,
            "discriminator": "0", "avatar": None}
