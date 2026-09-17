EVE_CLIENT_ID = "c5f7fdd82b54425887cebb5ea0d5e5a2"

EVE_CALLBACK_URL = "http://localhost:8080/callback"
EVE_AUTH_URL = "https://login.eveonline.com/v2/oauth/authorize"
EVE_TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"
EVE_SCOPES = "esi-location.read_location.v1"

ESI_BASE = "https://esi.evetech.net/latest"

LOCATION_POLL_INTERVAL = 5      # seconds between location checks
KILLS_POLL_INTERVAL = 30        # seconds between kills/jumps refresh

import os as _os
TOKEN_FILE = _os.path.join(
    _os.environ.get("APPDATA", _os.path.expanduser("~")),
    "GateScout", "tokens.json"
)
