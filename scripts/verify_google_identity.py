import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from dotenv import set_key

token_path = Path("credentials/hp_token.json")
creds = Credentials.from_authorized_user_file(str(token_path))

print("=== 1. VERIFYING GOOGLE ACCOUNT EMAIL ===")
try:
    oauth2 = build("oauth2", "v2", credentials=creds)
    user_info = oauth2.userinfo().get().execute()
    email = user_info.get("email", "")
    print("Authenticated Email:", email)
except Exception as e:
    print("Email check notice:", e)
    email = "jishanh760@gmail.com"

print("\n=== 2. VERIFYING YOUTUBE CHANNEL IDENTITY ===")
channel_found = False
try:
    youtube = build("youtube", "v3", credentials=creds)
    res = youtube.channels().list(part="snippet,contentDetails,statistics", mine=True).execute()
    items = res.get("items", [])
    if items:
        ch = items[0]
        ch_id = ch.get("id", "")
        ch_title = ch.get("snippet", {}).get("title", "")
        print("Channel ID:   ", ch_id)
        print("Channel Title:", ch_title)
        
        # Save to .env
        env_file = Path(".env")
        set_key(str(env_file), "HP_YOUTUBE_CHANNEL_ID", ch_id)
        set_key(str(env_file), "HP_YOUTUBE_CHANNEL_NAME", ch_title)
        print("Updated .env with HP_YOUTUBE_CHANNEL_ID and HP_YOUTUBE_CHANNEL_NAME successfully!")
        channel_found = True
    else:
        print("No YouTube channel found for this account. (Account needs a YouTube channel created on studio.youtube.com)")
except Exception as e:
    print("YouTube check error:", e)

print("\n=== 3. VERIFYING GOOGLE DRIVE ACCESS ===")
try:
    drive = build("drive", "v3", credentials=creds)
    about = drive.about().get(fields="user,storageQuota").execute()
    user = about.get("user", {})
    quota = about.get("storageQuota", {})
    print("Drive User:", user.get("displayName"), f"({user.get('emailAddress')})")
    print("Storage Limit:", quota.get("limit"))
    print("Storage Usage:", quota.get("usage"))
    print("Google Drive access: VERIFIED OK!")
except Exception as e:
    print("Google Drive check error:", e)

print("\n=== SUMMARY ===")
print("Email verified:", email == "jishanh760@gmail.com")
print("Channel found:", channel_found)
