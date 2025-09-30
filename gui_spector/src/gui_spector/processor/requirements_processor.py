from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Sequence
from dotenv import load_dotenv
from gui_spector.llm.llm import LLM
from gui_spector.models.requirements import Requirements, RequirementsPriority
from gui_spector.models.acceptance_criterion import AcceptanceCriterion, AcceptanceState

load_dotenv()


class RequirementsProcessor:
    """Processes plain text into a list of `Requirements` using an LLM.

    Constructor allows injecting a custom `LLM` instance and selecting a prompt template.
    Defaults to GPT-4.1 and template `PROMPT_TEMPLATE_EXTRACTION_V1`.
    """

    # Exposed constant for the default prompt template (stored under resources/prompts)
    PROMPT_TEMPLATE_EXTRACTION_V1 = "PROMPT_REQUIREMENTS_EXTRACT_V1.txt"

    def __init__(
        self,
        llm: Optional[LLM] = None,
        prompt_template_name: Optional[str] = None,
        temperature: float = 0.05,
    ) -> None:
        self.llm = llm or LLM(model_name=LLM.MODEL_GPT_4_1, temperature=temperature)
        self.prompt_template_name = (
            prompt_template_name or self.PROMPT_TEMPLATE_EXTRACTION_V1
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
        input_text: str,
        allow_guess: bool,
        default_priority: RequirementsPriority,
        source: Optional[str] = None,
    ) -> str:
        template = self._load_template()
        # If a source is provided, prepend it to the input section so the model can use it.
        final_input = f"Source: {source}\n\n{input_text}" if source else input_text
        rendered = (
            template
            .replace("{{INPUT_TEXT}}", final_input)
            .replace("{{ALLOW_GUESS}}", "true" if allow_guess else "false")
            .replace("{{DEFAULT_PRIORITY}}", default_priority.value)
        )
        return rendered

    def _parse_priority(self, value: Optional[str]) -> RequirementsPriority:
        if not value:
            return RequirementsPriority.MEDIUM
        value_norm = str(value).strip().lower()
        for p in RequirementsPriority:
            if p.value == value_norm:
                return p
        return RequirementsPriority.MEDIUM

    def _coerce_str_list(self, maybe_list) -> List[str]:
        if maybe_list is None:
            return []
        if isinstance(maybe_list, str):
            # Split by common delimiters if it looks like a CSV string
            parts = [p.strip() for p in maybe_list.replace(";", ",").split(",")]
            return [p for p in parts if p]
        if isinstance(maybe_list, Sequence):
            return [str(x) for x in maybe_list if str(x).strip()]
        return []

    def _coerce_criteria_list(self, maybe_list: Optional[Sequence[str]]) -> List[AcceptanceCriterion]:
        """Assume a list of strings and generate AC-1, AC-2, ... names in order."""
        if not maybe_list:
            return []
        result: List[AcceptanceCriterion] = []
        index = 1
        for it in list(maybe_list):
            text = str(it).strip()
            if not text:
                index += 1
                continue
            result.append(AcceptanceCriterion.create(name=f"AC-{index}", text=text, state=AcceptanceState.UNPROCESSED))
            index += 1
        return result

    def process_text(
        self,
        input_text: str,
        allow_guess: bool = True,
        default_priority: RequirementsPriority = RequirementsPriority.MEDIUM,
        source: Optional[str] = None,
    ) -> List[Requirements]:
        """Extract requirements from plain text using the configured LLM and prompt.
        """
        prompt = self._render_prompt(
            input_text=input_text,
            allow_guess=allow_guess,
            default_priority=default_priority,
            source=source,
        )
        print(f"Prompt: {prompt}")
        output, _usage = self.llm.invoke(prompt)
        print(f"Output: {output}")
        # Attempt to locate a JSON array in the output (robustness if model adds stray text)
        raw = output.strip()
        json_str = raw
        start = raw.find("[")
        end = raw.rfind("]")
        if start != -1 and end != -1 and end > start:
            json_str = raw[start : end + 1]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            raise ValueError("LLM did not return valid JSON array of requirements.")

        if not isinstance(data, list):
            raise ValueError("Expected a JSON array of requirement objects.")

        requirements: List[Requirements] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            description = str(item.get("description") or "").strip()
            if not title and not description:
                continue
            tags = self._coerce_str_list(item.get("tags"))
            acceptance = self._coerce_criteria_list(item.get("acceptance_criteria"))
            priority = self._parse_priority(item.get("priority"))
            req_source = item.get("source") or source
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else None

            requirements.append(
                Requirements.create(
                    title=title,
                    description=description,
                    source=req_source,
                    tags=tags,
                    acceptance_criteria=acceptance,
                    priority=priority,
                    metadata=metadata,
                )
            )

        return requirements


