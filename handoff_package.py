from __future__ import annotations

from pathlib import Path
import json
import shutil
import tempfile
import zipfile


class HandoffPackageError(RuntimeError):
    pass


FALLBACK_ASSETS_DIR = Path(__file__).resolve().with_name("handoff_assets")
DEFAULT_STYLE_REFERENCE = FALLBACK_ASSETS_DIR / "style_reference.png"

REQUIRED_HANDOFF_FILES = {
    "00_START_HERE.txt",
    "00_EXECUTE_THIS_TASK.txt",
    "01_PRODUCTION_PROMPT.txt",
    "README_HANDOFF.txt",
    "TASK.json",
    "manifest.json",
    "prompts/scifi_media_package_prompt.txt",
    "story/full_story.txt",
    "style_reference.png",
    "verification/DELIVERY_CHECKLIST.txt",
    "verification/validate_handoff.py",
    "build_story_video.py",
    "build_video.bat",
    "requirements.txt",
    "audio_mixer.py",
    "tools/list_winrt_voices.ps1",
    "tools/list_sapi_voices.ps1",
    "tools/synthesize_winrt.ps1",
    "tools/synthesize_sapi.ps1",
    "offline_fallback/build_story_video.py",
    "offline_fallback/build_video.bat",
    "offline_fallback/requirements.txt",
    "offline_fallback/audio_mixer.py",
    "offline_fallback/tools/list_winrt_voices.ps1",
    "offline_fallback/tools/list_sapi_voices.ps1",
    "offline_fallback/tools/synthesize_winrt.ps1",
    "offline_fallback/tools/synthesize_sapi.ps1",
}


def validate_total_package_prompt(prompt_text: str, *, background_required: bool) -> list[str]:
    required_markers = [
        "SCIFI-GENERATOR — GESAMTPAKET-PRODUKTIONSAUFTRAG",
        "NARRATIONSTEXT — exakt für die Sprachausgabe dieser Szene:",
        "AUDIO- UND VIDEOREGELN",
        "AUDIO- UND TTS-QUALITÄTSREGELN",
        "VERBINDLICHER VISUELLER QUALITÄTS- UND STILANKER",
        "LIEFERUMFANG DES FINALEN ERGEBNIS-ZIP",
        "MINDESTLIEFERUNG / COMPLETION GATE",
        "style_reference.png",
        "scifi_story.mp4",
        "scifi_story_package.zip",
        "final_mix.wav",
        "SOFORT AUSFÜHREN, NICHT NUR DAS ARCHIV PRÜFEN",
        "build_story_video.py",
        "build_video.bat",
    ]
    problems = [f"Pflichtabschnitt fehlt: {marker}" for marker in required_markers if marker not in prompt_text]
    if background_required:
        for marker in ("assets/background.wav", "Brückenatmosphäre", "Hintergrund"):
            if marker not in prompt_text:
                problems.append(f"Hintergrundsound-Verweis fehlt: {marker}")
    if "AUSFÜHRBARER BILDSERIEN-AUFTRAG" in prompt_text:
        problems.append("Die Ausgabe ist ein Bildserien-Auftrag und kein Gesamtpaket-Produktionsauftrag.")
    return problems


def _result_contract(manifest: dict) -> dict:
    contract = dict(manifest.get("result_package") or {})
    return {
        "video_always_included": True,
        "include_images": bool(contract.get("include_images", True)),
        "include_audio": bool(contract.get("include_audio", True)),
        "include_clips": bool(contract.get("include_clips", False)),
        "include_project_files": bool(contract.get("include_project_files", True)),
    }


def _result_description(manifest: dict) -> str:
    contract = _result_contract(manifest)
    items = ["fertiges Video"]
    if contract["include_images"]:
        items.append("Szenenbilder")
    if contract["include_audio"]:
        items.append("Szenenaudios und final_mix.wav")
    if contract["include_clips"]:
        items.append("Einzelclips")
    if contract["include_project_files"]:
        items.append("Story, Prompts, Manifest, Log und Build-Dateien")
    return ", ".join(items)


