from __future__ import annotations

from typing import Optional, Any
from pathlib import Path
from uuid import UUID, uuid4

from gui_spector.models.requirements import (
    Requirements as FWRequirements,
    RequirementsPriority,
    AcceptanceCriterion,
    AcceptanceState,
)
from gui_spector.models.verfication_run_result import VerficationRunResult, VerificationStatus
from gui_spector.models.inputs import Inputs as FWInputs
from .models import Requirement, Setup, VerificationRun, RunInteraction, AcceptanceCriterion as DBAcceptanceCriterion, Inputs as DBInputs


def _create_db_criteria(requirement: Requirement, criteria: list[AcceptanceCriterion] | None) -> None:
    if not criteria:
        return
    objs: list[DBAcceptanceCriterion] = []
    for c in criteria:
        try:
            objs.append(
                DBAcceptanceCriterion(
                    requirement=requirement,
                    name=c.name,
                    text=c.text,
                    state=c.state.value if hasattr(c.state, "value") else str(c.state),
                )
            )
        except Exception:
            continue
    if objs:
        DBAcceptanceCriterion.objects.bulk_create(objs)


def _criteria_from_db(requirement: Requirement) -> list[AcceptanceCriterion]:
    result: list[AcceptanceCriterion] = []
    try:
        items = list(requirement.criteria.all())
    except Exception:
        items = []
    idx = 1
    for it in items:
        try:
            result.append(
                AcceptanceCriterion.create(
                    name=it.name or f"AC-{idx}",
                    text=it.text or "",
                    state=it.state or AcceptanceState.UNPROCESSED,
                )
            )
        except Exception:
            pass
        idx += 1
    return result


def framework_to_model(setup: Setup, r: FWRequirements) -> Requirement:
    return Requirement(
        setup=setup,
        framework_id=r.id if isinstance(r.id, UUID) else uuid4(),
        title=r.title or "",
        description=r.description or "",
        source=r.source,
        tags_json=list(r.tags or []),
        priority=(r.priority.value if isinstance(r.priority, RequirementsPriority) else str(r.priority or "medium")),
        metadata_json=(r.metadata if isinstance(r.metadata, dict) else None),
    )


def model_to_framework(m: Requirement) -> FWRequirements:
    # Priority mapping with safe fallback
    try:
        prio = RequirementsPriority(m.priority)
    except Exception:
        prio = RequirementsPriority.MEDIUM

    # Title/description fallback for legacy `text`
    title = m.title or (m.text or "").split("\n", 1)[0]
    description = m.description or (m.text or "")

    fw = FWRequirements(
        id=m.framework_id or uuid4(),
        created_at=m.created_at,
        title=title,
        description=description,
        source=m.source,
        tags=list(m.tags_json or []),
        priority=prio,
        metadata=(m.metadata_json if isinstance(m.metadata_json, dict) else None),
    )
    # Attach DB criteria after constructing
    try:
        fw.acceptance_criteria = _criteria_from_db(m)
    except Exception:
        pass
    return fw


def create_model_criteria_from_framework(model_req: Requirement, fw_req: FWRequirements) -> None:
    try:
        _create_db_criteria(model_req, list(fw_req.acceptance_criteria or []))
    except Exception:
        pass


def map_status_to_fw(s: str) -> VerificationStatus:
    try:
        return VerificationStatus(s)
    except Exception:
        # Fallback mapping
        if s == "met":
            return VerificationStatus.MET
        if s == "partially_met":
            return VerificationStatus.PARTIALLY_MET
        if s == "error":
            return VerificationStatus.ERROR
        return VerificationStatus.UNMET


def framework_run_to_models(req: Requirement, fw: VerficationRunResult) -> tuple[VerificationRun, list[RunInteraction]]:
    run = VerificationRun(
        requirement=req,
        status=fw.status.value if hasattr(fw.status, "value") else str(fw.status),
        started_at=fw.started_at,
        finished_at=fw.finished_at,
        elapsed_s=fw.elapsed_s,
        start_url=fw.start_url,
        current_url=fw.current_url or None,
        steps_taken=fw.steps_taken,
        run_dir=str(fw.run_dir),
        model_decision_json=fw.model_decision or None,
        error=fw.error or None,
        usage_total_json=(fw.usage_total.__dict__ if hasattr(fw.usage_total, "__dict__") else None),
    )

    # Determine last screenshot path from the run's images directory
    try:
        images_dir = Path(fw.run_dir) / "images"
        if images_dir.exists():
            pngs = sorted([p for p in images_dir.iterdir() if p.is_file() and p.suffix.lower() == ".png"])
            if pngs:
                run.last_screenshot = str(pngs[-1])
    except Exception:
        pass

    interactions: list[RunInteraction] = []
    for it in fw.interactions or []:
        action = getattr(it, "action", None)
        interactions.append(
            RunInteraction(
                run=run,
                turn_index=it.turn_index,
                started_at=it.started_at,
                finished_at=it.finished_at,
                elapsed_s=it.elapsed_s,
                model_response_id=it.model_response_id or None,
                reasoning_summary=it.reasoning_summary or None,
                message_text=it.message_text or None,
                screenshot_path=str(it.screenshot_path) if getattr(it, "screenshot_path", None) else None,
                usage_json=(it.usage.__dict__ if getattr(it, "usage", None) else None),
                action_type=(action.type.value if getattr(action, "type", None) else None),
                action_params_json=(action.params if getattr(action, "params", None) else None),
                action_call_id=(action.call_id if getattr(action, "call_id", None) else None),
                action_status=(action.status if getattr(action, "status", None) else None),
                action_safety_checks_json=(action.safety_checks if getattr(action, "safety_checks", None) else None),
            )
        )
    return run, interactions


def verificationrun_status_to_requirement_status(vrun_status: str) -> str:
    """
    Map VerificationRun.status (string) to Requirement.Status (string).
    1:1 mapping for all VerificationRun.Status values.
    """
    from .models import Requirement, VerificationRun
    # Normalize input to the raw string value
    try:
        vs = vrun_status.value  # TextChoices or Enum
    except Exception:
        vs = str(vrun_status)
    if vs == VerificationRun.Status.MET:
        return Requirement.Status.MET
    if vs == VerificationRun.Status.PARTIALLY_MET:
        return Requirement.Status.PARTIALLY_MET
    if vs == VerificationRun.Status.MET:
        return Requirement.Status.MET
    if vs == VerificationRun.Status.PARTIALLY_MET:
        return Requirement.Status.PARTIALLY_MET
    if vs == VerificationRun.Status.UNMET:
        return Requirement.Status.UNMET
    if vs == VerificationRun.Status.ERROR:
        return Requirement.Status.ERROR
    if vs == VerificationRun.Status.PROCESSING:
        return Requirement.Status.PROCESSING
    # Fallbacks for legacy or unmapped states
    if vs == Requirement.Status.UNPROCESSED:
        return Requirement.Status.UNPROCESSED
    return Requirement.Status.UNMET


def inputs_model_to_framework(setup: Setup) -> FWInputs | None:
    """Map optional Setup.inputs to framework Inputs.

    Returns None when no inputs configured.
    """
    try:
        db_inputs: DBInputs | None = getattr(setup, "inputs", None)
    except Exception:
        db_inputs = None
    if not db_inputs:
        return None
    try:
        mapping = db_inputs.mapping_json or {}
        if not isinstance(mapping, dict):
            return None
        # Coerce to string->string
        normalized: dict[str, str] = {str(k): str(v) for k, v in mapping.items()}
        return FWInputs.create(initial=normalized)
    except Exception:
        return None