"""
EVE SSO OAuth2 with PKCE. Opens a browser for login, catches the callback
on localhost:8080, exchanges the code for tokens, and saves them to disk.
"""

import hashlib
import base64
import secrets
import json
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
import requests

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import EVE_CLIENT_ID, EVE_CALLBACK_URL, EVE_AUTH_URL, EVE_TOKEN_URL, EVE_SCOPES, TOKEN_FILE


def _pkce_pair():
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


class _CallbackHandler(BaseHTTPRequestHandler):
    auth_code = None
    error = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if "code" in params:
            _CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>GateScout: login successful. You can close this tab.</h2>")
        else:
            _CallbackHandler.error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>Login failed. Check the app and try again.</h2>")

    def log_message(self, *args):
        pass  # suppress console noise


def login():
    """Full OAuth login flow. Returns (character_id, character_name) and saves tokens."""
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)

    params = {
        "response_type": "code",
        "redirect_uri": EVE_CALLBACK_URL,
        "client_id": EVE_CLIENT_ID,
        "scope": EVE_SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = EVE_AUTH_URL + "?" + urlencode(params)

    print("Opening EVE login in your browser...")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", 8080), _CallbackHandler)
    server.timeout = 120
    server.handle_request()

    if _CallbackHandler.error:
        raise RuntimeError(f"EVE SSO error: {_CallbackHandler.error}")
    if not _CallbackHandler.auth_code:
        raise RuntimeError("No auth code received. Did you complete the login?")

    token_data = _exchange_code(_CallbackHandler.auth_code, verifier)
    character_id, character_name = _verify_token(token_data["access_token"])
    token_data["character_id"] = character_id
    token_data["character_name"] = character_name
    token_data["expires_at"] = time.time() + token_data.get("expires_in", 1200) - 60

    _save_tokens(token_data)
    print(f"Logged in as: {character_name}")
    return character_id, character_name


def _exchange_code(code, verifier):
    resp = requests.post(EVE_TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": EVE_CLIENT_ID,
        "code_verifier": verifier,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    resp.raise_for_status()
    return resp.json()


def _verify_token(access_token):
    """Decode the JWT to extract character_id and name without a secret."""
    payload_b64 = access_token.split(".")[1]
    # Add padding if needed
    padding = 4 - len(payload_b64) % 4
    payload_b64 += "=" * (padding % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    sub = payload.get("sub", "")
    character_id = int(sub.replace("CHARACTER:EVE:", ""))
    character_name = payload.get("name", "Unknown")
    return character_id, character_name


def get_access_token():
    """Return a valid access token, refreshing if needed."""
    tokens = _load_tokens()
    if not tokens:
        raise RuntimeError("Not logged in. Run login() first.")

    if time.time() >= tokens.get("expires_at", 0):
        tokens = _refresh(tokens)

    return tokens["access_token"]


def get_saved_character():
    """Return (character_id, character_name) from saved tokens, or None."""
    tokens = _load_tokens()
    if not tokens:
        return None, None
    return tokens.get("character_id"), tokens.get("character_name")


def _refresh(tokens):
    resp = requests.post(EVE_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": EVE_CLIENT_ID,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    resp.raise_for_status()
    new_tokens = resp.json()
    new_tokens["character_id"] = tokens["character_id"]
    new_tokens["character_name"] = tokens["character_name"]
    new_tokens["expires_at"] = time.time() + new_tokens.get("expires_in", 1200) - 60
    if "refresh_token" not in new_tokens:
        new_tokens["refresh_token"] = tokens["refresh_token"]
    _save_tokens(new_tokens)
    return new_tokens


def _save_tokens(data):
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)


def _load_tokens():
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
