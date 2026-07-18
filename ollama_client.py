from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import re
import urllib.error
import urllib.request

from storyboard_generator import StoryboardScene


class OllamaClientError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: float = 2.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request_json(self, path: str, payload: dict | None = None, *, timeout: float | None = None) -> dict:
        url = self.base_url + path
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as response:
                content = response.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            raise OllamaClientError(f"Ollama ist nicht erreichbar: {exc}") from exc
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise OllamaClientError("Ollama lieferte keine gültige JSON-Antwort.") from exc

    def is_available(self) -> bool:
        try:
            self.list_models()
            return True
        except OllamaClientError:
            return False

    def list_models(self) -> list[str]:
        data = self._request_json("/api/tags")
        models = []
        for item in data.get("models", []):
            name = item.get("name") or item.get("model")
            if name:
                models.append(str(name))
        return models

    @staticmethod
    def _extract_json_block(text: str) -> dict:
        text = text.strip()
        if not text:
            raise OllamaClientError("Ollama lieferte keinen Antworttext.")
        candidates = [text]
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            candidates.append(match.group(0))
        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        raise OllamaClientError("Die Ollama-Antwort konnte nicht als JSON interpretiert werden.")

    def generate_storyboard_prompts(
        self,
        story_text: str,
        local_scenes: list[StoryboardScene],
        model: str,
        *,
        timeout: float = 240.0,
    ) -> list[StoryboardScene]:
        if not model.strip():
            raise OllamaClientError("Es wurde kein Ollama-Modell ausgewählt.")
        outline_lines = [f"{scene.index}. {scene.title}: {scene.summary}" for scene in local_scenes]
        instruction = (
            "Du erhältst eine zufällig generierte Sci-Fi-Story und einen bereits vorbereiteten Ablauf mit Schlüsselszenen. "
            "Erstelle für jede Szene einen hochwertigen Prompt für einen externen KI-Bildgenerator. "
            "Die Bildprompts sollen realistisch, cineastisch, atmosphärisch und stilistisch untereinander konsistent sein. "
            "Wichtige Regeln: kein Text im Bild, keine Wasserzeichen, keine UI-Elemente, keine Comic-Optik, "
            "sondern authentisch wirkende Science-Fiction. "
            "Gib ausschließlich JSON im folgenden Format zurück: "
            '{"scenes":[{"index":1,"title":"...","summary":"...","prompt":"..."}]}.\n\n'
            "Story:\n"
            f"{story_text.strip()}\n\n"
            "Vorbereitete Schlüsselszenen:\n"
            + "\n".join(outline_lines)
        )
        payload = {
            "model": model,
            "prompt": instruction,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.4},
        }
        response = self._request_json("/api/generate", payload, timeout=timeout)
        raw_text = str(response.get("response", ""))
        data = self._extract_json_block(raw_text)
        items = data.get("scenes")
        if not isinstance(items, list):
            raise OllamaClientError("Die Ollama-Antwort enthält kein Feld 'scenes'.")

        refined: list[StoryboardScene] = []
        by_index = {int(scene.index): scene for scene in local_scenes}
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index"))
            except (TypeError, ValueError):
                continue
            base = by_index.get(index)
            if base is None:
                continue
            title = str(item.get("title") or base.title).strip()
            summary = str(item.get("summary") or base.summary).strip()
            prompt = str(item.get("prompt") or base.prompt).strip()
            refined.append(replace(base, title=title, summary=summary, prompt=prompt))
        if not refined:
            raise OllamaClientError("Ollama lieferte keine verwendbaren Szenen zurück.")

        refined_by_index = {scene.index: scene for scene in refined}
        ordered = [refined_by_index.get(scene.index, scene) for scene in local_scenes]
        return ordered