def _start_here_text(*, app_version: str, manifest: dict, background_included: bool) -> str:
    scene_count = len(manifest.get("scenes") or [])
    outputs = manifest.get("outputs") or {}
    video_name = str(outputs.get("video") or "scifi_story.mp4")
    zip_name = str(outputs.get("zip") or "scifi_story_package.zip")
    fps = int(manifest.get("fps", 8))
    resolution = str(manifest.get("resolution") or "1024x1024")
    voice = manifest.get("voice") or {}
    voice_quality = str(voice.get("quality_target") or "Beste verfügbare Qualität")
    voice_character = str(voice.get("character") or "Menschlich / natürlich")
    result_description = _result_description(manifest)
    background_note = (
        "Die Original-Brückenatmosphäre liegt in assets/background.wav und MUSS leise, aber hörbar, in "
        "audio/final_mix.wav und in die Audiospur des finalen MP4 eingemischt werden."
        if background_included
        else "In diesem Auftrag ist kein Hintergrundsound aktiviert."
    )
    return f"""SCIFI-GENERATOR v{app_version} — START HERE / GESAMTPAKET-ÜBERGABE

DIES IST EINE AUSFÜHRUNGSANWEISUNG, KEINE BITTE UM ARCHIVANALYSE.
Dies ist ausdrücklich KEIN reiner Bildserien-Auftrag.

Öffne zuerst 01_PRODUCTION_PROMPT.txt beziehungsweise prompts/scifi_media_package_prompt.txt und führe den dortigen Produktionsauftrag vollständig aus. Fehlende Bilder, Audiodateien und Videos sind die zu erzeugenden Ergebnisse und keine Paketfehler.

VERBINDLICHER ABLAUF
1. Erzeuge chronologisch genau {scene_count} separate Szenenbilder.
2. Verwende style_reference.png als visuellen Qualitäts- und Stilanker; keine flache 2D-, Vektor-, Cutout-, Low-Poly-, Collage- oder Storyboard-Optik.
3. Stoppe nach den Bildern nicht. Stoppe danach nicht, sondern erzeuge die Szenenaudios aus den NARRATIONSTEXT-Blöcken.
4. Mische Stimme und gegebenenfalls background.wav zu audio/final_mix.wav.
5. Erzeuge {video_name} in {resolution} mit {fps} fps und hörbarer Audiospur.
6. Erzeuge {zip_name} mit genau diesem gewünschten Lieferumfang: {result_description}.
7. Die Auswahl des ZIP-Lieferumfangs betrifft nur die zurückgelieferten Dateien. Bilder und Audio müssen für den Videobau trotzdem produziert werden.
8. Falls direkte Audio-/Videoerzeugung nicht möglich ist, verwende die bereits enthaltenen echten Skripte build_story_video.py und build_video.bat. Identische Kopien liegen zusätzlich unter offline_fallback/.

STIMMENQUALITÄT
Gewünschter Stimmcharakter: {voice_character}
Qualitätsziel: {voice_quality}
Bei natürlicher Stimme sind eSpeak-artige, robotische Linux-Legacy- oder monotone Standardstimmen nicht als undokumentierte finale Qualitätsstimme zulässig. Jede Abweichung protokollieren.

{background_note}

NICHT ALS ENDERGEBNIS ZULÄSSIG
- reine Beschreibung oder Analyse des ZIP-Inhalts
- Hinweis, dass Output-Medien noch fehlen
- ZIP mit ausschließlich Bildern und ohne fertiges Video
- Pseudocode anstelle der beigefügten ausführbaren Skripte

ERFOLGSKRITERIUM
Die Aufgabe ist erst abgeschlossen, wenn {video_name} mit vollständiger, hörbarer Sprachausgabe vorliegt und {zip_name} exakt den oben ausgewählten Lieferumfang enthält.
"""


