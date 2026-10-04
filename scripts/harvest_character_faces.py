"""
Character Face Harvester & Dataset Ingestion
============================================
Gathers canonical reference faces for all Harry Potter characters:
- Major characters: 50-60 diverse reference faces.
- Secondary / Minor characters: 15-20 diverse reference faces.

Extracts aligned face crops and pre-computes SFace 128-d embeddings
into `data/reference_faces/character_embeddings.npz`.
"""

import os
import re
import sys
import cv2
import time
import requests
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.character_face_engine import (
    CharacterFaceEngine,
    ALL_CHARACTER_TARGETS,
    MAJOR_CHARACTERS,
    SECONDARY_CHARACTERS,
    slugify_name,
    FACES_DIR
)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HarryPotterCharacterEngine/1.0"}
SESSION = requests.Session()


def search_fandom_character_files(character_name: str, max_results: int = 100) -> List[Dict[str, Any]]:
    """
    Queries Harry Potter Fandom MediaWiki search in File namespace (srnamespace=6)
    for exact character image files across multiple search angles.
    """
    clean_name = character_name.strip()
    search_queries = [
        f'"{clean_name}"',
        f'"{clean_name}" portrait',
        f'"{clean_name}" promo',
        f'{clean_name} movie'
    ]
    seen_titles = set()
    all_hits = []

    for sq in search_queries:
        encoded = requests.utils.quote(sq)
        url = f"https://harrypotter.fandom.com/api.php?action=query&list=search&srsearch={encoded}&srnamespace=6&srlimit={max_results}&format=json"
        try:
            r = SESSION.get(url, headers=HEADERS, timeout=8)
            data = r.json()
            hits = data.get("query", {}).get("search", [])
            for h in hits:
                t = h.get("title", "")
                if t and t not in seen_titles:
                    seen_titles.add(t)
                    all_hits.append(h)
        except Exception:
            pass

    return all_hits


def get_image_direct_urls(titles: List[str]) -> Dict[str, str]:
    """
    Batches titles to get direct high-resolution image URLs.
    """
    if not titles:
        return {}

    url_map = {}
    chunk_size = 30
    for i in range(0, len(titles), chunk_size):
        chunk = titles[i:i + chunk_size]
        pipe_titles = "|".join(chunk)
        api_url = f"https://harrypotter.fandom.com/api.php?action=query&titles={requests.utils.quote(pipe_titles)}&prop=imageinfo&iiprop=url|dimensions&format=json"
        try:
            r = SESSION.get(api_url, headers=HEADERS, timeout=10)
            pages = r.json().get("query", {}).get("pages", {})
            for pid, p in pages.items():
                title = p.get("title", "")
                infos = p.get("imageinfo", [])
                if infos and infos[0].get("url"):
                    raw_url = infos[0]["url"]
                    # Strip revision query if present
                    clean_u = raw_url.split("/revision/")[0]
                    url_map[title] = clean_u
        except Exception as e:
            print(f"Error resolving chunk URLs: {e}")

    return url_map


