from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import wave
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR if (SCRIPT_DIR / "manifest.json").is_file() else SCRIPT_DIR.parent
MANIFEST_PATH = ROOT / "manifest.json"
LOG_PATH = ROOT / "production.log"


class BuildError(RuntimeError):
    pass


class Logger:
    def __init__(self) -> None:
        self.started = time.monotonic()
        LOG_PATH.write_text("", encoding="utf-8")

    def write(self, message: str) -> None:
        elapsed = time.monotonic() - self.started
        line = f"[{elapsed:8.1f}s] {message}"
        print(line, flush=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def phase(self, current: int, total: int, message: str) -> None:
        percent = round(current * 100 / max(1, total))
        self.write(f"[{percent:3d}%] PHASE {current}/{total}: {message}")


LOGGER = Logger()


def run(command: list[str], description: str, *, capture: bool = False) -> str:
    LOGGER.write(description)
    LOGGER.write("COMMAND: " + subprocess.list2cmdline(command))
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise BuildError(f"{description} konnte nicht gestartet werden: {exc}") from exc
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "unbekannter Fehler").strip()
        raise BuildError(f"{description} fehlgeschlagen (Exit {completed.returncode}):\n{details}")
    return (completed.stdout or "").strip()


def find_executable(name: str) -> str:
    candidates = [ROOT / "tools" / f"{name}.exe", ROOT / f"{name}.exe"]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    located = shutil.which(name)
    if located:
        return located
    raise BuildError(
        f"{name} wurde nicht gefunden. Installiere FFmpeg und stelle sicher, dass {name} im PATH liegt, "
        f"oder lege {name}.exe in den Ordner tools/."
    )


def load_manifest() -> dict:
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError(f"manifest.json konnte nicht gelesen werden: {exc}") from exc
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise BuildError("manifest.json enthält keine Szenen.")
    return data


def scene_image_path(scene: dict) -> Path:
    raw = str(scene.get("image") or f"scene_{int(scene['index']):02d}.png")
    name = Path(raw).name
    candidates = [ROOT / "images" / name]
    stem = Path(name).stem
    candidates.extend(ROOT / "images" / f"{stem}{suffix}" for suffix in (".png", ".jpg", ".jpeg", ".webp"))
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    raise BuildError(
        f"Szenenbild fehlt: images/{stem}.png. Erzeuge zuerst das Bild für Szene {scene.get('index')} "
        "und speichere es im images-Ordner."
    )


def audio_path(scene: dict) -> Path:
    return ROOT / "audio" / Path(str(scene.get("audio") or f"scene_{int(scene['index']):02d}.wav")).name


def powershell_json(script: Path) -> list[dict]:
    output = run(
        [
            "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(script),
        ],
        f"Stimmenliste aus {script.name} lesen",
        capture=True,
    )
    if not output:
        return []
    data = json.loads(output)
    if isinstance(data, dict):
        return [data]
    return list(data)


def choose_voice(manifest: dict) -> tuple[str, str, str]:
    voice = manifest.get("voice") or {}
    requested_id = str(voice.get("id") or "").strip()
    requested_name = str(voice.get("name") or "").strip()
    backend_key = str(voice.get("backend_key") or "").strip().lower()
    backend_label = str(voice.get("backend") or "").lower()

    if os.name != "nt":
        raise BuildError(
            "Für die automatische TTS-Erzeugung ist Windows erforderlich. Alternativ können bereits erzeugte "
            "audio/scene_XX.wav-Dateien in das Paket gelegt und das Skript erneut gestartet werden."
        )

    tools = ROOT / "tools"
    prefer_winrt = backend_key == "winrt" or "winrt" in backend_label or "onecore" in backend_label
    sources = ["winrt", "sapi"] if prefer_winrt else ["sapi", "winrt"]
    for source in sources:
        if source == "winrt":
            voices = powershell_json(tools / "list_winrt_voices.ps1")
        else:
            voices = powershell_json(tools / "list_sapi_voices.ps1")
        if requested_id:
            match = next((item for item in voices if str(item.get("id", "")) == requested_id), None)
            if match:
                return source, str(match["id"]), str(match.get("name") or requested_name)
        lowered = requested_name.casefold()
        if lowered:
            match = next((item for item in voices if str(item.get("name", "")).casefold() == lowered), None)
            if match:
                return source, str(match["id"]), str(match.get("name") or requested_name)
        if voices:
            # Prefer a German voice, then a voice matching the requested gender expression.
            gender = str(voice.get("gender_expression") or "").casefold()
            german = [item for item in voices if str(item.get("language", item.get("locale", ""))).lower().startswith("de")]
            pool = german or voices
            if "weib" in gender:
                female = [item for item in pool if "female" in str(item.get("gender", "")).lower()]
                pool = female or pool
            elif "männ" in gender or "mann" in gender:
                male = [item for item in pool if "male" in str(item.get("gender", "")).lower()]
                pool = male or pool
            chosen = pool[0]
            LOGGER.write(
                f"WARNUNG: Gewünschte Stimme '{requested_name}' nicht gefunden. Ersatz: "
                f"{chosen.get('name')} ({source})."
            )
            return source, str(chosen["id"]), str(chosen.get("name") or "Systemstimme")
    raise BuildError("Keine verwendbare Windows-TTS-Stimme wurde gefunden.")