def _readme_text(*, app_version: str, manifest: dict, background_included: bool) -> str:
    return f"""SCIFI-GENERATOR v{app_version} — GESAMTPAKET-HANDOFF

Dieses Übergabe-ZIP ist zur direkten Weitergabe an ein Bild-/Audio-/Video-fähiges LLM gedacht.

Wichtige Eigenschaften:
- style_reference.png als verbindlicher Qualitäts- und Stilanker für cinematische CGI-/3D-Filmstills
- vollständiger Produktionsprompt und maschinenlesbares Manifest
- echte Offline-Fallback-Skripte im Wurzelverzeichnis und unter offline_fallback/
- {'eingebettete Brückenatmosphäre unter assets/background.wav' if background_included else 'kein aktivierter Hintergrundsound'}
- gewünschter Inhalt des finalen Ergebnis-ZIP: {_result_description(manifest)}

Das Übergabe-ZIP selbst enthält absichtlich noch keine fertigen Szenenmedien. Diese werden durch das Zielsystem erzeugt. Die Lieferumfangsauswahl betrifft das finale Ergebnis-ZIP, nicht die zur Produktion erforderlichen Zwischenschritte.
"""


def _delivery_checklist_text(*, manifest: dict, background_included: bool) -> str:
    contract = _result_contract(manifest)
    resolution = str(manifest.get("resolution") or "1024x1024")
    fps = int(manifest.get("fps", 8))
    style_filename = str((manifest.get("style_reference") or {}).get("filename") or "style_reference.png")
    bg_line = (
        "[ ] assets/background.wav wurde tatsächlich in final_mix.wav und in die Audiospur des MP4 eingemischt; sie ist leise, aber hörbar."
        if background_included
        else "[ ] Hintergrundsound war deaktiviert; es wurde kein Hintergrundmix behauptet."
    )
    lines = [
        "LIEFERPRÜFUNG — FERTIGES VIDEO IST PFLICHT",
        "",
        "[ ] scifi_story.mp4 existiert und ist abspielbar.",
        f"[ ] Das MP4 ist {resolution} und mit {fps} fps kodiert.",
        "[ ] Das MP4 enthält eine hörbare, nicht-stumme Audiospur.",
        "[ ] Die komplette Story ist hörbar; kein Szenentext wurde abgeschnitten.",
        "[ ] Die finale Stimme erfüllt die gewählte Qualitäts- und Charaktervorgabe oder jede Abweichung ist dokumentiert.",
        "[ ] audio/final_mix.wav wurde für den Videobau erzeugt und als tatsächliche MP4-Audiospur verwendet.",
        bg_line,
        f"[ ] {style_filename} wurde als visueller Stilanker verwendet.",
        "[ ] Die Szenenbilder wirken wie final gerenderte cinematische CGI-/3D-Filmstills, nicht wie flache geometrische 2D-Kompositionen, Collagen oder Storyboards.",
        "[ ] Szenenreihenfolge und Übergänge stimmen.",
        "",
        "AUSGEWÄHLTER INHALT DES FINALEN ERGEBNIS-ZIP",
        "[ ] Fertiges Video ist enthalten.",
        f"[ ] Szenenbilder sind {'enthalten' if contract['include_images'] else 'nicht enthalten, wie ausgewählt'}.",
        f"[ ] Szenenaudios und final_mix.wav sind {'enthalten' if contract['include_audio'] else 'nicht enthalten, wie ausgewählt'}.",
        f"[ ] Einzelclips sind {'enthalten' if contract['include_clips'] else 'nicht enthalten, wie ausgewählt'}.",
        f"[ ] Projektdateien sind {'enthalten' if contract['include_project_files'] else 'nicht enthalten, wie ausgewählt'}.",
        "",
        "Eine reine Bilddatei-Sammlung oder eine Ausgabe ohne fertiges Video gilt als unvollständige Lieferung.",
    ]
    return "\n".join(lines) + "\n"


