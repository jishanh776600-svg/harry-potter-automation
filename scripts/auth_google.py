"""
Google OAuth Authentication Script — Harry Potter Automation
Account: jishanh760@gmail.com (ISOLATED — NOT AL AMR)

This script:
  1. Runs Google OAuth 2.0 flow via browser (YouTube + Drive scopes)
  2. Saves token ONLY to: credentials/hp_token.json (gitignored)
  3. Verifies the authenticated Google account email
  4. Retrieves the authenticated YouTube channel (channel ID + name)
  5. Runs a CHANNEL SAFETY GATE: if channel does not match HP_YOUTUBE_CHANNEL_ID
     from .env, publishing remains disabled and a clear warning is printed.
  6. Updates .env with verified channel ID and name.
  7. NEVER touches AL AMR credentials or Drive.
  8. NEVER enables uploads/publishing — that is the launch step only.

Usage:
    python scripts/auth_google.py

    User must authorize jishanh760@gmail.com when the browser opens.
    If Google shows account chooser, select: jishanh760@gmail.com
"""
import os
import sys
import json
import logging
from pathlib import Path

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv, set_key
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HP_AUTH")

# ==============================================================================
# PATHS — ALL ISOLATED TO HARRY POTTER PROJECT
# ==============================================================================
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
TOKEN_PATH = CREDENTIALS_DIR / "hp_token.json"
CLIENT_SECRETS_PATH = CREDENTIALS_DIR / "hp_client_secret.json"
ENV_FILE = PROJECT_ROOT / ".env"

EXPECTED_ACCOUNT = "jishanh760@gmail.com"
EXPECTED_CHANNEL_ID = os.getenv("HP_YOUTUBE_CHANNEL_ID", "")

# OAuth scopes required
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",      # Read channel identity
    "https://www.googleapis.com/auth/drive",                  # Full Drive access for vault
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]


def check_dependencies():
    missing = []
    try:
        import google.oauth2.credentials  # noqa: F401
    except ImportError:
        missing.append("google-auth")
    try:
        import google_auth_oauthlib.flow  # noqa: F401
    except ImportError:
        missing.append("google-auth-oauthlib")
    try:
        from googleapiclient.discovery import build  # noqa: F401
    except ImportError:
        missing.append("google-api-python-client")
    if missing:
        print(f"\n[ERROR] Missing required packages: {', '.join(missing)}")
        print("Install with:  pip install google-auth google-auth-oauthlib google-api-python-client")
        sys.exit(1)


def run_oauth_flow() -> object:
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRETS_PATH.exists():
        print(f"\n{'=' * 70}")
        print("HARRY POTTER OAUTH SETUP — USER ACTION REQUIRED")
        print(f"{'=' * 70}")
        print()
        print("You need to supply the Google OAuth client secret file for:")
        print(f"  Account: {EXPECTED_ACCOUNT}")
        print()
        print("STEPS:")
        print("  1. Go to: https://console.cloud.google.com/")
        print("  2. Select your Harry Potter project (under jishanh760@gmail.com)")
        print("  3. APIs & Services > Credentials > Create OAuth 2.0 Client ID")
        print("     - Application type: Desktop App")
        print("  4. Download the JSON file.")
        print(f"  5. Rename it to: hp_client_secret.json")
        print(f"  6. Place it at:  {CLIENT_SECRETS_PATH}")
        print()
        print("Then re-run:  python scripts/auth_google.py")
        print()
        print("IMPORTANT: Use the jishanh760@gmail.com Google Cloud project.")
        print("Do NOT use the AL AMR Google Cloud project.")
        sys.exit(0)

    logger.info(f"Starting OAuth flow for Harry Potter account ({EXPECTED_ACCOUNT})...")
    logger.info("A browser window will open. Sign in with: jishanh760@gmail.com")
    logger.info("If Google shows an account chooser, select: jishanh760@gmail.com")

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_PATH), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")

    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())

    logger.info(f"Token saved to: {TOKEN_PATH}")
    return creds


def get_authenticated_email(creds) -> str:
    from googleapiclient.discovery import build
    try:
        oauth2 = build("oauth2", "v2", credentials=creds)
        info = oauth2.userinfo().get().execute()
        return info.get("email", "")
    except Exception as e:
        logger.warning(f"Could not retrieve email: {e}")
        return ""


def get_youtube_channel(creds) -> dict:
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
            "description": ch.get("snippet", {}).get("description", "")[:100],
        }
    except Exception as e:
        logger.error(f"Could not retrieve YouTube channel: {e}")
        return {}


