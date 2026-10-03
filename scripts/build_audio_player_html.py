import base64
from pathlib import Path

clone_mp3_path = Path(r"C:\Users\jisha\.gemini\antigravity\brain\eaa301ad-f26a-485c-9af7-0c985361de36\f5_tts_clone_audition\f5_tts_reference_clone_master.mp3")
ref_mp3_path = Path(r"C:\Users\jisha\.gemini\antigravity\brain\eaa301ad-f26a-485c-9af7-0c985361de36\f5_tts_clone_audition\conditioning_reference_segment.mp3")

clone_b64 = base64.b64encode(clone_mp3_path.read_bytes()).decode("ascii")
ref_b64 = base64.b64encode(ref_mp3_path.read_bytes()).decode("ascii")

html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
</head>
<body class="bg-transparent text-[var(--foreground)] antialiased p-3">
  <div class="bg-[var(--card)] text-[var(--foreground)] border border-[var(--border)] rounded-2xl p-5 shadow-lg max-w-xl mx-auto space-y-5">
    
    <div class="flex items-center justify-between border-b border-[var(--border)] pb-3">
      <div>
        <div class="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">STORY FORGE Audio Lab</div>
        <h2 class="text-lg font-bold text-[var(--foreground)]">F5-TTS Voice Clone vs Reference</h2>
      </div>
      <span class="px-2.5 py-1 text-xs font-medium rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
        Ready to Play
      </span>
    </div>

    <!-- Track 1: F5-TTS Cloned Narrator Master -->
    <div class="p-4 rounded-xl bg-[var(--background)]/60 border border-[var(--border)] space-y-2">
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <span class="flex h-2.5 w-2.5 rounded-full bg-indigo-500"></span>
          <span class="font-semibold text-sm text-[var(--foreground)]">1. F5-TTS Cloned Narrator (Broadcast Master)</span>
        </div>
        <span class="text-xs text-[var(--muted-foreground)]">22.05s &bull; -14.0 LUFS</span>
      </div>
      <p class="text-xs text-[var(--muted-foreground)] italic">
        Spoken label + 74-word Deathly Hallows exposition script.
      </p>
      <audio controls class="w-full pt-1" preload="metadata">
        <source src="data:audio/mp3;base64,{clone_b64}" type="audio/mp3">
        Your browser does not support the audio element.
      </audio>
    </div>

    <!-- Track 2: Original Reference Segment -->
    <div class="p-4 rounded-xl bg-[var(--background)]/60 border border-[var(--border)] space-y-2">
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <span class="flex h-2.5 w-2.5 rounded-full bg-amber-500"></span>
          <span class="font-semibold text-sm text-[var(--foreground)]">2. Conditioning Reference Segment (Original Target)</span>
        </div>
        <span class="text-xs text-[var(--muted-foreground)]">5.28s &bull; Barty Crouch Short</span>
      </div>
      <p class="text-xs text-[var(--muted-foreground)] italic">
        "To put that into perspective, even Hermione only got 10..."
      </p>
      <audio controls class="w-full pt-1" preload="metadata">
        <source src="data:audio/mp3;base64,{ref_b64}" type="audio/mp3">
        Your browser does not support the audio element.
      </audio>
    </div>

    <div class="text-xs text-[var(--muted-foreground)] flex justify-between items-center pt-1 border-t border-[var(--border)]">
      <span>Acoustic Distance: 1.2354</span>
      <span>Tenor F0: ~182 Hz vs ~190 Hz</span>
    </div>
  </div>
</body>
</html>
"""

out_file = Path(r"C:\Users\jisha\.gemini\antigravity\brain\eaa301ad-f26a-485c-9af7-0c985361de36\f5_tts_player.html")
out_file.write_text(html_content, encoding="utf-8")
print("Wrote player to:", out_file, "Size bytes:", len(html_content))
