from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from dotenv import load_dotenv

from gui_spector.llm.llm import LLM
from gui_spector.models.requirements import Requirements


load_dotenv()


@dataclass
class AppExtractionResult:
    description: str
    tags: List[str]


class AppExtractor:
    """Extract a concise app description and high-level tags from a screenshot
    and optional requirements using an LLM.

    - Loads a text prompt template from `resources/prompts`.
    - Prompt template is selectable by name.
    - LLM is selectable; defaults to GPT-4.1.
    - Accepts image bytes/path/url. When bytes/path are given, the image is embedded as a data URL hint.
    - Returns `AppExtractionResult` with description and unique tags.
    """

    PROMPT_TEMPLATE_APP_V1 = "PROMPT_APP_EXTRACT_V1.txt"

    def __init__(
        self,
        llm: Optional[LLM] = None,
        prompt_template_name: Optional[str] = None,
        temperature: float = 0.05,
    ) -> None:
        self.llm = llm or LLM(model_name=LLM.MODEL_GPT_4_1, temperature=temperature)
        self.prompt_template_name = (
            prompt_template_name or self.PROMPT_TEMPLATE_APP_V1
        )

    def _load_template(self) -> str:
        package_root = Path(__file__).resolve().parents[3]  # .../gui_spector
        template_name = self.prompt_template_name
        if not template_name.endswith(".txt"):
            template_name = f"{template_name}.txt"
        template_path = package_root / "resources" / "prompts" / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_path}")
        return template_path.read_text(encoding="utf-8")

    def _render_prompt(
        self,
        requirements: Optional[Sequence[Requirements]],
        image_hint: Optional[str],
        max_tags: int,
        requirements_text: Optional[str] = None,
    ) -> str:
        template = self._load_template()
        req_block = "None"
        if requirements:
            lines: List[str] = []
            for r in requirements:
                title = (r.title or "").strip()
                desc = (r.description or "").strip()
                combined = title if title else desc
                if title and desc and title.lower() not in desc.lower():
                    combined = f"{title}: {desc}"
                elif not combined:
                    continue
                lines.append(f"- {combined}")
            if lines:
                req_block = "\n".join(lines)
        elif requirements_text and requirements_text.strip():
            req_block = requirements_text.strip()

        rendered = (
            template
            .replace("{{REQUIREMENTS_BLOCK}}", req_block)
            .replace("{{IMAGE_REFERENCE}}", image_hint or "")
            .replace("{{MAX_TAGS}}", str(max_tags))
        )
        return rendered

    def _image_to_data_url(
        self,
        image_bytes: Optional[bytes] = None,
        image_path: Optional[str] = None,
        mime_type: str = "image/png",
    ) -> Optional[str]:
        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            return f"data:{mime_type};base64,{b64}"
        if image_path:
            try:
                p = Path(image_path)
                if p.exists():
                    data = p.read_bytes()
                    b64 = base64.b64encode(data).decode("utf-8")
                    suffix = p.suffix.lower()
                    mt = "image/jpeg" if suffix in [".jpg", ".jpeg"] else ("image/webp" if suffix == ".webp" else "image/png")
                    return f"data:{mt};base64,{b64}"
            except Exception:
                return None
        return None

    def extract_app(
        self,
        *,
        image_bytes: Optional[bytes] = None,
        image_path: Optional[str] = None,
        image_url: Optional[str] = None,
        requirements: Optional[Sequence[Requirements]] = None,
        requirements_text: Optional[str] = None,
        max_tags: int = 7,
    ) -> AppExtractionResult:
        image_ref = image_url or self._image_to_data_url(image_bytes=image_bytes, image_path=image_path)
        prompt_text = self._render_prompt(
            requirements=requirements,
            image_hint=image_ref,
            max_tags=max_tags,
            requirements_text=requirements_text,
        )
        print(f"Prompt text: {prompt_text}")
        output, _usage = self.llm.invoke(prompt_text)
        print(f"Output: {output}")

        raw = (output or "").strip()
        # Try to locate a JSON object
        start = raw.find("{")
        end = raw.rfind("}")
        json_str = raw[start : end + 1] if start != -1 and end != -1 and end > start else raw
        try:
            data = json.loads(json_str)
        except Exception:
            # Fallback: try pure array -> tags only
            try:
                arr = json.loads(json_str)
                if isinstance(arr, list):
                    return AppExtractionResult(description="", tags=[str(x).strip() for x in arr if str(x).strip()])
            except Exception:
                return AppExtractionResult(description="", tags=[])

        description = ""
        tags: List[str] = []
        if isinstance(data, dict):
            # Try multiple key spellings
            for key in ["description", "app_description", "summary", "overview"]:
                if key in data and isinstance(data[key], str):
                    description = data[key].strip()
                    break
            for key in ["tags", "app_tags", "labels"]:
                if key in data and isinstance(data[key], list):
                    for item in data[key]:
                        s = str(item).strip()
                        if s:
                            tags.append(s)
                    break

        # De-duplicate tags while preserving order
        seen = set()
        uniq: List[str] = []
        for t in tags:
            t_norm = t.lower().strip()
            if t_norm and t_norm not in seen:
                seen.add(t_norm)
                uniq.append(t)
        return AppExtractionResult(description=description, tags=uniq)


