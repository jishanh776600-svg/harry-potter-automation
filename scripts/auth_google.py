"""
Google OAuth Authentication — Harry Potter Automation (Web App Flow)
Account: jishanh760@gmail.com  |  ISOLATED FROM AL AMR

Web Application OAuth flow:
  - Opens browser at localhost:8080 for one-time consent
  - Saves token to credentials/hp_token.json  (gitignored)
  - Extracts refresh_token for GitHub Secrets
  - Verifies authenticated account + YouTube channel identity
  - NEVER enables uploads — that is the launch step only

Usage:
    python scripts/auth_google.py
"""
import os
import sys
import json
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv, set_key
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HP_AUTH")

CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
TOKEN_PATH = CREDENTIALS_DIR / "hp_token.json"
CLIENT_SECRETS_PATH = CREDENTIALS_DIR / "hp_client_secret.json"
ENV_FILE = PROJECT_ROOT / ".env"

EXPECTED_ACCOUNT = "jishanh760@gmail.com"
EXPECTED_CHANNEL_ID = os.getenv("HP_YOUTUBE_CHANNEL_ID", "")
REDIRECT_PORT = 8080

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/drive",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]


def run_oauth_flow():
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRETS_PATH.exists():
        print(f"\n[ERROR] Client secret not found at: {CLIENT_SECRETS_PATH}")
        sys.exit(1)

    # Detect credential type (web vs installed)
    with open(CLIENT_SECRETS_PATH) as f:
        secret_data = json.load(f)
    cred_type = "web" if "web" in secret_data else "installed"

    logger.info(f"Credential type: {cred_type}")
    logger.info(f"Starting OAuth flow — browser will open for jishanh760@gmail.com...")
    logger.info(f"If Google shows account chooser, select: {EXPECTED_ACCOUNT}")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRETS_PATH),
        scopes=SCOPES,
        redirect_uri=f"http://localhost:{REDIRECT_PORT}"
    )

    creds = flow.run_local_server(
        port=REDIRECT_PORT,
        prompt="consent",
        access_type="offline",
    )

    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    token_data = json.loads(creds.to_json())
    with open(TOKEN_PATH, "w") as f:
        json.dump(token_data, f, indent=2)

    logger.info(f"Token saved to: {TOKEN_PATH}")
    return creds, token_data


def get_authenticated_email(creds):
    from googleapiclient.discovery import build
    try:
        oauth2 = build("oauth2", "v2", credentials=creds)
        info = oauth2.userinfo().get().execute()
        return info.get("email", "")
    except Exception as e:
        logger.warning(f"Could not retrieve email: {e}")
        return ""


def get_youtube_channel(creds):
    from googleapiclient.discovery import build
    try:
        youtube = build("youtube", "v3", credentials=creds)
        response = youtube.channels().list(part="snippet,id", mine=True).execute()
        items = response.get("items", [])
        if not items:
            return {}
        ch = items[0]
        return {
            "id": ch.get("id", ""),
            "title": ch.get("snippet", {}).get("title", ""),
        }
    except Exception as e:
        logger.error(f"Could not retrieve YouTube channel: {e}")
        return {}


def main():
    print()
    print("=" * 70)
    print("HARRY POTTER AUTOMATION — GOOGLE OAUTH SETUP (WEB APP FLOW)")
    print(f"Account: {EXPECTED_ACCOUNT}  |  ISOLATED FROM AL AMR")
    print("=" * 70)
    print()

    creds, token_data = run_oauth_flow()

    # Verify email
    email = get_authenticated_email(creds)
    print()
    print(f"Authenticated Google Account: {email}")

    if email and email.lower() != EXPECTED_ACCOUNT.lower():
        print()
        print(f"[WARNING] Wrong account! Got: {email}, expected: {EXPECTED_ACCOUNT}")
        print("Delete credentials/hp_token.json and re-run to fix.")
        return

    # Get YouTube channel
    print("Retrieving YouTube channel...")
    channel = get_youtube_channel(creds)
    channel_id = channel.get("id", "")
    channel_name = channel.get("title", "")

    # Update .env with channel identity
    if channel_id:
        set_key(str(ENV_FILE), "HP_YOUTUBE_CHANNEL_ID", channel_id)
        set_key(str(ENV_FILE), "HP_YOUTUBE_CHANNEL_NAME", channel_name)
        print(f"Written to .env: HP_YOUTUBE_CHANNEL_ID={channel_id}")
        print(f"Written to .env: HP_YOUTUBE_CHANNEL_NAME={channel_name}")

    # Extract refresh token for GitHub Secrets
    refresh_token = token_data.get("refresh_token", "")
    client_id = token_data.get("client_id", "")
    client_secret_val = token_data.get("client_secret", "")

    print()
    print("=" * 70)
    print("STEP 5 - AUTHENTICATION COMPLETE")
    print("=" * 70)
    print(f"  Google Account:        {email or 'Unknown'}")
    print(f"  Token Path:            {TOKEN_PATH}")
    print(f"  Channel ID:            {channel_id or 'NOT FOUND'}")
    print(f"  Channel Name:          {channel_name or 'NOT FOUND'}")
    print(f"  Refresh Token Found:   {'YES' if refresh_token else 'NO'}")
    print(f"  Publishing Enabled:    FALSE (requires launch step)")
    print(f"  AL AMR Credentials:    NOT USED")
    print()

    if refresh_token:
        print("=" * 70)
        print("GITHUB SECRETS — Add these to jishanh760-source/harry-potter-automation")
        print("Settings > Secrets and variables > Actions > New repository secret")
        print("=" * 70)
        print(f"  Secret name:  GOOGLE_REFRESH_TOKEN")
        print(f"  Secret value: {refresh_token}")
        print()
        print(f"  Secret name:  GOOGLE_CLIENT_ID")
        print(f"  Secret value: {client_id}")
        print()
        print(f"  Secret name:  GOOGLE_CLIENT_SECRET")
        print(f"  Secret value: {client_secret_val}")
        print()
        print(f"  Secret name:  HP_YOUTUBE_CHANNEL_ID")
        print(f"  Secret value: {channel_id}")
        print("=" * 70)
    else:
        print("[WARNING] No refresh_token in response.")
        print("This can happen if the account was previously authorized.")
        print("Delete credentials/hp_token.json and re-run with prompt=consent to force refresh token.")

    print()
    print("Publishing remains DISABLED until the launch step.")
    print("AL AMR remains completely untouched.")


if __name__ == "__main__":
    main()