def synthesize_scene(scene: dict, manifest: dict, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    narration = str(scene.get("narration_text") or "").strip()
    if not narration:
        raise BuildError(f"Szene {scene.get('index')} enthält keinen narration_text.")
    text_file = ROOT / "story" / f"scene_{int(scene['index']):02d}.txt"
    text_file.parent.mkdir(parents=True, exist_ok=True)
    text_file.write_text(narration, encoding="utf-8")

    source, voice_id, resolved_name = choose_voice(manifest)
    voice = manifest.get("voice") or {}
    rate = int(voice.get("rate", 0))
    volume = int(voice.get("volume", 100))
    tools = ROOT / "tools"
    if source == "winrt":
        speaking_rate = 1.0 + max(-10, min(10, rate)) * 0.05
        command = [
            "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(tools / "synthesize_winrt.ps1"),
            "-VoiceId", voice_id, "-InputFile", str(text_file), "-OutputFile", str(target),
            "-Rate", f"{speaking_rate:.2f}", "-Volume", f"{max(0, min(100, volume))/100:.2f}",
        ]
    else:
        command = [
            "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(tools / "synthesize_sapi.ps1"),
            "-VoiceId", voice_id, "-InputFile", str(text_file), "-OutputFile", str(target),
            "-Rate", str(max(-10, min(10, rate))), "-Volume", str(max(0, min(100, volume))),
        ]
    run(command, f"Szene {scene['index']:02d} mit {resolved_name} vertonen")
    if not target.is_file() or target.stat().st_size < 44:
        raise BuildError(f"TTS-Ausgabe für Szene {scene['index']} ist leer oder ungültig.")


def probe_duration(ffprobe: str, path: Path) -> float:
    output = run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        f"Dauer von {path.name} ermitteln",
        capture=True,
    )
    try:
        duration = float(output.strip())
    except ValueError as exc:
        raise BuildError(f"Ungültige Mediendauer für {path}: {output}") from exc
    if duration <= 0:
        raise BuildError(f"Mediendauer ist null: {path}")
    return duration


def concat_narration(ffmpeg: str, audio_files: list[Path], output: Path) -> None:
    list_file = ROOT / "audio" / "narration_concat.txt"
    list_file.write_text(
        "\n".join(f"file '{path.resolve().as_posix().replace("'", "'\\''")}'" for path in audio_files) + "\n",
        encoding="utf-8",
    )
    run([
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(output),
    ], "Szenenaudios zur vollständigen Erzählung verbinden")


def mix_background(ffmpeg: str, ffprobe: str, manifest: dict, narration: Path, output: Path) -> None:
    background = manifest.get("background") or {}
    enabled = bool(background.get("enabled"))
    asset = ROOT / str(background.get("asset_path") or "assets/background.wav")
    volume = max(0.0, min(1.0, float(background.get("volume", 0)) / 100.0))
    duration = probe_duration(ffprobe, narration)
    if enabled:
        if not asset.is_file() or asset.stat().st_size < 44:
            raise BuildError(
                "Hintergrundsound ist aktiviert, aber assets/background.wav fehlt. "
                "Der Mix darf nicht stillschweigend ohne Hintergrundton erzeugt werden."
            )
        fade_out = max(0.0, duration - 1.0)
        filter_graph = (
            f"[1:a]volume={volume:.4f},atrim=0:{duration:.3f},"
            f"afade=t=in:st=0:d=1,afade=t=out:st={fade_out:.3f}:d=1[bg];"
            "[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
            "alimiter=limit=0.95[out]"
        )
        run([
            ffmpeg, "-y", "-loglevel", "error",
            "-i", str(narration), "-stream_loop", "-1", "-i", str(asset),
            "-filter_complex", filter_graph, "-map", "[out]",
            "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(output),
        ], "Erzählung und Brückenatmosphäre hörbar mischen")
    else:
        run([
            ffmpeg, "-y", "-loglevel", "error", "-i", str(narration),
            "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(output),
        ], "Finalen Audiomix ohne Hintergrundsound erzeugen")


