from gui_spector.computers.computer import Computer
from gui_spector.exceptions.maximum_reasoning_steps import MaximumReasoningStepsReachedException
from gui_spector.utils.utils import (
    create_response,
    show_image,
    pp,
    sanitize_message,
    check_blocklisted_url,
)
from gui_spector.models import (
    Requirements,
    VerficationRunResult,
    Interaction,
    Usage,
    ComputerAction,
    ActionType,
)
from gui_spector.models.verfication_run_result import VerificationStatus
from gui_spector.models import Inputs
from gui_spector.exceptions.acceptance_criteria_mismatch import AcceptanceCriteriaMismatchException
import json
from typing import Callable, List, Optional
import os
from pathlib import Path
from datetime import datetime, timezone


# Module-level default prompt template name
PROMPT_TEMPLATE_V1 = "PROMPT_V1"

class VerficationRunner:
    """
    A sample agent class that can be used to interact with a computer.

    (See simple_cua_loop.py for a simple example without an agent.)
    """

    # Default prompt template constant so callers can reference it explicitly
    PROMPT_TEMPLATE_V1 = "PROMPT_V1"

    def __init__(
        self,
        model="computer-use-preview",
        computer: Computer = None,
        tools: list[dict] = [],
        acknowledge_safety_check_callback: Callable = lambda: False,
        data_dir: Path = None,
        prompt_name: str | None = None,
        run_dir: Path | None = None,
    ):
        self.model = model
        self.computer = computer
        self.tools = tools
        self.print_steps = True
        self.debug = False
        self.show_images = False
        self.acknowledge_safety_check_callback = acknowledge_safety_check_callback
        self.prompt_name = prompt_name or VerficationRunner.PROMPT_TEMPLATE_V1
        # Per-run accumulators
        self._usages: List[Usage] = []
        self._last_response_id: Optional[str] = None
        self._last_action: Optional[ComputerAction] = None
        self._last_screenshot_path: Optional[Path] = None
        self._responses: List[dict] = []
        self._response_extras: List[dict] = []

        # --- Run folder and step counter logic ---
        if run_dir is not None:
            # Use an explicit target directory (created by caller's ID scheme)
            self.run_dir = Path(run_dir)
            # Be idempotent: the task may have already created it
            self.run_dir.mkdir(exist_ok=True, parents=True)
        else:
            if data_dir is None:
                data_dir = Path("data")
            data_dir = Path(data_dir)
            data_dir.mkdir(exist_ok=True, parents=True)
            # Fallback: sequential numbering (legacy)
            existing_runs = [d for d in data_dir.iterdir() if d.is_dir() and d.name.isdigit()]
            if existing_runs:
                max_run_id = max(int(d.name) for d in existing_runs)
            else:
                max_run_id = 0
            self.run_id = max_run_id + 1
            self.run_dir = data_dir / f"{self.run_id:03d}"
            self.run_dir.mkdir(exist_ok=False)
        # Subdirectories for better organization
        self.images_dir = self.run_dir / "images"
        self.responses_dir = self.run_dir / "responses"
        self.interactions_dir = self.run_dir / "interactions"
        self.result_dir = self.run_dir / "result"
        self.images_dir.mkdir(exist_ok=True)
        self.responses_dir.mkdir(exist_ok=True)
        self.interactions_dir.mkdir(exist_ok=True)
        self.result_dir.mkdir(exist_ok=True)
        self.step_counter = 1
        # --- End run folder logic ---

        if computer:
            dimensions = computer.get_dimensions()
            self.tools += [
                {
                    "type": "computer-preview",
                    "display_width": dimensions[0],
                    "display_height": dimensions[1],
                    "environment": computer.get_environment(),
                },
            ]

    def debug_print(self, *args):
        if self.debug:
            pp(*args)

    def handle_item(self, item):
        """Handle each item; may cause a computer action + screenshot."""
        if item["type"] == "message":
            if self.print_steps:
                print(item["content"][0]["text"])
            # Save message to response file as part of the response dump only; no separate txt
            # (Messages will be contained in the full response JSON file.)
            self.step_counter += 1

        if item["type"] == "function_call":
            name, args = item["name"], json.loads(item["arguments"])
            if self.print_steps:
                print(f"{name}({args})")
            # No separate function call txt; action and responses are captured elsewhere
            self.step_counter += 1

            if hasattr(self.computer, name):  # if function exists on computer, call it
                method = getattr(self.computer, name)
                method(**args)
            return [
                {
                    "type": "function_call_output",
                    "call_id": item["call_id"],
                    "output": "success",  # hard-coded output for demo
                }
            ]

        if item["type"] == "computer_call":
            action = item["action"]
            action_type = action["type"]
            action_args = {k: v for k, v in action.items() if k != "type"}
            if self.print_steps:
                print(f"{action_type}({action_args})")

            method = getattr(self.computer, action_type)
            method(**action_args)

            screenshot_base64 = self.computer.screenshot()
            # Save screenshot to images directory
            screenshot_filename = self.images_dir / f"{self.step_counter:03d}.png"
            with open(screenshot_filename, "wb") as f:
                import base64
                f.write(base64.b64decode(screenshot_base64))
            print(f"Saved screenshot to {screenshot_filename}")
            if self.show_images:
                show_image(screenshot_base64)

            # No separate txt action file; interactions JSON will capture details
            self.step_counter += 1

            # if user doesn't ack all safety checks exit with error
            pending_checks = item.get("pending_safety_checks", [])
            for check in pending_checks:
                message = check["message"]
                if not self.acknowledge_safety_check_callback(message):
                    raise ValueError(
                        f"Safety check failed: {message}. Cannot continue with unacknowledged safety checks."
                    )

            call_output = {
                "type": "computer_call_output",
                "call_id": item["call_id"],
                "acknowledged_safety_checks": pending_checks,
                "output": {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{screenshot_base64}",
                },
            }

            # additional URL safety checks for browser environments
            if self.computer.get_environment() == "browser":
                current_url = self.computer.get_current_url()
                check_blocklisted_url(current_url)
                call_output["output"]["current_url"] = current_url

            # Record action and screenshot for this turn
            try:
                atype = ActionType(action_type)
            except ValueError:
                atype = ActionType.WAIT
            safety_msgs = [c.get("message", "") for c in pending_checks] if pending_checks else []
            self._last_action = ComputerAction(
                type=atype,
                params=action_args,
                call_id=item.get("call_id"),
                status=item.get("status"),
                safety_checks=safety_msgs,
            )
            self._last_screenshot_path = screenshot_filename

            return [call_output]
        return []

    def run_full_turn(
        self,
        input_items,
        print_steps=True,
        debug=False,
        show_images=False,
        progress_callback: Optional[Callable[[dict], None]] = None,
        max_reasoning_steps: Optional[int] = None,
    ):
        self.print_steps = print_steps
        self.debug = debug
        self.show_images = show_images
        new_items = []

        # keep looping until we get a final response
        turns_completed = 0
        # Ensure we have a run start time reference for cumulative runtime
        try:
            run_started_at = getattr(self, "_run_started_at", None)
        except Exception:
            run_started_at = None
        while new_items[-1].get("role") != "assistant" if new_items else True:
            self.debug_print([sanitize_message(msg) for msg in input_items + new_items])

            # Mark per-turn start time
            turn_started_at = datetime.now(timezone.utc)

            response = create_response(
                model=self.model,
                input=input_items + new_items,
                tools=self.tools,
                reasoning={"effort": "medium", "summary": "auto"},
                truncation="auto",
            )
            self.debug_print(response)

            # Collect per-response usage in-memory (avoid reading from files)
            try:
                if isinstance(response, dict) and isinstance(response.get("usage"), dict):
                    u = response["usage"]
                    self._usages.append(
                        Usage(
                            tokens_in=int(u.get("input_tokens", 0)),
                            tokens_out=int(u.get("output_tokens", 0)),
                            tokens_reasoning=int((u.get("output_tokens_details", {}) or {}).get("reasoning_tokens", 0)),
                            tokens_total=int(u.get("total_tokens", 0)),
                        )
                    )
                if isinstance(response, dict) and "id" in response:
                    self._last_response_id = str(response["id"])  
            except Exception:
                pass

            # Prepare per-response collection structures
            self._last_action = None
            self._last_screenshot_path = None
            usage_obj = None
            try:
                if isinstance(response, dict) and isinstance(response.get("usage"), dict):
                    u = response["usage"]
                    usage_obj = Usage(
                        tokens_in=int(u.get("input_tokens", 0)),
                        tokens_out=int(u.get("output_tokens", 0)),
                        tokens_reasoning=int((u.get("output_tokens_details", {}) or {}).get("reasoning_tokens", 0)),
                        tokens_total=int(u.get("total_tokens", 0)),
                    )
            except Exception:
                usage_obj = None
            self._responses.append(response)

            if "output" not in response and self.debug:
                print(response)
                raise ValueError("No output from model")
            else:
                # Save the entire response under responses directory
                response_filename = self.responses_dir / f"{self.step_counter:03d}_response.json"
                with open(response_filename, "w", encoding="utf-8") as f:
                    json.dump(response, f, ensure_ascii=False, indent=2)
                new_items += response["output"]
                for item in response["output"]:
                    print(item)
                    new_items += self.handle_item(item)

                # Compute reasoning summary and message text from this response
                reasoning_summary = None
                message_text = None
                try:
                    for out in response.get("output", []):
                        if out.get("type") == "reasoning":
                            summary = out.get("summary")
                            if isinstance(summary, list) and summary and isinstance(summary[0], dict):
                                reasoning_summary = summary[0].get("text")
                        if out.get("type") == "message":
                            content = out.get("content", [])
                            if content and isinstance(content, list) and "text" in content[0]:
                                message_text = content[0]["text"]
                except Exception:
                    pass

                turn_finished_at = datetime.now(timezone.utc)
                turn_elapsed = (turn_finished_at - turn_started_at).total_seconds()
                try:
                    run_elapsed = (turn_finished_at - run_started_at).total_seconds() if run_started_at else turn_elapsed
                except Exception:
                    run_elapsed = turn_elapsed
                turn_extra = {
                    "response_id": self._last_response_id,
                    "usage": usage_obj.to_dict() if usage_obj else None,
                    "reasoning_summary": reasoning_summary,
                    "message_text": message_text,
                    "action": {
                        "type": getattr(self._last_action.type, "value", None) if self._last_action else None,
                        "params": self._last_action.params if self._last_action else None,
                        "call_id": self._last_action.call_id if self._last_action else None,
                        "status": self._last_action.status if self._last_action else None,
                        "safety_checks": self._last_action.safety_checks if self._last_action else None,
                    } if self._last_action else None,
                    "screenshot_path": str(self._last_screenshot_path) if self._last_screenshot_path else None,
                    "started_at": turn_started_at.isoformat(),
                    "finished_at": turn_finished_at.isoformat(),
                    "elapsed_s": turn_elapsed,
                    "run_elapsed_s": run_elapsed,
                }
                # Persist per-turn interaction JSON immediately
                inter_path = self.interactions_dir / f"{self.step_counter:03d}_interaction.json"
                with open(inter_path, "w", encoding="utf-8") as jf:
                    json.dump(turn_extra, jf, ensure_ascii=False, indent=2)

                # Keep Python objects for final result construction
                self._response_extras.append(
                    {
                        "response_id": self._last_response_id,
                        "usage": usage_obj,
                        "reasoning_summary": reasoning_summary,
                        "message_text": message_text,
                        "action": self._last_action,
                        "screenshot_path": self._last_screenshot_path,
                        "started_at": turn_started_at,
                        "finished_at": turn_finished_at,
                        "elapsed_s": turn_elapsed,
                    }
                )

                # Progress callback after each turn
                if callable(progress_callback):
                    try:
                        progress_callback(
                            {
                                "event": "turn",
                                "step_counter": self.step_counter,
                                "turn_elapsed_s": turn_elapsed,
                                "run_elapsed_s": run_elapsed,
                                "reasoning_summary": reasoning_summary,
                                "message_text": message_text,
                                # Provide latest screenshot path so caller can stream a thumbnail
                                "screenshot_path": str(self._last_screenshot_path) if self._last_screenshot_path else None,
                                "last_action": {
                                    "type": getattr(self._last_action.type, "value", None) if self._last_action else None,
                                    "status": self._last_action.status if self._last_action else None,
                                },
                            }
                        )
                    except Exception:
                        pass

                # Enforce maximum reasoning steps
                turns_completed += 1
                if isinstance(max_reasoning_steps, int) and max_reasoning_steps > 0 and turns_completed >= max_reasoning_steps:
                    raise MaximumReasoningStepsReachedException(
                        f"Maximum reasoning steps reached: {max_reasoning_steps}"
                    )

        return new_items

    def _load_prompt_template(self, prompt_name: str) -> str:
        package_root = Path(__file__).resolve().parent.parent.parent.parent
        prompt_path = package_root / "resources" / "prompts" / f"{prompt_name}.txt"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {prompt_path}")
        return prompt_path.read_text(encoding="utf-8")

    def _render_prompt(
        self,
        template: str,
        requirement: Requirements,
        start_url: str,
        inputs: Optional[Inputs] = None,
    ) -> str:
        rendered = template
        # Simple replacements
        rendered = rendered.replace("{{START_URL}}", start_url)
        rendered = rendered.replace("{{DESCRIPTION}}", requirement.description)
        # Optional blocks handling: remove block if missing
        def replace_optional_block(block_name: str, content: Optional[str]):
            nonlocal rendered
            start_tag = f"[SECTION_{block_name}]"
            end_tag = f"[/SECTION_{block_name}]"
            if content and isinstance(content, str) and content.strip():
                # keep content, remove section markers
                rendered = rendered.replace(start_tag, "").replace(end_tag, "")
                rendered = rendered.replace(f"{{{{{block_name}}}}}", content)
            else:
                # drop entire section
                while start_tag in rendered and end_tag in rendered:
                    start_idx = rendered.index(start_tag)
                    end_idx = rendered.index(end_tag) + len(end_tag)
                    rendered = rendered[:start_idx] + rendered[end_idx:]

        replace_optional_block("TITLE", requirement.title)
        replace_optional_block("SOURCE", requirement.source or "")
        tags_csv = ", ".join(requirement.tags) if requirement.tags else ""
        replace_optional_block("TAGS_CSV", tags_csv)
        # Enum to string value
        replace_optional_block("PRIORITY", getattr(requirement.priority, "value", str(requirement.priority)))
        # Acceptance criteria bullets (support structured criteria)
        try:
            ac_bullets = "\n".join([
                f"- {getattr(c, 'name', '') + ': ' if getattr(c, 'name', '') else ''}{getattr(c, 'text', str(c))}"
                for c in (requirement.acceptance_criteria or [])
            ]) if requirement.acceptance_criteria else ""
        except Exception:
            ac_bullets = ""
        replace_optional_block("ACCEPTANCE_CRITERIA_BULLETS", ac_bullets)
        # User-provided inputs block
        try:
            inputs_block = "\n".join([
                f"- {str(k)}: {str(v)}" for k, v in (inputs.key_value_mapping.items() if inputs and inputs.key_value_mapping else [])
            ]) if (inputs and inputs.key_value_mapping) else ""
        except Exception:
            inputs_block = ""
        replace_optional_block("INPUTS", inputs_block)
        # Collapse excessive blank lines after optional removals
        lines = rendered.splitlines()
        normalized_lines = []
        previous_blank = False
        for line in lines:
            if line.strip() == "":
                if not previous_blank:
                    normalized_lines.append("")
                previous_blank = True
            else:
                normalized_lines.append(line.rstrip())
                previous_blank = False
        rendered = "\n".join(normalized_lines).strip()
        return rendered

    def _extract_json(self, assistant_outputs: list) -> tuple[Optional[dict], Optional[str]]:
        """Return (parsed_json, error_str). Only succeed if valid JSON is present; no heuristics."""
        import re
        from json import JSONDecodeError

        text_segments = []
        for item in assistant_outputs:
            if item.get("type") == "message":
                parts = item.get("content", [])
                if parts and isinstance(parts, list) and "text" in parts[0]:
                    text_segments.append(parts[0]["text"])
        if not text_segments:
            return None, "no_assistant_text"
        full_text = "\n\n".join(text_segments)

        # Strip code fences if present
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", full_text)
        candidate = fenced.group(1) if fenced else full_text

        # Try to find the last JSON object in text
        json_like = re.findall(r"\{[\s\S]*\}", candidate)
        if not json_like:
            return None, "no_json_output"
        last = json_like[-1]

        try:
            parsed = json.loads(last)
            return parsed, None, last
        except JSONDecodeError as e:
            return None, f"json_parse_error: {e}; json_like={json_like}", last

    def _validate_acceptance_criteria_names(self, parsed_json: dict, requirement: Requirements) -> None:
        """Ensure the set of acceptance criteria names in the parsed JSON
        matches the set from the provided requirement. Raise if mismatch."""
        expected_names = {str(c.name).strip() for c in (requirement.acceptance_criteria or [])}
        # Remove one item from expected_names to force a mismatch and trigger the exception (for frontend testing)
        results_list = parsed_json.get("acceptance_criteria_results")
        reported_names = set()
        if isinstance(results_list, list):
            for item in results_list:
                try:
                    name = item.get("criterion_name")
                except Exception:
                    name = None
                if name is None:
                    continue
                reported_names.add(str(name).strip())
        # Compare sets strictly
        print("validating acceptance criteria names")
        print("expected_names", expected_names)
        print("reported_names", reported_names)
        if expected_names != reported_names:
            missing = sorted(expected_names - reported_names)
            extra = sorted(reported_names - expected_names)
            raise AcceptanceCriteriaMismatchException(
                f"Acceptance criteria names mismatch. Missing: {missing}; Extra: {extra}"
            )

    def _derive_status_from_acceptance(self, parsed_json: dict) -> VerificationStatus:
        """Derive overall requirement status from per-criterion results.

        Rules:
        - MET: all acceptance criteria are fulfilled (met == true for every criterion)
        - UNMET: no acceptance criteria are fulfilled (met == false for every criterion)
        - PARTIALLY_MET: at least one fulfilled and at least one not fulfilled
        If results are missing or empty, default to UNMET.
        """
        try:
            results = parsed_json.get("acceptance_criteria_results") or []
            if not isinstance(results, list) or len(results) == 0:
                return VerificationStatus.ERROR
            any_met = False
            any_unmet = False
            for item in results:
                if not isinstance(item, dict):
                    continue
                val = item.get("met")
                if isinstance(val, bool):
                    any_met = any_met or val
                    any_unmet = any_unmet or (not val)
                    continue
                status_raw = str(item.get("status", "")).strip().lower()
                if status_raw in ["met", "pass", "true", "yes", "1"]:
                    any_met = True
                elif status_raw in ["unmet", "fail", "false", "no", "0"]:
                    any_unmet = True
            if any_met and any_unmet:
                return VerificationStatus.PARTIALLY_MET
            if any_met and not any_unmet:
                return VerificationStatus.MET
            if not any_met and any_unmet:
                return VerificationStatus.UNMET
            return VerificationStatus.UNMET
        except Exception:
            return VerificationStatus.ERROR
    def run(
        self,
        requirement: Requirements,
        start_url: str,
        inputs: Optional[Inputs] = None,
        print_steps: bool = True,
        show_images: bool = False,
        debug: bool = False,
        progress_callback: Optional[Callable[[dict], None]] = None,
        max_reasoning_steps: Optional[int] = None,
    ) -> VerficationRunResult:
        print(f"Starting verification for: {requirement.title} ({requirement.id})")
        print(f"Start URL: {start_url} | Prompt: {self.prompt_name}")
        print(f"Max reasoning steps: {max_reasoning_steps}")
        started_at = datetime.now(timezone.utc)
        # Expose run start time to run_full_turn for cumulative runtime
        try:
            self._run_started_at = started_at
        except Exception:
            pass
        # Reset per-run accumulators
        self._usages = []
        self._last_response_id = None
        self._last_action = None
        self._last_screenshot_path = None
        if start_url and hasattr(self.computer, "prepare_browser"):
            print("Preparing browser environment...")
            self.computer.prepare_browser(start_url)

        template = self._load_prompt_template(self.prompt_name)
        user_message = self._render_prompt(template, requirement, start_url, inputs)
        print(f"Prompt message: {user_message}")
        print("Prompt rendered; invoking model...")

        items = []
        items.append({"role": "user", "content": user_message})
        output_items = self.run_full_turn(
            items,
            print_steps=print_steps,
            show_images=show_images,
            debug=debug,
            progress_callback=progress_callback,
            max_reasoning_steps=max_reasoning_steps,
        )
        items += output_items

        if hasattr(self.computer, "cleanup_browser"):
            print("Cleaning up browser environment...")
            self.computer.cleanup_browser()

        finished_at = datetime.now(timezone.utc)
        elapsed_s = (finished_at - started_at).total_seconds()

        print("Parsing model decision...")
        parsed_json, parse_error, last_json = self._extract_json(items)
        status: VerificationStatus = VerificationStatus.UNMET
        current_url = None
        steps_taken = self.step_counter - 2

        # Build interactions per response
        interactions: List[Interaction] = []
        turn_idx = 0

        # Create one Interaction per collected response
        prev_screenshot_path = None
        for idx, extra in enumerate(self._response_extras):
            if idx == 0:
                prev_screenshot_path = extra.get("screenshot_path")
                continue
            interactions.append(
                Interaction.create(
                    turn_index=turn_idx+1,
                    started_at=extra.get("started_at"),
                    finished_at=extra.get("finished_at"),
                    elapsed_s=float(extra.get("elapsed_s", 0.0)),
                    model_response_id=extra.get("response_id"),
                    reasoning_summary=extra.get("reasoning_summary"),
                    message_text=extra.get("message_text"),
                    screenshot_path=prev_screenshot_path,
                    usage=extra.get("usage"),
                    action=extra.get("action"),
                )
            )
            prev_screenshot_path = extra.get("screenshot_path")
            turn_idx += 1

        print(f"Length of Interactions: {len(interactions)}")
        print(f"Length of extras: {len(self._response_extras)}")
        #interactions = interactions[1:]
        print(interactions)

        if parsed_json and isinstance(parsed_json, dict):
            # Compute status from acceptance_criteria_results instead of using model's top-level status
            status = self._derive_status_from_acceptance(parsed_json)
            current_url = parsed_json.get("final_url") or None
        elif parse_error:
            status = VerificationStatus.ERROR

        # Additional validation only when JSON parsed successfully and status is valid
        if parsed_json:
            self._validate_acceptance_criteria_names(parsed_json, requirement)

        # Persist normalized decision if available
        if parsed_json:
            decision_path = self.result_dir / "result.json"
            with open(decision_path, "w", encoding="utf-8") as f:
                json.dump(parsed_json, f, ensure_ascii=False, indent=2)
        if parse_error:
            print(f"Decision parse error: {parse_error}")
            parse_error = parse_error + "last_json: " + last_json
        else:
            status_value = status.name if hasattr(status, "name") else str(status)
            print(f"Verification finished with status: {status_value} in {elapsed_s:.2f}s")

        result = VerficationRunResult(
            requirement=requirement,
            requirement_id=requirement.id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            elapsed_s=elapsed_s,
            start_url=start_url,
            current_url=current_url,
            steps_taken=steps_taken,
            run_dir=self.run_dir,
            model_decision=parsed_json,
            error=parse_error,
            interactions=interactions,
            usage_total=Usage.sum(self._usages) if self._usages else None,
        )
        return result

    def run_all(
        self,
        requirements: List[Requirements],
        start_url: str,
        print_steps: bool = True,
        show_images: bool = False,
        debug: bool = False,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ) -> List[VerficationRunResult]:
        results: List[VerficationRunResult] = []
        for req in requirements:
            results.append(
                self.run(
                    requirement=req,
                    start_url=start_url,
                    print_steps=print_steps,
                    show_images=show_images,
                    debug=debug,
                    progress_callback=progress_callback,
                )
            )
        return results
