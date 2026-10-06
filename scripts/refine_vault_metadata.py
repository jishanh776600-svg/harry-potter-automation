import os
import sys
import glob
import json
import base64
import time
import requests
import sqlite3
from dotenv import load_dotenv
import subprocess

load_dotenv()

DB_PATH = "data/database/franchise_visual_vault.db"
FRAMES_DIR = "data/vault_verification_frames"
CLIPS_DIR = "data/franchise_vault_clips"
NVIDIA_KEY = os.getenv("NVIDIA_API_KEY")

def analyze_frame_with_vision(image_path: str):
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    prompt = (
        "You are an expert Harry Potter cinematic archivist. Analyze this video frame from Harry Potter and the Sorcerer's Stone.\n"
        "Return ONLY a valid JSON object with NO markdown formatting, NO backticks, and NO conversational filler:\n"
        "{\n"
        '  "primary_subject": "Main character, object, or creature",\n'
        '  "characters_present": ["Character name 1"],\n'
        '  "character_expressions": ["Character: expression description"],\n'
        '  "visible_objects_props": ["prop 1", "prop 2"],\n'
        '  "spells_magic_actions": [],\n'
        '  "action_description": "Precise 1-2 sentence description of what is visually happening",\n'
        '  "lore_context": "Canonical context and story significance",\n'
        '  "location_setting": "Exact setting name (e.g. Potions Dungeon, Great Hall, Forbidden Forest)",\n'
        '  "shot_scale": "CLOSE_UP or MEDIUM_SHOT or WIDE_ESTABLISHING or OVER_SHOULDER",\n'
        '  "camera_motion": "STATIC or PAN or TILT or TRACKING",\n'
        '  "lighting_and_mood": "Mood description (e.g. tense, eerie, whimsical, cold)",\n'
        '  "search_tags": ["tag1", "tag2", "tag3", "tag4"]\n'
        "}"
    )

    headers = {
        "Authorization": f"Bearer {NVIDIA_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "meta/llama-3.2-11b-vision-instruct",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                ]
            }
        ],
        "temperature": 0.1,
        "max_tokens": 1024
    }

    resp = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers=headers, json=payload, timeout=45)
    if resp.status_code != 200:
        raise RuntimeError(f"Vision API error {resp.status_code}: {resp.text}")

    content = resp.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return json.loads(content.strip())

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT clip_id, start_seconds, end_seconds, primary_subject FROM franchise_clips WHERE primary_subject LIKE '%Canonical%'")
    fallback_clips = cursor.fetchall()
    print(f"Found {len(fallback_clips)} fallback clips needing Vision AI refinement.")

    for i, (clip_id, start_sec, end_sec, old_subj) in enumerate(fallback_clips, 1):
        frame_file = os.path.join(FRAMES_DIR, f"{clip_id}.jpg")
        alt_frame_file = os.path.join("data/franchise_vault_frames", f"{clip_id}.jpg")
        meta_file = os.path.join(CLIPS_DIR, f"{clip_id}.meta.json")
        mp4_file = os.path.join(CLIPS_DIR, f"{clip_id}.mp4")
        
        target_frame = frame_file if os.path.exists(frame_file) else alt_frame_file
        if not os.path.exists(target_frame) and os.path.exists(mp4_file):
            # Extract center frame
            subprocess.run(["ffmpeg", "-y", "-ss", "0.5", "-i", mp4_file, "-vframes", "1", "-q:v", "2", target_frame], capture_output=True)

        if not os.path.exists(target_frame):
            print(f"[{i}/{len(fallback_clips)}] Frame {target_frame} not found, skipping.")
            continue

        print(f"[{i}/{len(fallback_clips)}] Analyzing {clip_id} ({start_sec}s)...", end=" ", flush=True)
        try:
            meta = analyze_frame_with_vision(target_frame)
            print(f"SUCCESS -> Subject: {meta.get('primary_subject')} | Characters: {meta.get('characters_present')}")

            # Update DB
            cursor.execute("""
                UPDATE franchise_clips SET
                    primary_subject = ?,
                    characters_present = ?,
                    character_expressions = ?,
                    visible_objects_props = ?,
                    spells_magic_actions = ?,
                    action_description = ?,
                    lore_context = ?,
                    location_setting = ?,
                    shot_scale = ?,
                    camera_motion = ?,
                    lighting_and_mood = ?,
                    search_tags = ?
                WHERE clip_id = ?
            """, (
                meta.get("primary_subject", "Scene"),
                json.dumps(meta.get("characters_present", [])),
                json.dumps(meta.get("character_expressions", [])),
                json.dumps(meta.get("visible_objects_props", [])),
                json.dumps(meta.get("spells_magic_actions", [])),
                meta.get("action_description", ""),
                meta.get("lore_context", ""),
                meta.get("location_setting", "Hogwarts"),
                meta.get("shot_scale", "MEDIUM_SHOT"),
                meta.get("camera_motion", "STATIC"),
                meta.get("lighting_and_mood", ""),
                json.dumps(meta.get("search_tags", [])),
                clip_id
            ))

            # Update FTS
            cursor.execute("""
                INSERT OR REPLACE INTO franchise_clips_fts(
                    clip_id, primary_subject, characters_present,
                    visible_objects_props, spells_magic_actions,
                    action_description, lore_context, search_tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                clip_id,
                meta.get("primary_subject", "Scene"),
                json.dumps(meta.get("characters_present", [])),
                json.dumps(meta.get("visible_objects_props", [])),
                json.dumps(meta.get("spells_magic_actions", [])),
                meta.get("action_description", ""),
                meta.get("lore_context", ""),
                json.dumps(meta.get("search_tags", []))
            ))
            conn.commit()

            # Update sidecar json if exists
            if os.path.exists(meta_file):
                with open(meta_file, "r") as mf:
                    existing_data = json.load(mf)
                existing_data.update(meta)
                with open(meta_file, "w") as mf:
                    json.dump(existing_data, mf, indent=2)

        except Exception as e:
            print(f"FAILED: {e}")
        time.sleep(1)

    conn.close()
    print("Metadata refinement complete!")

if __name__ == "__main__":
    main()
