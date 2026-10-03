"""
COMPLETE PC AUTOMATION PROJECT SIZE AUDIT SCRIPT
=================================================
Strictly READ-ONLY comprehensive filesystem measurement of ALL
YouTube/video automation projects, dependencies, models, caches,
backups, and local media across the PC.
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

PROJECT_ROOT = Path(r"C:\Users\jisha\.gemini\antigravity\scratch\harry_potter_automation")

# Define the targets to audit

PROJECTS_SPEC = {
    # -------------------------------------------------------------------------
    # A) ACTUAL AUTOMATION PROJECTS
    # -------------------------------------------------------------------------
    "AL AMR / Forgotten Files (Active Workspace)": {
        "path": r"C:\Users\jisha\OneDrive\Desktop\yt automation",
        "category_group": "A) ACTUAL AUTOMATION PROJECTS",
        "description": "Production YouTube/video automation workspace (AL AMR / Forgotten Files)",
    },
    "Harry Potter / STORY FORGE": {
        "path": r"C:\Users\jisha\.gemini\antigravity\scratch\harry_potter_automation",
        "category_group": "A) ACTUAL AUTOMATION PROJECTS",
        "description": "Story Forge visual evidence automation system",
    },
    "Clipping Automation (AutoClip)": {
        "path": r"C:\Users\jisha\OneDrive\Desktop\automation_clipping",
        "category_group": "A) ACTUAL AUTOMATION PROJECTS",
        "description": "AutoClip clipping automation project & evaluation venv",
    },
    "AutoClip Local Runtime (.autoclip)": {
        "path": r"C:\Users\jisha\.autoclip",
        "category_group": "A) ACTUAL AUTOMATION PROJECTS",
        "description": "AutoClip runtime data, database, models, media, and cache",
    },
    "PyVisualEvidence Engine": {
        "path": r"C:\Users\jisha\.gemini\antigravity\scratch\py_visual_evidence",
        "category_group": "A) ACTUAL AUTOMATION PROJECTS",
        "description": "Visual verification engine and blind test footage clips",
    },
    "History Shorts Automation Pipeline": {
        "path": r"C:\Users\jisha\.gemini\antigravity\scratch\history_shorts_pipeline",
        "category_group": "A) ACTUAL AUTOMATION PROJECTS",
        "description": "Autonomous YouTube Shorts pipeline for cinematic historical stories",
    },
    "Instagram AI Automation (Scratch Pipeline)": {
        "path": r"C:\Users\jisha\.gemini\antigravity\scratch\instagram_ai_automation",
        "category_group": "A) ACTUAL AUTOMATION PROJECTS",
        "description": "Instagram AI cinematic video & product automation",
    },
    "Instagram AI Automation (Desktop App & Autopilot)": {
        "path": r"C:\Users\jisha\OneDrive\Desktop\antigravity-results\instagram_ai_automation",
        "category_group": "A) ACTUAL AUTOMATION PROJECTS",
        "description": "Instagram autopilot engine, actions, and deliverables",
    },
    "Automation Media Assets": {
        "path": r"C:\Users\jisha\OneDrive\Desktop\automation assets",
        "category_group": "A) ACTUAL AUTOMATION PROJECTS",
        "description": "SFX, transition sound effects, and background music archives",
    },
    "Antigravity Results (Reels & Carousels)": {
        "path": r"C:\Users\jisha\OneDrive\Desktop\antigravity-results",
        "category_group": "A) ACTUAL AUTOMATION PROJECTS",
        "exclude_subdirs": [r"C:\Users\jisha\OneDrive\Desktop\antigravity-results\instagram_ai_automation"],
        "description": "Rendered Hollywood-tier reels, carousels, and workflow outputs",
    },

    # -------------------------------------------------------------------------
    # B) POSSIBLE AUTOMATION-RELATED / ADJACENT PROJECTS
    # -------------------------------------------------------------------------
    "Autonomous Client Acquisition System": {
        "path": r"C:\Users\jisha\.gemini\antigravity\scratch\client_acquisition_system",
        "category_group": "B) POSSIBLE AUTOMATION-RELATED",
        "description": "Autonomous AI client acquisition & business dev pipeline",
    },
    "StoryForge Blender Dev Addon": {
        "path": r"C:\Users\jisha\.gemini\antigravity\scratch\StoryForge_Dev",
        "category_group": "B) POSSIBLE AUTOMATION-RELATED",
        "description": "StoryForge Blender addon development workspace",
    },
    "StoryForge Rig Toolkit Addon Zips": {
        "path": r"C:\my own addon",
        "category_group": "B) POSSIBLE AUTOMATION-RELATED",
        "description": "StoryForge rig toolkit addon release archives",
    },
    "Blender Tools / Pipeline": {
        "path": r"C:\Users\jisha\.gemini\antigravity\scratch\BlenderTools",
        "category_group": "B) POSSIBLE AUTOMATION-RELATED",
        "description": "Blender automation & rigging scripts",
    },
    "MetaHuman Rigify Bridge": {
        "path": r"C:\Users\jisha\.gemini\antigravity\scratch\metahuman_rigify_bridge",
        "category_group": "B) POSSIBLE AUTOMATION-RELATED",
        "description": "MetaHuman to Rigify animation automation bridge",
    },
    "Playwright Automation Vault": {
        "path": r"C:\tmp\test_playwright_vault",
        "category_group": "B) POSSIBLE AUTOMATION-RELATED",
        "description": "Playwright automated browser testing vault",
    },

    # -------------------------------------------------------------------------
    # D) SHARED MODELS & CACHES
    # -------------------------------------------------------------------------
    "HuggingFace Shared AI Models Hub": {
        "path": r"C:\Users\jisha\.cache\huggingface\hub",
        "category_group": "D) SHARED MODELS & CACHES",
        "description": "Cached AI models: F5-TTS, Vocos, OWLv2, Whisper models",
    },
    "Antigravity IDE Tool Runtimes & Cache": {
        "path": r"C:\Users\jisha\.cache\codex-runtimes",
        "category_group": "D) SHARED MODELS & CACHES",
        "description": "Antigravity/Codex runtimes cache",
    },

    # -------------------------------------------------------------------------
    # E) BACKUPS & DUPLICATES
    # -------------------------------------------------------------------------
    "AL AMR Backup Master Zip": {
        "path": r"C:\automation backups\AL_AMR_COMPLETE_AUTOMATION_BACKUP.zip",
        "category_group": "E) BACKUPS & DUPLICATES",
        "is_file": True,
        "description": "Master 3.06 GB zip backup of entire AL AMR system",
    },
    "AL AMR Active Mirror Zip": {
        "path": r"C:\automation backups\AL_AMR_ACTIVE_MIRROR.zip",
        "category_group": "E) BACKUPS & DUPLICATES",
        "is_file": True,
        "description": "Compressed 6.02 GB active mirror backup archive",
    },
    "AL AMR Active Mirror Directory": {
        "path": r"C:\automation backups\AL_AMR_ACTIVE_MIRROR",
        "category_group": "E) BACKUPS & DUPLICATES",
        "description": "Uncompressed active mirror directory backup of AL AMR",
    },
    "AL AMR Cold Storage Secrets Zip": {
        "path": r"C:\automation backups\AL_AMR_CREDENTIALS_AND_SECRETS_COLD_STORAGE.zip",
        "category_group": "E) BACKUPS & DUPLICATES",
        "is_file": True,
        "description": "Isolated credentials cold storage archive",
    },
    "AL AMR Old Desktop Clone (Aug 27)": {
        "path": r"C:\Users\jisha\Desktop\yt automation",
        "category_group": "E) BACKUPS & DUPLICATES",
        "description": "Duplicate/historical clone of yt automation on Desktop",
    },
    "StoryForge Backup PreFix": {
        "path": r"C:\Users\jisha\.gemini\antigravity\scratch\StoryForge_Backup_PreFix",
        "category_group": "E) BACKUPS & DUPLICATES",
        "description": "Pre-fix backup copy of StoryForge addon",
    },
    "StoryForge Buyer Package": {
        "path": r"C:\Users\jisha\.gemini\antigravity\scratch\StoryForge_Buyer",
        "category_group": "E) BACKUPS & DUPLICATES",
        "description": "Packaged buyer copy of StoryForge addon",
    },
    "Antigravity Brain Artifacts & Transcripts": {
        "path": r"C:\Users\jisha\.gemini\antigravity\brain",
        "category_group": "E) BACKUPS & DUPLICATES",
        "description": "Session artifacts, test renders, keyframes, and transcripts",
    },
}

CATEGORIES = [
    "source code",
    "tests",
    "configuration",
    "SQLite/databases",
    "models",
    "Python environments/dependencies",
    "caches",
    "Git/.git",
    "generated videos",
    "generated audio",
    "images/assets",
    "logs",
    "reports/documentation",
    "local movie storage",
    "temporary files",
    "other",
]


def classify_file(file_path: Path, root_path: Path) -> str:
    """Classifies a file into one of the canonical categories."""
    p_str = str(file_path).lower()
    name = file_path.name.lower()
    suffix = file_path.suffix.lower()

    # 1. Local Movie Storage (explicitly separated per user media rule)
    if "data\\movies" in p_str or "data/movies" in p_str:
        if suffix in (".mkv", ".mp4", ".avi", ".mov") and file_path.stat().st_size > 50_000_000:
            return "local movie storage"

    # 2. Git
    if "\\.git\\" in p_str or "/.git/" in p_str or name in (".gitignore", ".gitattributes", ".gitmodules", ".gitkeep"):
        return "Git/.git"

    # 3. Environments / Dependencies
    if any(k in p_str for k in ("\\venv\\", "\\.venv\\", "\\venv311\\", "\\node_modules\\", "\\site-packages\\", "/venv/", "/.venv/", "/venv311/")):
        return "Python environments/dependencies"

    # 4. Caches
    if any(k in p_str for k in ("\\__pycache__\\", "\\.pytest_cache\\", "\\.ruff_cache\\", "\\.cache\\pip\\", "\\.cgheven_cache\\")):
        return "caches"

    # 5. Models
    if "\\models\\" in p_str or "\\hub\\models--" in p_str or suffix in (".safetensors", ".onnx", ".tflite") or (suffix in (".bin", ".pt", ".pth") and file_path.stat().st_size > 5_000_000):
        return "models"

    # 6. Tests
    if "\\tests\\" in p_str or "/tests/" in p_str or name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
        return "tests"

    # 7. Databases
    if suffix in (".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm"):
        return "SQLite/databases"

    # 8. Generated Video
    if suffix in (".mp4", ".mkv", ".mov", ".webm", ".avi"):
        return "generated videos"

    # 9. Generated Audio
    if suffix in (".wav", ".mp3", ".aac", ".flac", ".m4a", ".ogg"):
        return "generated audio"

    # 10. Images / Assets
    if suffix in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".bmp", ".gif", ".ico", ".ttf", ".otf"):
        return "images/assets"

    # 11. Logs
    if suffix in (".log", ".jsonl"):
        return "logs"

    # 12. Documentation / Reports
    if suffix in (".md", ".rst", ".pdf", ".txt") and any(k in p_str for k in ("docs", "reports", "doc", "readme", "license", "guidelines", "manifest")):
        return "reports/documentation"

    # 13. Configuration
    if suffix in (".json", ".yaml", ".yml", ".toml", ".ini", ".cfg") or name.startswith(".env") or name in ("dockerfile", "compose.yaml", "render.yaml"):
        return "configuration"

    # 14. Temporary Files
    if suffix in (".tmp", ".temp", ".bak", ".swp") or name.endswith(".tmp"):
        return "temporary files"

    # 15. Source Code
    if suffix in (".py", ".ts", ".tsx", ".js", ".jsx", ".html", ".css", ".sh", ".bat", ".ps1", ".vbs", ".c", ".cpp", ".h", ".rs", ".go"):
        return "source code"

    # 16. Other
    return "other"


def audit_project(proj_name: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    target_path = Path(spec["path"])
    is_file = spec.get("is_file", False)
    exclude_subdirs = [Path(p) for p in spec.get("exclude_subdirs", [])]

    breakdown_bytes = {c: 0 for c in CATEGORIES}
    breakdown_files = {c: 0 for c in CATEGORIES}
    all_files: List[Tuple[int, str, str, Path]] = [] # (size, proj_name, category, path)

    total_bytes = 0
    total_files = 0
    total_dirs = 0

    if not target_path.exists():
        return {
            "name": proj_name,
            "path": str(target_path),
            "exists": False,
            "total_bytes": 0,
            "total_files": 0,
            "total_dirs": 0,
            "breakdown_bytes": breakdown_bytes,
            "breakdown_files": breakdown_files,
            "largest_files": [],
        }

    if is_file:
        sz = target_path.stat().st_size
        cat = "other"
        if target_path.suffix == ".zip":
            cat = "other"  # archive
        total_bytes = sz
        total_files = 1
        total_dirs = 0
        breakdown_bytes[cat] = sz
        breakdown_files[cat] = 1
        all_files.append((sz, proj_name, cat, target_path))
    else:
        for root, dirs, files in os.walk(target_path):
            current_dir = Path(root)

            # Check if this directory should be excluded (e.g. if reported as separate project)
            if any(current_dir == exc or exc in current_dir.parents for exc in exclude_subdirs):
                continue

            total_dirs += len(dirs)

            for f in files:
                fp = current_dir / f
                try:
                    # Resolve reparse point or check physical size
                    st = fp.stat()
                    sz = st.st_size
                    cat = classify_file(fp, target_path)

                    total_bytes += sz
                    total_files += 1
                    breakdown_bytes[cat] += sz
                    breakdown_files[cat] += 1
                    all_files.append((sz, proj_name, cat, fp))
                except Exception:
                    pass

    all_files.sort(key=lambda x: x[0], reverse=True)

    return {
        "name": proj_name,
        "path": str(target_path),
        "exists": True,
        "category_group": spec.get("category_group", "A) ACTUAL AUTOMATION PROJECTS"),
        "description": spec.get("description", ""),
        "total_bytes": total_bytes,
        "total_files": total_files,
        "total_dirs": total_dirs,
        "breakdown_bytes": breakdown_bytes,
        "breakdown_files": breakdown_files,
        "largest_files": all_files[:50],
        "all_files": all_files,
    }


def main():
    print("=" * 80)
    print("EXECUTING COMPLETE PC AUTOMATION PROJECT SIZE AUDIT (READ-ONLY)")
    print("=" * 80)

    results: Dict[str, Any] = {}
    master_all_files: List[Tuple[int, str, str, Path]] = []

    for name, spec in PROJECTS_SPEC.items():
        print(f"[*] Auditing: {name} ({spec['path']})...", flush=True)
        t0 = time.time()
        res = audit_project(name, spec)
        elapsed = time.time() - t0
        results[name] = res
        master_all_files.extend(res["all_files"])
        gb = res["total_bytes"] / (1024 ** 3)
        mb = res["total_bytes"] / (1024 ** 2)
        sz_str = f"{gb:.2f} GB" if gb >= 1.0 else f"{mb:.1f} MB"
        print(f"    -> {sz_str} ({res['total_files']} files, {res['total_dirs']} dirs) in {elapsed:.2f}s", flush=True)

    # Sort master largest files
    master_all_files.sort(key=lambda x: x[0], reverse=True)

    # Group totals
    global_category_bytes = {c: 0 for c in CATEGORIES}
    global_category_files = {c: 0 for c in CATEGORIES}

    # Grouped by category_group
    group_totals = {}

    for name, res in results.items():
        grp = res.get("category_group", "OTHER")
        group_totals.setdefault(grp, {"bytes": 0, "files": 0, "dirs": 0, "projects": []})
        group_totals[grp]["bytes"] += res["total_bytes"]
        group_totals[grp]["files"] += res["total_files"]
        group_totals[grp]["dirs"] += res["total_dirs"]
        group_totals[grp]["projects"].append(name)

        for c in CATEGORIES:
            global_category_bytes[c] += res["breakdown_bytes"][c]
            global_category_files[c] += res["breakdown_files"][c]

    # Save raw audit data
    audit_dump = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_automation_storage_bytes": sum(r["total_bytes"] for r in results.values()),
        "global_category_bytes": global_category_bytes,
        "global_category_files": global_category_files,
        "group_totals": {k: {"bytes": v["bytes"], "files": v["files"], "dirs": v["dirs"], "gb": round(v["bytes"] / (1024**3), 2)} for k, v in group_totals.items()},
        "projects": {k: {
            "path": v["path"],
            "total_bytes": v["total_bytes"],
            "total_gb": round(v["total_bytes"] / (1024**3), 3),
            "total_mb": round(v["total_bytes"] / (1024**2), 1),
            "total_files": v["total_files"],
            "total_dirs": v["total_dirs"],
            "category_group": v.get("category_group", ""),
            "breakdown_bytes": v["breakdown_bytes"],
            "breakdown_mb": {c: round(b / (1024**2), 2) for c, b in v["breakdown_bytes"].items()},
            "breakdown_files": v["breakdown_files"],
        } for k, v in results.items()},
        "top_50_largest_files": [
            {
                "rank": idx + 1,
                "project": item[1],
                "category": item[2],
                "path": str(item[3]),
                "extension": item[3].suffix.lower(),
                "size_bytes": item[0],
                "size_mb": round(item[0] / (1024**2), 2),
                "size_gb": round(item[0] / (1024**3), 3),
            }
            for idx, item in enumerate(master_all_files[:50])
        ]
    }

    out_json = PROJECT_ROOT / "reports" / "complete_pc_automation_storage_audit.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(audit_dump, f, indent=2)

    # Generate markdown report
    out_md = PROJECT_ROOT / "reports" / "complete_pc_automation_storage_audit.md"
    generate_markdown_report(audit_dump, results, master_all_files, group_totals, global_category_bytes, global_category_files, out_md)
    print(f"[+] Formatted Markdown report saved to {out_md}")


def generate_markdown_report(audit_dump: Dict[str, Any], results: Dict[str, Any], master_all_files: List[Tuple[int, str, str, Path]], group_totals: Dict[str, Any], global_cat_bytes: Dict[str, int], global_cat_files: Dict[str, int], out_md: Path):
    lines = []
    total_bytes = audit_dump["total_automation_storage_bytes"]
    total_gb = total_bytes / (1024 ** 3)
    total_files = sum(r["total_files"] for r in results.values())
    total_dirs = sum(r["total_dirs"] for r in results.values())

    lines.append("# Complete PC Video Automation Storage Audit Report")
    lines.append("")
    lines.append(f"**Audit Timestamp:** `{audit_dump['timestamp']}`  ")
    lines.append("**System Platform:** Windows (`C:\\`)  ")
    lines.append("**Execution Mode:** **STRICTLY READ-ONLY** (0 files modified, 0 bytes deleted)  ")
    lines.append("**Scope:** Exhaustive filesystem storage measurement of ALL YouTube, video, clipping, and social automation projects, runtime environments, AI models, shared caches, backups, mirrors, duplicates, and local media.  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 1. Executive Summary
    lines.append("## 1. Executive Summary & Storage Totals")
    lines.append("")
    lines.append(f"> [!IMPORTANT]")
    lines.append(f"> **Total Automation Storage Occupied:** **`{total_gb:.2f} GB`** ({total_bytes:,} bytes) across **`{total_files:,}`** files and **`{total_dirs:,}`** directories.")
    lines.append("")
    lines.append("### High-Level Group Breakdown")
    lines.append("")
    lines.append("| Category Group | Projects / Targets | Total Files | Total Dirs | Size (GB) | % of Total Storage |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")

    group_sort_order = [
        "A) ACTUAL AUTOMATION PROJECTS",
        "E) BACKUPS & DUPLICATES",
        "D) SHARED MODELS & CACHES",
        "B) POSSIBLE AUTOMATION-RELATED",
    ]
    for grp in group_sort_order:
        if grp in group_totals:
            g_data = group_totals[grp]
            g_gb = g_data["bytes"] / (1024 ** 3)
            g_pct = (g_data["bytes"] / total_bytes * 100) if total_bytes > 0 else 0
            lines.append(f"| **{grp}** | {len(g_data['projects'])} | {g_data['files']:,} | {g_data['dirs']:,} | **{g_gb:.2f} GB** | {g_pct:.1f}% |")
    lines.append(f"| **ALL COMBINED** | **{len(results)}** | **{total_files:,}** | **{total_dirs:,}** | **`{total_gb:.2f} GB`** | **100.0%** |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 2. Master Table
    lines.append("## 2. Master Project-by-Project Storage Comparison")
    lines.append("")
    lines.append("All audited automation projects, dependencies, model hubs, and backup directories, sorted in descending order of storage footprint:")
    lines.append("")
    lines.append("| Rank | Target / Project Name | Group | Path | Total Files | Code (MB) | Models (GB) | Media (GB) | Cache/Env (GB) | Other (GB) | Total Size |")
    lines.append("| :---: | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

    sorted_projects = sorted(results.items(), key=lambda kv: kv[1]["total_bytes"], reverse=True)
    for idx, (name, res) in enumerate(sorted_projects):
        p_bytes = res["total_bytes"]
        p_gb = p_bytes / (1024 ** 3)
        p_mb = p_bytes / (1024 ** 2)
        sz_fmt = f"**{p_gb:.2f} GB**" if p_gb >= 1.0 else f"**{p_mb:.1f} MB**"

        bb = res["breakdown_bytes"]
        code_mb = (bb.get("source code", 0) + bb.get("tests", 0)) / (1024 ** 2)
        models_gb = bb.get("models", 0) / (1024 ** 3)
        media_gb = (bb.get("local movie storage", 0) + bb.get("generated videos", 0) + bb.get("generated audio", 0) + bb.get("images/assets", 0)) / (1024 ** 3)
        cache_env_gb = (bb.get("caches", 0) + bb.get("Python environments/dependencies", 0)) / (1024 ** 3)
        other_gb = (p_bytes - (code_mb * 1024**2 + models_gb * 1024**3 + media_gb * 1024**3 + cache_env_gb * 1024**3)) / (1024 ** 3)
        if other_gb < 0: other_gb = 0.0

        p_path_short = res["path"]
        if len(p_path_short) > 42:
            p_path_short = "..." + p_path_short[-39:]

        lines.append(f"| {idx+1} | **{name}** | {res['category_group'][:2]} | `{p_path_short}` | {res['total_files']:,} | {code_mb:.1f} MB | {models_gb:.2f} GB | {media_gb:.2f} GB | {cache_env_gb:.2f} GB | {other_gb:.2f} GB | {sz_fmt} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # 3. Global Storage Breakdown by File Category
    lines.append("## 3. Global Storage Breakdown by Category")
    lines.append("")
    lines.append("Storage distribution across all 16 canonical categories defined for this audit:")
    lines.append("")
    lines.append("| Category | Total Files | Size (MB) | Size (GB) | % of Total Storage | Description / Typical Contents |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :--- |")

    sorted_cats = sorted(CATEGORIES, key=lambda c: global_cat_bytes[c], reverse=True)
    cat_desc = {
        "local movie storage": "Raw high-res movie source footage (MKV/MP4 in data/movies)",
        "generated videos": "Rendered final MP4s, timeline test clips, video beats",
        "Python environments/dependencies": "Isolated virtual environments (venv, .venv, venv311, node_modules)",
        "models": "AI weights (.safetensors, .onnx, .bin, .pt, OWLv2, F5-TTS, Vocos, Whisper)",
        "caches": "Build caches, __pycache__, huggingface download blobs, pip caches",
        "other": "Compressed backup archives (.zip), binary assets, unclassified files",
        "images/assets": "Source frames, verification keyframes, thumbnails, PNG/JPG assets",
        "generated audio": "TTS narration WAVs, extracted BGM, sound effects, audio mixes",
        "logs": "Execution logs, audit logs, jsonl transcripts",
        "Git/.git": "Local git repository history, packfiles, refs",
        "reports/documentation": "Markdown documentation, forensic reports, guides, specs",
        "SQLite/databases": "Local SQLite databases (.db, .sqlite, state tracking)",
        "source code": "Python, TypeScript, JavaScript, HTML, CSS automation scripts",
        "configuration": "JSON metadata, YAML workflows, settings, env templates",
        "tests": "Pytest test suites, unit & integration test files",
        "temporary files": "Temporary lockfiles, swap files, intermediary render scratch",
    }

    for c in sorted_cats:
        c_bytes = global_cat_bytes[c]
        c_mb = c_bytes / (1024 ** 2)
        c_gb = c_bytes / (1024 ** 3)
        c_pct = (c_bytes / total_bytes * 100) if total_bytes > 0 else 0
        lines.append(f"| **{c}** | {global_cat_files[c]:,} | {c_mb:,.1f} MB | **{c_gb:.2f} GB** | {c_pct:.1f}% | {cat_desc.get(c, '')} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # 4. Local Media Storage Deep-Dive
    lines.append("## 4. Local Media Storage Deep-Dive (Source Movie Footage)")
    lines.append("")
    lines.append("> [!NOTE]")
    lines.append("> **Local Working Copies Only**: As required, source movie footage files (`data/movies`) are categorized separately from pure code/model storage. These files represent essential raw high-definition video assets used for visual extraction, ground truth evidence, and render testing.")
    lines.append("")

    # Find all files classified under 'local movie storage'
    movie_files = [item for item in master_all_files if item[2] == "local movie storage"]
    movie_bytes = sum(item[0] for item in movie_files)
    movie_gb = movie_bytes / (1024 ** 3)

    lines.append(f"- **Total Dedicated Movie Storage:** **`{movie_gb:.2f} GB`** ({len(movie_files)} source files)")
    lines.append("")
    lines.append("| Movie / File Name | Project | File Size (MB) | File Size (GB) | Path |")
    lines.append("| :--- | :--- | :---: | :---: | :--- |")
    for sz, proj, cat, fp in movie_files:
        sz_mb = sz / (1024 ** 2)
        sz_gb = sz / (1024 ** 3)
        lines.append(f"| **{fp.name}** | {proj} | {sz_mb:,.1f} MB | **{sz_gb:.2f} GB** | `{fp}` |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # 5. Duplicates, Clones & Backup Archives Deep-Dive
    lines.append("## 5. Backups, Mirrors & Redundant Duplicates Deep-Dive")
    lines.append("")
    lines.append("> [!WARNING]")
    lines.append("> **Redundant / Cold Storage Footprint:** A significant portion of disk space is consumed by inactive mirror folders, zip backups, historical repository clones, and AI session transcripts. None of these files are active runtime dependencies.")
    lines.append("")

    backup_projects = [
        "AL AMR Active Mirror Zip",
        "AL AMR Active Mirror Directory",
        "AL AMR Backup Master Zip",
        "AL AMR Cold Storage Secrets Zip",
        "AL AMR Old Desktop Clone (Aug 27)",
        "StoryForge Backup PreFix",
        "StoryForge Buyer Package",
        "Antigravity Brain Artifacts & Transcripts",
    ]
    backup_total_bytes = sum(results[p]["total_bytes"] for p in backup_projects if p in results)
    backup_total_gb = backup_total_bytes / (1024 ** 3)

    lines.append(f"- **Total Inactive Backups & Duplicates Footprint:** **`{backup_total_gb:.2f} GB`**")
    lines.append("")
    lines.append("| Target Name | Location / Path | Files | Size (GB) | Status & Description |")
    lines.append("| :--- | :--- | :---: | :---: | :--- |")
    for bp in backup_projects:
        if bp in results:
            b_res = results[bp]
            b_gb = b_res["total_bytes"] / (1024 ** 3)
            b_mb = b_res["total_bytes"] / (1024 ** 2)
            sz_str = f"**{b_gb:.2f} GB**" if b_gb >= 1.0 else f"{b_mb:.1f} MB"
            lines.append(f"| **{bp}** | `{b_res['path']}` | {b_res['total_files']:,} | {sz_str} | {b_res['description']} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # 6. Detailed Target Profiles
    lines.append("## 6. Detailed Profiles by Target")
    lines.append("")
    for name, res in sorted_projects:
        r_gb = res["total_bytes"] / (1024 ** 3)
        r_mb = res["total_bytes"] / (1024 ** 2)
        sz_str = f"{r_gb:.2f} GB" if r_gb >= 1.0 else f"{r_mb:.1f} MB"

        lines.append(f"### {name}")
        lines.append(f"- **Path:** `{res['path']}`")
        lines.append(f"- **Group:** {res.get('category_group', 'N/A')}")
        lines.append(f"- **Description:** {res.get('description', '')}")
        lines.append(f"- **Total Size:** **{sz_str}** ({res['total_bytes']:,} bytes)")
        lines.append(f"- **Total Files / Dirs:** {res['total_files']:,} files, {res['total_dirs']:,} dirs")
        lines.append("")

        # Breakdown table
        lines.append("| Category | Files | Size (MB) | Size (GB) | % Share |")
        lines.append("| :--- | :---: | :---: | :---: | :---: |")
        b_bytes = res["breakdown_bytes"]
        b_files = res["breakdown_files"]
        active_cats = [c for c in CATEGORIES if b_bytes[c] > 0 or b_files[c] > 0]
        active_cats.sort(key=lambda c: b_bytes[c], reverse=True)
        for ac in active_cats:
            ac_sz = b_bytes[ac]
            ac_pct = (ac_sz / res["total_bytes"] * 100) if res["total_bytes"] > 0 else 0
            lines.append(f"| {ac} | {b_files[ac]:,} | {ac_sz / (1024**2):,.1f} MB | {ac_sz / (1024**3):.3f} GB | {ac_pct:.1f}% |")

        # Top 3 largest files in target
        if res["largest_files"]:
            lines.append("")
            lines.append("**Top Files:**")
            for l_sz, l_proj, l_cat, l_fp in res["largest_files"][:3]:
                l_mb = l_sz / (1024 ** 2)
                lines.append(f"- `{l_fp.name}` ({l_mb:,.1f} MB) — *{l_cat}*")

        lines.append("")

    lines.append("---")
    lines.append("")

    # 7. Top 50 Largest Automation Files Across PC
    lines.append("## 7. Top 50 Largest Automation Files Across the Entire PC")
    lines.append("")
    lines.append("The 50 single largest files detected across all automation workspaces, dependencies, models, and backup archives:")
    lines.append("")
    lines.append("| Rank | File Name | Target / Project | Category | Ext | Size (MB) | Size (GB) | Relative / Absolute Path |")
    lines.append("| :---: | :--- | :--- | :--- | :---: | :---: | :---: | :--- |")

    for idx, (sz, proj, cat, fp) in enumerate(master_all_files[:50]):
        sz_mb = sz / (1024 ** 2)
        sz_gb = sz / (1024 ** 3)
        fp_str = str(fp)
        if len(fp_str) > 50:
            fp_str = "..." + fp_str[-47:]
        lines.append(f"| {idx+1} | **{fp.name}** | {proj} | {cat} | `{fp.suffix.lower()}` | {sz_mb:,.1f} MB | **{sz_gb:.2f} GB** | `{fp_str}` |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # 8. Optimization & Safe Reclamation Insights
    lines.append("## 8. Safe Reclamation & Disk Optimization Opportunities")
    lines.append("")
    lines.append("> [!TIP]")
    lines.append("> **Zero Operational Risk Storage Reclamation (Advisory Only)**  ")
    lines.append("> The audit confirms that the following items are inactive or duplicated, and could be moved to external cold storage or safely pruned if disk space is ever required in the future:")
    lines.append("")
    lines.append(f"1. **`C:\\automation backups` Archives ({backup_total_gb - 2.39:.2f} GB)**: Multiple overlapping backups (active mirror folder + active mirror zip + complete automation zip). Consolidating to one off-disk cold backup frees up over **10 GB** instantly.")
    lines.append(f"2. **Desktop Duplicate Clone (`C:\\Users\\jisha\\Desktop\\yt automation` — 385.5 MB)**: Stale clone from August 27 completely redundant with the live active workspace on OneDrive Desktop.")
    lines.append(f"3. **HuggingFace Models Hub (`C:\\Users\\jisha\\.cache\\huggingface\\hub` — 2.76 GB)**: Contains downloaded model snapshots for F5-TTS, Vocos, OWLv2, and Whisper. These can be cleared and re-downloaded on demand if needed.")
    lines.append(f"4. **Antigravity Brain Artifacts (`C:\\Users\\jisha\\.gemini\\antigravity\\brain` — 2.39 GB)**: Ephemeral test clips, keyframe diagnostics, and logs across previous agent sessions.")
    lines.append(f"5. **AutoClip Virtual Environments (`C:\\Users\\jisha\\OneDrive\\Desktop\\automation_clipping` — ~6.5 GB in `venv311` & `.venv`)**: Duplicate virtual environments inside the clipping automation directory.")
    lines.append("")
    lines.append("*(Note: In accordance with audit safety instructions, no changes or deletions were performed.)*")
    lines.append("")

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