def harvest_faces_for_character(
    char_name: str,
    target_count: int,
    engine: CharacterFaceEngine
) -> int:
    """
    Harvests up to target_count distinct face crops for a single character.
    """
    slug = slugify_name(char_name)
    char_dir = FACES_DIR / slug
    char_dir.mkdir(parents=True, exist_ok=True)

    existing_imgs = list(char_dir.glob("face_*.jpg"))
    if len(existing_imgs) >= target_count:
        print(f"[{char_name}] Already satisfied: {len(existing_imgs)}/{target_count} faces.")
        return len(existing_imgs)

    print(f"\n[{char_name}] Target: {target_count} faces (Current: {len(existing_imgs)})...")

    # Search Fandom files
    search_hits = search_fandom_character_files(char_name, max_results=max(60, target_count * 2))
    candidate_titles = []
    first_token = char_name.split()[0].lower()
    last_token = char_name.split()[-1].lower()

    other_major_tokens = set()
    for other_c in MAJOR_CHARACTERS:
        if other_c.lower() != char_name.lower():
            for tok in other_c.lower().split():
                if len(tok) > 3:
                    other_major_tokens.add(tok)

    for hit in search_hits:
        t = hit.get("title", "")
        t_low = t.lower()
        if any(neg in t_low for neg in [
            "vinyl", "lego", "wand", "letter", "book", "card", "ps2", "pc",
            "game", "pop", "funko", "costume", "merchandise", "map", "coin", "trio"
        ]):
            continue
        # Check that this file title is specifically about this character, and doesn't mention another main character
        if (first_token in t_low or last_token in t_low):
            if not any(ot in t_low for ot in other_major_tokens if ot not in (first_token, last_token)):
                candidate_titles.append(t)

    # Resolve direct URLs
    direct_urls = get_image_direct_urls(candidate_titles)
    print(f"[{char_name}] Resolved {len(direct_urls)} candidate image URLs.", flush=True)

    saved_count = len(existing_imgs)
    extracted_embeddings = []

    # Also load existing embeddings if any
    for existing_f in existing_imgs:
        img_e = cv2.imread(str(existing_f))
        if img_e is not None:
            feats = engine.extract_face_embeddings_from_image(img_e)
            if feats:
                extracted_embeddings.append(feats[0])

    # Concurrent download of images
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _fetch_img(item):
        title, url = item
        try:
            r = SESSION.get(url, headers=HEADERS, timeout=5)
            if r.status_code == 200 and len(r.content) >= 5000:
                arr = np.asarray(bytearray(r.content), dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None:
                    return title, img
        except Exception:
            pass
        return None, None

    items = list(direct_urls.items())
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_item = {executor.submit(_fetch_img, it): it for it in items}
        for future in as_completed(future_to_item):
            if saved_count >= target_count:
                break
            try:
                title, img = future.result()
                if img is None:
                    continue

                h, w = img.shape[:2]
                engine.yunet.setInputSize((w, h))
                _, faces = engine.yunet.detect(img)
                if faces is None or len(faces) == 0:
                    continue

                # Strict Solitary Face Check: If image has multiple faces, skip to avoid intruder faces
                if len(faces) > 1:
                    continue

                face = faces[0]
                aligned = engine.sface.alignCrop(img, face)
                feat = engine.sface.feature(aligned)

                # Centroid Self-Consistency Check:
                # If we already have 2+ reference faces, check similarity with running centroid
                if len(extracted_embeddings) >= 2:
                    centroid = np.mean(extracted_embeddings, axis=0).reshape(1, 128)
                    norm_c = centroid / (np.linalg.norm(centroid) + 1e-8)
                    norm_f = feat.reshape(1, 128) / (np.linalg.norm(feat) + 1e-8)
                    sim = float(np.dot(norm_c, norm_f.T)[0][0])
                    if sim < 0.28:  # Intrinsic face mismatch / different actor / false positive
                        continue

                saved_count += 1
                out_file = char_dir / f"face_{saved_count:02d}.jpg"
                cv2.imwrite(str(out_file), aligned)
                extracted_embeddings.append(feat)
                print(f"  + Saved [{saved_count}/{target_count}] from {title[:40]}...", flush=True)

            except Exception as e:
                continue

    if extracted_embeddings:
        all_feats = np.vstack([f.reshape(1, 128) for f in extracted_embeddings])
        engine.embeddings[slug] = all_feats

    return saved_count


def harvest_all_characters(max_chars: Optional[int] = None):
    """
    Iterates through all Harry Potter characters and populates the face dataset.
    """
    engine = CharacterFaceEngine()

    total_characters = list(ALL_CHARACTER_TARGETS.items())
    if max_chars:
        total_characters = total_characters[:max_chars]

    print("=" * 80)
    print(f"HARVESTING HARRY POTTER FACE DATASET ({len(total_characters)} Characters)")
    print("Major Characters Target: 50 | Secondary Target: 20")
    print("=" * 80)

    start_time = time.time()
    for idx, (char_name, target) in enumerate(total_characters, 1):
        try:
            print(f"\nProgress: [{idx}/{len(total_characters)}] {char_name}")
            harvest_faces_for_character(char_name, target, engine)
        except Exception as err:
            print(f"Failed harvesting {char_name}: {err}")

    # Save cache
    engine.save_cached_embeddings()
    elapsed = time.time() - start_time
    print("=" * 80)
    print(f"HARVEST COMPLETE in {elapsed:.1f}s. Total characters indexed: {len(engine.embeddings)}")
    print(f"Embeddings saved to: {FACES_DIR / 'character_embeddings.npz'}")
    print("=" * 80)


if __name__ == "__main__":
    count_arg = int(sys.argv[1]) if len(sys.argv) > 1 else None
    harvest_all_characters(max_chars=count_arg)