def build_scene_clip(ffmpeg: str, image: Path, audio: Path, output: Path, width: int, height: int, fps: int) -> None:
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,format=yuv420p"
    )
    run([
        ffmpeg, "-y", "-loglevel", "error",
        "-loop", "1", "-framerate", str(fps), "-i", str(image), "-i", str(audio),
        "-vf", vf, "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(output),
    ], f"Einzelclip {output.name} erstellen")


def build_final_video(
    ffmpeg: str,
    images: list[Path],
    durations: list[float],
    final_audio: Path,
    output: Path,
    width: int,
    height: int,
    fps: int,
    transition: float,
) -> None:
    transition = max(0.0, min(transition, min(durations) / 2 if durations else 0.0))
    command = [ffmpeg, "-y", "-loglevel", "error"]
    for index, (image, duration) in enumerate(zip(images, durations)):
        source_duration = duration + (transition if index < len(images) - 1 else 0.0)
        command.extend(["-loop", "1", "-framerate", str(fps), "-t", f"{source_duration:.3f}", "-i", str(image)])
    audio_index = len(images)
    command.extend(["-i", str(final_audio)])

    filters: list[str] = []
    for index in range(len(images)):
        filters.append(
            f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps},format=yuv420p[v{index}]"
        )
    if len(images) == 1:
        video_label = "v0"
    else:
        elapsed = durations[0]
        previous = "v0"
        for index in range(1, len(images)):
            output_label = f"x{index}"
            filters.append(
                f"[{previous}][v{index}]xfade=transition=fade:duration={transition:.3f}:offset={elapsed:.3f}[{output_label}]"
            )
            previous = output_label
            elapsed += durations[index]
        video_label = previous
    command.extend([
        "-filter_complex", ";".join(filters),
        "-map", f"[{video_label}]", "-map", f"{audio_index}:a:0",
        "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(output),
    ])
    run(command, "Finales Video mit sanften Szenenüberblendungen erstellen")


def verify_video(ffprobe: str, video: Path) -> None:
    data = run([
        ffprobe, "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "json", str(video)
    ], "Finales Video verifizieren", capture=True)
    payload = json.loads(data)
    types = {stream.get("codec_type") for stream in payload.get("streams", [])}
    if "video" not in types or "audio" not in types:
        raise BuildError("Das finale MP4 enthält nicht sowohl eine Video- als auch eine Audiospur.")
    if video.stat().st_size < 100_000:
        raise BuildError("Das finale MP4 ist verdächtig klein und vermutlich unvollständig.")


def package_outputs(output_zip: Path, manifest: dict) -> None:
    contract = manifest.get("result_package") or {}
    include_images = bool(contract.get("include_images", True))
    include_audio = bool(contract.get("include_audio", True))
    include_clips = bool(contract.get("include_clips", False))
    include_project_files = bool(contract.get("include_project_files", True))

    include_roots: list[str] = []
    if include_images:
        include_roots.append("images")
    if include_audio:
        include_roots.append("audio")
    if include_clips:
        include_roots.append("clips")
    if include_project_files:
        include_roots.extend(["story", "prompts", "assets", "tools", "verification"])

    include_files = ["scifi_story.mp4"]
    if include_project_files:
        include_files.extend([
            "manifest.json", "production.log", "style_reference.png",
            "build_story_video.py", "build_video.bat", "requirements.txt",
            "00_START_HERE.txt", "00_EXECUTE_THIS_TASK.txt", "TASK.json",
        ])

    partial = output_zip.with_suffix(".partial.zip")
    partial.unlink(missing_ok=True)
    with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for filename in include_files:
            path = ROOT / filename
            if path.is_file() and path.resolve() != output_zip.resolve():
                archive.write(path, path.relative_to(ROOT).as_posix())
        for root_name in include_roots:
            root = ROOT / root_name
            if root.is_dir():
                for path in sorted(root.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(ROOT).as_posix())
    partial.replace(output_zip)


