"""Obtient le refresh token Google (OAuth 2.0) d'un compte de TEST. À lancer une seule fois en local.

Prérequis : projet Google Cloud, APIs Calendar + Drive activées, identifiants OAuth « Application de bureau ».
Usage : GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... uv run python scripts/google_login.py
Copier ensuite le refresh token affiché dans GOOGLE_REFRESH_TOKEN (secret, jamais dans le code).
"""

import os

from google_auth_oauthlib.flow import InstalledAppFlow

from app.tools.google import SCOPES

config = {"installed": {
    "client_id": os.environ["GOOGLE_CLIENT_ID"],
    "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "redirect_uris": ["http://localhost"],
}}
creds = InstalledAppFlow.from_client_config(config, SCOPES).run_local_server(port=0, prompt="consent", access_type="offline")
print("\nGOOGLE_REFRESH_TOKEN=" + creds.refresh_token)