def _task_payload(*, manifest: dict, app_version: str, background_included: bool) -> dict:
    scene_count = len(manifest.get("scenes") or [])
    result_contract = _result_contract(manifest)
    return {
        "schema": "scifi-generator-handoff-v3",
        "app_version": app_version,
        "mode": "execute_now",
        "task": "produce_illustrated_audio_story_video",
        "analysis_only_is_not_an_answer": True,
        "missing_output_media_are_expected": True,
        "offline_build_scripts_included": True,
        "style_reference_included": True,
        "scene_count": scene_count,
        "first_document": "00_START_HERE.txt",
        "production_prompt": "01_PRODUCTION_PROMPT.txt",
        "required_outputs": [
            str((manifest.get("outputs") or {}).get("video") or "scifi_story.mp4"),
            str((manifest.get("outputs") or {}).get("zip") or "scifi_story_package.zip"),
        ],
        "production_intermediates_required": ["images/scene_XX.png", "audio/scene_XX.wav", "audio/final_mix.wav"],
        "final_result_package": result_contract,
        "background_asset": "assets/background.wav" if background_included else "",
        "completion_gate": {
            "images_only_is_incomplete": True,
            "video_must_contain_audio": True,
            "full_narration_required": True,
            "background_must_be_mixed_when_enabled": background_included,
            "style_reference_must_be_used": True,
            "returned_zip_must_match_selected_contents": True,
        },
    }