def check_inputs(manifest: dict) -> None:
    scenes = manifest["scenes"]
    missing = []
    for scene in scenes:
        try:
            scene_image_path(scene)
        except BuildError as exc:
            missing.append(str(exc))
    if missing:
        raise BuildError("Noch nicht alle Szenenbilder vorhanden:\n- " + "\n- ".join(missing))
    background = manifest.get("background") or {}
    if background.get("enabled") and not (ROOT / "assets" / "background.wav").is_file():
        raise BuildError("assets/background.wav fehlt trotz aktiviertem Hintergrundsound.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Baut die illustrierte SciFi-Audiogeschichte aus dem Übergabepaket.")
    parser.add_argument("--check-only", action="store_true", help="Nur Eingaben und Werkzeuge prüfen.")
    args = parser.parse_args()

    try:
        manifest = load_manifest()
        scenes = manifest["scenes"]
        total_phases = 8
        LOGGER.phase(1, total_phases, "Manifest und Paketstruktur prüfen")
        check_inputs(manifest)
        ffmpeg = find_executable("ffmpeg")
        ffprobe = find_executable("ffprobe")
        if args.check_only:
            LOGGER.write("Prüfung erfolgreich: Bilder, Hintergrunddatei, Manifest und FFmpeg sind vorhanden.")
            return 0

        images = [scene_image_path(scene) for scene in scenes]
        audio_dir = ROOT / "audio"
        clips_dir = ROOT / "clips"
        audio_dir.mkdir(parents=True, exist_ok=True)
        clips_dir.mkdir(parents=True, exist_ok=True)

        LOGGER.phase(2, total_phases, "Szenenweise Sprachausgabe erzeugen oder vorhandene Audios verwenden")
        audio_files: list[Path] = []
        for scene in scenes:
            target = audio_path(scene)
            if target.is_file() and target.stat().st_size >= 44:
                LOGGER.write(f"Vorhandene Audiodatei wird verwendet: {target.relative_to(ROOT)}")
            else:
                synthesize_scene(scene, manifest, target)
            audio_files.append(target)

        LOGGER.phase(3, total_phases, "Audiodauern bestimmen und Erzählung verbinden")
        durations = [probe_duration(ffprobe, path) for path in audio_files]
        narration = audio_dir / "narration_full.wav"
        concat_narration(ffmpeg, audio_files, narration)

        LOGGER.phase(4, total_phases, "Brückenatmosphäre in den finalen Audiomix einarbeiten")
        final_mix = audio_dir / "final_mix.wav"
        mix_background(ffmpeg, ffprobe, manifest, narration, final_mix)

        LOGGER.phase(5, total_phases, "Einzelclips erstellen")
        width = int(manifest.get("width", 1024))
        height = int(manifest.get("height", 1024))
        fps = int(manifest.get("fps", 8))
        for scene, image, audio in zip(scenes, images, audio_files):
            target = clips_dir / f"scene_{int(scene['index']):02d}.mp4"
            build_scene_clip(ffmpeg, image, audio, target, width, height, fps)

        LOGGER.phase(6, total_phases, "Finales Video mit Überblendungen bauen")
        final_video = ROOT / str((manifest.get("outputs") or {}).get("video") or "scifi_story.mp4")
        build_final_video(
            ffmpeg, images, durations, final_mix, final_video, width, height, fps,
            float(manifest.get("transition_seconds", 0.8)),
        )

        LOGGER.phase(7, total_phases, "Video- und Audiospuren verifizieren")
        verify_video(ffprobe, final_video)
        LOGGER.write(f"Finales Video geprüft: {final_video.name} ({final_video.stat().st_size} Bytes)")

        LOGGER.phase(8, total_phases, "Gesamtergebnis als ZIP paketieren")
        output_zip = ROOT / str((manifest.get("outputs") or {}).get("zip") or "scifi_story_package.zip")
        package_outputs(output_zip, manifest)
        LOGGER.write(f"FERTIG: {final_video}")
        LOGGER.write(f"FERTIG: {output_zip}")
        return 0
    except KeyboardInterrupt:
        LOGGER.write("ABGEBROCHEN: Benutzerabbruch.")
        return 130
    except (BuildError, OSError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        LOGGER.write("FEHLER: " + str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