def channel_safety_gate(channel: dict) -> bool:
    """
    Hard safety gate. Returns True only if:
    - A channel was found for the authenticated account
    - The channel ID matches HP_YOUTUBE_CHANNEL_ID from .env (if set)
    """
    if not channel or not channel.get("id"):
        logger.warning("[SAFETY GATE] FAIL — No YouTube channel found for authenticated account.")
        logger.warning("  The account may not have a YouTube channel yet.")
        logger.warning("  Create a YouTube channel at: https://studio.youtube.com/")
        logger.warning("  Publishing remains DISABLED.")
        return False

    channel_id = channel["id"]
    channel_name = channel["title"]

    print()
    print("=" * 70)
    print("AUTHENTICATED YOUTUBE CHANNEL")
    print("=" * 70)
    print(f"  Channel ID:    {channel_id}")
    print(f"  Channel Name:  {channel_name}")
    print()

    if EXPECTED_CHANNEL_ID and channel_id != EXPECTED_CHANNEL_ID:
        print("[SAFETY GATE] FAIL — Authenticated channel does NOT match expected Harry Potter channel!")
        print(f"  Expected:     {EXPECTED_CHANNEL_ID}")
        print(f"  Got:          {channel_id}")
        print()
        print("ACTION REQUIRED:")
        print(f"  1. Ensure you authorized jishanh760@gmail.com (not another account).")
        print(f"  2. If the Harry Potter channel is under a different YouTube channel ID,")
        print(f"     update HP_YOUTUBE_CHANNEL_ID in .env manually.")
        print()
        print("  Publishing remains DISABLED.")
        return False

    if not EXPECTED_CHANNEL_ID:
        print("[SAFETY GATE] INFO — HP_YOUTUBE_CHANNEL_ID not yet set in .env.")
        print(f"  Detected channel: {channel_id} ({channel_name})")
        print()
        print("  Writing discovered channel to .env...")
        set_key(str(ENV_FILE), "HP_YOUTUBE_CHANNEL_ID", channel_id)
        set_key(str(ENV_FILE), "HP_YOUTUBE_CHANNEL_NAME", channel_name)
        print(f"  HP_YOUTUBE_CHANNEL_ID={channel_id}")
        print(f"  HP_YOUTUBE_CHANNEL_NAME={channel_name}")
        print()
        print("  IMPORTANT: Confirm this is the correct Harry Potter channel before launch.")
        print("  Publishing remains DISABLED until the launch step.")
        return True

    print(f"[SAFETY GATE] PASS — Authenticated channel matches expected Harry Potter channel.")
    return True


def main():
    print()
    print("=" * 70)
    print("HARRY POTTER AUTOMATION — GOOGLE OAUTH SETUP")
    print("Account: jishanh760@gmail.com  |  ISOLATED FROM AL AMR")
    print("=" * 70)
    print()
    print("SAFETY CONFIRMATION:")
    print("  - This script will ONLY authorize jishanh760@gmail.com")
    print("  - Token is stored ONLY in: credentials/hp_token.json (gitignored)")
    print("  - AL AMR credentials are NOT touched")
    print("  - AL AMR Drive is NOT accessed")
    print("  - AL AMR YouTube channel is NOT accessed")
    print("  - Uploads/publishing remain DISABLED after this step")
    print()

    check_dependencies()

    # Run OAuth flow
    creds = run_oauth_flow()

    # Verify authenticated email
    email = get_authenticated_email(creds)
    print()
    print(f"Authenticated Google Account: {email}")

    if email and email.lower() != EXPECTED_ACCOUNT.lower():
        print()
        print(f"[WARNING] Authenticated account ({email}) does NOT match expected Harry Potter account ({EXPECTED_ACCOUNT}).")
        print("  You may have authorized the wrong Google account.")
        print("  Delete credentials/hp_token.json and re-run to authorize the correct account.")
        print("  Publishing remains DISABLED.")
        return

    # Retrieve YouTube channel
    print()
    print("Retrieving YouTube channel identity...")
    channel = get_youtube_channel(creds)

    # Run channel safety gate
    gate_passed = channel_safety_gate(channel)

    # Final status report
    print()
    print("=" * 70)
    print("AUTHENTICATION COMPLETE — STEP 5 STATUS REPORT")
    print("=" * 70)
    print(f"  Google Account:        {email or 'Unknown'}")
    print(f"  Token Path:            {TOKEN_PATH}")
    print(f"  Client Secrets Path:   {CLIENT_SECRETS_PATH}")
    print(f"  Channel ID:            {channel.get('id', 'NOT FOUND')}")
    print(f"  Channel Name:          {channel.get('title', 'NOT FOUND')}")
    print(f"  Channel Safety Gate:   {'PASS' if gate_passed else 'FAIL — publishing blocked'}")
    print(f"  Publishing Enabled:    FALSE (requires explicit launch step)")
    print(f"  AL AMR Credentials:    NOT USED")
    print(f"  AL AMR Drive:          NOT ACCESSED")
    print(f"  AL AMR YouTube:        NOT ACCESSED")
    print()
    print("Next: Verify the channel identity above is the correct Harry Potter channel.")
    print("Publishing will remain disabled until the launch step is explicitly authorized.")
    print("=" * 70)


if __name__ == "__main__":
    main()