def validate_handoff_archive(
    archive_path: Path,
    *,
    background_required: bool,
    expected_scene_count: int,
) -> list[str]:
    problems: list[str] = []
    archive_path = Path(archive_path)
    if not archive_path.is_file():
        return [f"Übergabe-ZIP wurde nicht erzeugt: {archive_path}"]
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            for required in sorted(REQUIRED_HANDOFF_FILES):
                if required not in names:
                    problems.append(f"Pflichtdatei fehlt im Übergabe-ZIP: {required}")
            if background_required and "assets/background.wav" not in names:
                problems.append("Hintergrundsound ist aktiviert, aber assets/background.wav fehlt im Übergabe-ZIP.")
            for required in REQUIRED_HANDOFF_FILES:
                if required in names and archive.getinfo(required).file_size == 0:
                    problems.append(f"Pflichtdatei ist leer: {required}")
            if "style_reference.png" in names and archive.getinfo("style_reference.png").file_size < 10_000:
                problems.append("style_reference.png ist verdächtig klein oder ungültig.")
            if "TASK.json" in names:
                try:
                    task = json.loads(archive.read("TASK.json").decode("utf-8-sig"))
                    if task.get("mode") != "execute_now":
                        problems.append("TASK.json enthält nicht mode=execute_now.")
                    if int(task.get("scene_count", -1)) != expected_scene_count:
                        problems.append("TASK.json enthält eine falsche Szenenzahl.")
                    if not task.get("offline_build_scripts_included"):
                        problems.append("TASK.json bestätigt die enthaltenen Offline-Build-Skripte nicht.")
                    if not task.get("style_reference_included"):
                        problems.append("TASK.json bestätigt die enthaltene Stilreferenz nicht.")
                except (UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
                    problems.append(f"TASK.json ist ungültig: {exc}")
            if "manifest.json" in names:
                try:
                    manifest = json.loads(archive.read("manifest.json").decode("utf-8-sig"))
                    scenes = manifest.get("scenes") or []
                    if len(scenes) != expected_scene_count:
                        problems.append(f"manifest.json enthält {len(scenes)} statt {expected_scene_count} Szenen.")
                    if not manifest.get("handoff_package"):
                        problems.append("manifest.json ist nicht als handoff_package markiert.")
                    style = manifest.get("style_reference") or {}
                    if not style.get("enabled") or style.get("filename") != "style_reference.png":
                        problems.append("manifest.json aktiviert style_reference.png nicht korrekt.")
                    result_package = manifest.get("result_package") or {}
                    if not result_package.get("video_always_included"):
                        problems.append("manifest.json schreibt das finale Video nicht verbindlich vor.")
                except (UnicodeError, json.JSONDecodeError) as exc:
                    problems.append(f"manifest.json ist ungültig: {exc}")
            if "00_START_HERE.txt" in names:
                text = archive.read("00_START_HERE.txt").decode("utf-8-sig", errors="replace")
                for marker in (
                    "KEINE BITTE UM ARCHIVANALYSE",
                    "style_reference.png",
                    "Stoppe nach den Bildern nicht",
                    "scifi_story.mp4",
                    "gewünschten Lieferumfang",
                ):
                    if marker not in text:
                        problems.append(f"Startanweisung ist nicht eindeutig genug; Marker fehlt: {marker}")
    except (OSError, zipfile.BadZipFile) as exc:
        problems.append(f"Übergabe-ZIP ist beschädigt oder nicht lesbar: {exc}")
    return problems


def _copy_fallback_assets(temp_root: Path) -> None:
    sources = {
        "build_story_video.py": FALLBACK_ASSETS_DIR / "build_story_video.py",
        "build_video.bat": FALLBACK_ASSETS_DIR / "build_video.bat",
        "requirements.txt": FALLBACK_ASSETS_DIR / "requirements.txt",
        "audio_mixer.py": FALLBACK_ASSETS_DIR / "audio_mixer.py",
        "verification/validate_handoff.py": FALLBACK_ASSETS_DIR / "validate_handoff.py",
        "tools/list_winrt_voices.ps1": FALLBACK_ASSETS_DIR / "tools" / "list_winrt_voices.ps1",
        "tools/list_sapi_voices.ps1": FALLBACK_ASSETS_DIR / "tools" / "list_sapi_voices.ps1",
        "tools/synthesize_winrt.ps1": FALLBACK_ASSETS_DIR / "tools" / "synthesize_winrt.ps1",
        "tools/synthesize_sapi.ps1": FALLBACK_ASSETS_DIR / "tools" / "synthesize_sapi.ps1",
    }
    for archive_name, source in sources.items():
        if not source.is_file():
            raise HandoffPackageError(f"Interne Fallback-Datei fehlt: {source}")
        destinations = [temp_root / archive_name]
        if archive_name != "verification/validate_handoff.py":
            destinations.append(temp_root / "offline_fallback" / archive_name)
        for destination in destinations:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def create_handoff_zip(
    output_path: Path,
    *,
    prompt_text: str,
    manifest: dict,
    full_story: str,
    app_version: str,
    background_path: Path | None = None,
    style_reference_path: Path | None = None,
    extra_files: dict[str, Path] | None = None,
) -> Path:
    output_path = Path(output_path)
    if output_path.suffix.lower() != ".zip":
        output_path = output_path.with_suffix(".zip")
    background_included = bool(background_path and Path(background_path).is_file())
    style_reference = Path(style_reference_path) if style_reference_path else DEFAULT_STYLE_REFERENCE
    if not style_reference.is_file():
        raise HandoffPackageError(f"Stilreferenz fehlt: {style_reference}")

    problems = validate_total_package_prompt(prompt_text, background_required=background_included)
    if problems:
        raise HandoffPackageError("Gesamtpaket-Prompt ist unvollständig:\n" + "\n".join(problems))

    manifest = dict(manifest)
    manifest["handoff_package"] = True
    manifest["app_version"] = app_version
    manifest["instruction_document"] = "01_PRODUCTION_PROMPT.txt"
    manifest["full_story"] = "story/full_story.txt"
    manifest["offline_build_scripts_included"] = True
    manifest["background_asset_included"] = background_included
    manifest.setdefault("style_reference", {})
    manifest["style_reference"].update({
        "enabled": True,
        "filename": "style_reference.png",
        "role": "Primary visual style anchor only; do not copy its exact scene composition.",
    })
    scenes = manifest.get("scenes") or []
    if not isinstance(scenes, list) or not scenes:
        raise HandoffPackageError("Manifest enthält keine Szenen.")
    scene_count = len(scenes)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="scifi_handoff_"))
    try:
        for folder in (
            "prompts", "story", "assets", "verification", "images", "audio", "clips", "tools",
            "offline_fallback", "offline_fallback/tools",
        ):
            (temp_root / folder).mkdir(parents=True, exist_ok=True)

        start_text = _start_here_text(
            app_version=app_version,
            manifest=manifest,
            background_included=background_included,
        )
        (temp_root / "00_START_HERE.txt").write_text(start_text, encoding="utf-8-sig")
        (temp_root / "00_EXECUTE_THIS_TASK.txt").write_text(start_text, encoding="utf-8-sig")
        (temp_root / "README_HANDOFF.txt").write_text(
            _readme_text(app_version=app_version, manifest=manifest, background_included=background_included),
            encoding="utf-8-sig",
        )
        (temp_root / "01_PRODUCTION_PROMPT.txt").write_text(prompt_text, encoding="utf-8-sig")
        (temp_root / "prompts" / "scifi_media_package_prompt.txt").write_text(prompt_text, encoding="utf-8-sig")
        (temp_root / "story" / "full_story.txt").write_text(full_story, encoding="utf-8-sig")
        (temp_root / "TASK.json").write_text(
            json.dumps(
                _task_payload(manifest=manifest, app_version=app_version, background_included=background_included),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8-sig",
        )
        (temp_root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8-sig"
        )
        (temp_root / "verification" / "DELIVERY_CHECKLIST.txt").write_text(
            _delivery_checklist_text(manifest=manifest, background_included=background_included),
            encoding="utf-8-sig",
        )
        (temp_root / "images" / "GENERATE_SCENE_IMAGES_HERE.txt").write_text(
            f"Erzeuge {scene_count} Bilder als scene_01.png bis scene_{scene_count:02d}.png. "
            "Diese Dateien sind Produktionsausgaben und deshalb im Übergabe-ZIP noch nicht vorhanden.\n",
            encoding="utf-8-sig",
        )
        (temp_root / "audio" / "AUDIO_IS_GENERATED_DURING_PRODUCTION.txt").write_text(
            "scene_XX.wav und final_mix.wav werden während der Produktion erzeugt. Ob sie im finalen Ergebnis-ZIP "
            "enthalten sein sollen, steht in manifest.json unter result_package.\n",
            encoding="utf-8-sig",
        )

        shutil.copy2(style_reference, temp_root / "style_reference.png")
        if background_included:
            shutil.copy2(Path(background_path), temp_root / "assets" / "background.wav")

        _copy_fallback_assets(temp_root)

        for archive_name, source_path in (extra_files or {}).items():
            source_path = Path(source_path)
            if not source_path.is_file():
                raise HandoffPackageError(f"Erforderliche Zusatzdatei fehlt: {source_path}")
            destination = temp_root / archive_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)

        partial = output_path.with_name(output_path.stem + ".partial.zip")
        partial.unlink(missing_ok=True)
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(temp_root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(temp_root).as_posix())
        partial.replace(output_path)

        validation = validate_handoff_archive(
            output_path,
            background_required=background_included,
            expected_scene_count=scene_count,
        )
        if validation:
            output_path.unlink(missing_ok=True)
            raise HandoffPackageError(
                "Übergabe-ZIP hat die Abschlussprüfung nicht bestanden:\n" + "\n".join(validation)
            )
        return output_path
    except OSError as exc:
        raise HandoffPackageError(str(exc)) from exc
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
