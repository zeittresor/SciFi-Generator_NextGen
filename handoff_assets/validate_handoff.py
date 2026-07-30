from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
required = [
    "00_START_HERE.txt", "00_EXECUTE_THIS_TASK.txt", "01_PRODUCTION_PROMPT.txt",
    "README_HANDOFF.txt", "TASK.json", "manifest.json", "style_reference.png",
    "prompts/scifi_media_package_prompt.txt", "story/full_story.txt",
    "build_story_video.py", "build_video.bat", "requirements.txt", "audio_mixer.py",
    "tools/synthesize_winrt.ps1", "tools/synthesize_sapi.ps1",
    "tools/list_winrt_voices.ps1", "tools/list_sapi_voices.ps1",
    "offline_fallback/build_story_video.py", "offline_fallback/build_video.bat",
    "offline_fallback/requirements.txt", "offline_fallback/audio_mixer.py",
]
missing = [name for name in required if not (ROOT / name).is_file()]
try:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8-sig"))
except Exception as exc:
    print(f"[ERROR] manifest.json: {exc}")
    raise SystemExit(1)
if manifest.get("background", {}).get("enabled") and not (ROOT / "assets/background.wav").is_file():
    missing.append("assets/background.wav")
style = manifest.get("style_reference") or {}
if not style.get("enabled") or style.get("filename") != "style_reference.png":
    missing.append("manifest.style_reference")
result = manifest.get("result_package") or {}
if not result.get("video_always_included"):
    missing.append("manifest.result_package.video_always_included")
if missing:
    print("[ERROR] Fehlende oder ungültige Übergabedateien:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)
print(
    f"[OK] Übergabepaket vollständig: {len(manifest.get('scenes', []))} Szenen, "
    "Stilreferenz, Build-Skripte und ausgewählter Ergebnis-Lieferumfang vorhanden."
)
