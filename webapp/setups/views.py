from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import Setup, Requirement, VerificationRun, RunInteraction, Inputs
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.conf import settings
from pathlib import Path
from .forms import SetupForm, SetupEditForm
from django.core.files.base import ContentFile
from .screenshot import PlaywrightScreenshotter
from gui_spector.processor.app_extractor import AppExtractor
from gui_spector.processor.requirements_processor import RequirementsProcessor
from gui_spector.models.requirements import RequirementsPriority
from .mappers import framework_to_model, framework_run_to_models, create_model_criteria_from_framework
from .tasks import run_verification_task
from gui_spector.llm.llm import LLM
from gui_spector.llm.config import AVAILABLE_MODELS
from gui_spector.verfication.config import AVAILABLE_AGENTS, DEFAULT_AGENT
from django.db import transaction
from settings.models import set_api_keys_from_settings
import json


@ensure_csrf_cookie
def overview(request):
    return render(request, "setups/overview.html")


@require_http_methods(["GET"])
def api_list_setups(request):
    print("api_list_setups")
    setups = (
        Setup.objects.all()
        .select_related()
        .prefetch_related("requirements")
    )
    results = []
    for s in setups:
        results.append(
            {
                "id": s.id,
                "name": s.name,
                "created_at": timezone.localtime(s.created_at).strftime("%Y-%m-%d %H:%M"),
                "state": s.state or Setup.State.READY,
                "screenshot": s.screenshot.url if s.screenshot else "",
                "num_requirements": s.num_requirements,
                "num_met": s.num_met,
                "num_unmet": s.num_unmet,
                "num_partially_met": s.num_partially_met,
                "num_processing": s.num_processing,
                "num_unprocessed": s.num_unprocessed,
                "num_error": s.num_error,
                "tags": list(s.tags_json or []),
            }
        )
    print("results", results)
    return JsonResponse({"setups": results})


@require_http_methods(["GET", "POST"])
def add_setup(request):
    # Determine selected LLM (defaults to GPT-4.1) and validate against AVAILABLE_MODELS
    # Ensure API keys from latest settings are applied before any LLM usage
    try:
        set_api_keys_from_settings()
    except Exception:
        pass
    default_llm = LLM.MODEL_GPT_4_1
    valid_llms = [v for (v, _d) in AVAILABLE_MODELS]
    selected_llm = request.POST.get("llm_model") if request.method == "POST" else default_llm
    if selected_llm not in valid_llms:
        selected_llm = default_llm

    # Determine selected Agent (defaults configured) and validate
    valid_agents = [v for (v, _d) in AVAILABLE_AGENTS]
    selected_agent = request.POST.get("agent_model") if request.method == "POST" else DEFAULT_AGENT
    if selected_agent not in valid_agents:
        selected_agent = DEFAULT_AGENT

    # Build reasoning steps options (10..120 by 10)
    reasoning_options = [(i, str(i)) for i in range(10, 121, 10)] + [(5, "5")]

    if request.method == "POST":
        form = SetupForm(request.POST)
        if form.is_valid():
            # Save Setup
            setup = form.save()
            # Persist selected llm_model explicitly in case of tampering/defaults
            try:
                if selected_llm and setup.llm_model != selected_llm:
                    setup.llm_model = selected_llm
                    setup.save(update_fields=["llm_model"])
                if selected_agent and setup.agent_model != selected_agent:
                    setup.agent_model = selected_agent
                    setup.save(update_fields=["agent_model"])
            except Exception:
                pass
            # Try to capture a screenshot of the start_url
            try:
                print(f"Capturing screenshot for {setup.start_url}")
                shooter = PlaywrightScreenshotter()
                img_bytes = shooter.capture_to_bytes(setup.start_url)
                if img_bytes:
                    setup.screenshot.save(f"setup_{setup.pk}.png", ContentFile(img_bytes), save=True)
                # Always run AppExtractor to get description and (optionally) tags
                try:
                    try:
                        set_api_keys_from_settings()
                    except Exception:
                        pass
                    updates = []
                    extractor = AppExtractor(llm=LLM(model_name=selected_llm, temperature=0.05))
                    # Use the raw input to help the model infer high-level details
                    req_text = form.cleaned_data.get("requirements_input", "") or ""
                    result = extractor.extract_app(
                        image_bytes=img_bytes,
                        image_url=None,
                        requirements=None,
                        requirements_text=req_text,
                        max_tags=7,
                    )
                    # Always set description when provided by extractor
                    if result and getattr(result, "description", None):
                        setup.description = result.description
                        updates.append("description")
                    # Determine final tags: user provided or extracted
                    raw_tags = (form.cleaned_data.get("tags_input") or "").strip()
                    if raw_tags:
                        tags = [t.strip() for t in raw_tags.replace(";", ",").split(",") if t.strip()]
                        setup.tags_json = tags
                        updates.append("tags_json")
                    elif result and getattr(result, "tags", None):
                        setup.tags_json = list(result.tags)
                        updates.append("tags_json")
                    if updates:
                        setup.save(update_fields=updates)
                except Exception as te:
                    print(f"Error extracting/applying tags/description: {te}")
            except Exception as e:
                print(f"Error capturing screenshot: {e}")
            # Use RequirementsProcessor to extract structured requirements from textarea
            req_text = form.cleaned_data.get("requirements_input", "") or ""
            if req_text.strip():
                try:
                    set_api_keys_from_settings()
                except Exception:
                    pass
                processor = RequirementsProcessor(llm=LLM(model_name=selected_llm, temperature=0.05))
                extracted = processor.process_text(
                    input_text=req_text,
                    allow_guess=bool(form.cleaned_data.get("allow_guess")),
                    default_priority=RequirementsPriority.MEDIUM,
                    source=setup.start_url,
                )
                bulk = [framework_to_model(setup, r) for r in extracted]
                if bulk:
                    Requirement.objects.bulk_create(bulk)
                    # Create related acceptance criteria per requirement
                    created = list(Requirement.objects.filter(setup=setup, framework_id__in=[b.framework_id for b in bulk]))
                    fw_map = {str(r.id): r for r in extracted}
                    for mr in created:
                        fwr = fw_map.get(str(mr.framework_id))
                        if fwr:
                            create_model_criteria_from_framework(mr, fwr)
            # Persist Inputs mapping if provided
            try:
                raw_inputs = (request.POST.get("inputs_json") or "").strip()
                if raw_inputs:
                    data = json.loads(raw_inputs)
                    mapping = {}
                    if isinstance(data, list):
                        for it in data:
                            try:
                                key = str((it.get("key") or "").strip())
                                val = str(it.get("value") if it.get("value") is not None else "")
                            except Exception:
                                continue
                            if key:
                                mapping[key] = val
                    elif isinstance(data, dict):
                        mapping = {str(k): str(v) for k, v in data.items()}
                    if mapping:
                        db_inputs = Inputs.objects.create(mapping_json=mapping)
                        setup.inputs = db_inputs
                        setup.save(update_fields=["inputs"])
            except Exception as e:
                # Do not fail on inputs parsing errors
                print(f"Failed to parse inputs_json: {e}")
            return redirect("setups:open", pk=setup.pk)
    else:
        form = SetupForm(initial={"llm_model": selected_llm, "agent_model": selected_agent})
    return render(request, "setups/add.html", {"form": form, "agent_options": AVAILABLE_AGENTS, "default_agent": selected_agent, "llm_options": AVAILABLE_MODELS, "default_llm": selected_llm, "reasoning_step_options": reasoning_options})


@ensure_csrf_cookie
def open_setup(request, pk: int):
    setup = get_object_or_404(Setup, pk=pk)
    return render(request, "setups/detail.html", {"setup": setup})
@require_http_methods(["GET", "POST"])
def edit_setup(request, pk: int):
    setup = get_object_or_404(Setup, pk=pk)
    if request.method == "POST":
        form = SetupEditForm(request.POST, instance=setup)
        if form.is_valid():
            obj = form.save(commit=False)
            # Parse tags_input into tags_json
            raw_tags = (form.cleaned_data.get("tags_input") or "").strip()
            tags = [t.strip() for t in raw_tags.replace(";", ",").split(",") if t.strip()]
            obj.tags_json = tags
            obj.save()
            # Persist Inputs mapping if provided
            try:
                raw_inputs = (request.POST.get("inputs_json") or "").strip()
                mapping = {}
                if raw_inputs:
                    data = json.loads(raw_inputs)
                    if isinstance(data, list):
                        for it in data:
                            try:
                                key = str((it.get("key") or "").strip())
                                val = str(it.get("value") if it.get("value") is not None else "")
                            except Exception:
                                continue
                            if key:
                                mapping[key] = val
                    elif isinstance(data, dict):
                        mapping = {str(k): str(v) for k, v in data.items()}
                # Update or create/delete Inputs
                if mapping:
                    if getattr(obj, "inputs", None):
                        obj.inputs.mapping_json = mapping
                        obj.inputs.save(update_fields=["mapping_json",])
                    else:
                        from .models import Inputs as DBInputs
                        obj.inputs = DBInputs.objects.create(mapping_json=mapping)
                    obj.save(update_fields=["inputs"]) 
                else:
                    # If empty mapping, clear existing mapping
                    if getattr(obj, "inputs", None):
                        obj.inputs.mapping_json = {}
                        obj.inputs.save(update_fields=["mapping_json"]) 
            except Exception as e:
                print(f"Failed to parse inputs_json (edit): {e}")
            return redirect("setups:open", pk=setup.pk)
    else:
        initial = {"tags_input": ", ".join(setup.tags_json or [])}
        form = SetupEditForm(instance=setup, initial=initial)
    # Provide dropdown options similar to Add page
    # Build initial inputs array for editor
    try:
        mapping = (setup.inputs.mapping_json if getattr(setup, "inputs", None) else {}) or {}
        if isinstance(mapping, dict):
            initial_inputs_list = [{"key": str(k), "value": str(v)} for k, v in mapping.items()]
        else:
            initial_inputs_list = []
    except Exception:
        initial_inputs_list = []
    return render(request, "setups/edit.html", {
        "form": form,
        "setup": setup,
        "agent_options": AVAILABLE_AGENTS,
        "default_agent": setup.agent_model,
        "llm_options": AVAILABLE_MODELS,
        "default_llm": setup.llm_model,
        "initial_inputs_json": json.dumps(initial_inputs_list),
    })



@require_http_methods(["GET"])
def api_requirements(request, pk: int):
    setup = get_object_or_404(Setup, pk=pk)
    q = setup.requirements.all().order_by("created_at")

    results = []
    for idx, r in enumerate(q, start=1):
        results.append(
            {
                "id": r.id,
                "index": idx,
                "title": r.title,
                "description": r.description,
                "priority": r.priority,
                "tags": list(r.tags_json or []),
                "created_at": timezone.localtime(r.created_at).strftime("%Y-%m-%d"),
                "status": r.status,
            }
        )
    return JsonResponse({"requirements": results})


@require_http_methods(["POST"])
def api_requirements_add(request, pk: int):
    # Ensure API keys from latest settings are applied before any LLM usage
    set_api_keys_from_settings()
    setup = get_object_or_404(Setup, pk=pk)
    # New flow: extract multiple requirements from free text via RequirementsProcessor
    raw_text = (request.POST.get("requirements_input") or "").strip()
    if raw_text:
        allow_guess = True if str(request.POST.get("allow_guess", "true")).lower() in ["1", "true", "yes", "on"] else False
        processor = RequirementsProcessor()
        extracted = processor.process_text(
            input_text=raw_text,
            allow_guess=allow_guess,
            default_priority=RequirementsPriority.MEDIUM,
            source=setup.start_url,
        )
        print(f"Extracted: {extracted}")
        to_create = [framework_to_model(setup, r) for r in extracted]
        if not to_create:
            return JsonResponse({"created": []})
        # Keep track of framework IDs to reliably fetch after bulk_create
        fw_ids = [obj.framework_id for obj in to_create]
        Requirement.objects.bulk_create(to_create)
        # Create criteria per requirement
        created_qs = list(Requirement.objects.filter(setup=setup, framework_id__in=fw_ids).order_by("created_at"))
        # Build mapping by framework_id string
        fw_map = {str(fr.id): fr for fr in extracted}
        for mr in created_qs:
            fw_req = fw_map.get(str(mr.framework_id))
            if fw_req:
                create_model_criteria_from_framework(mr, fw_req)
        created_payload = []
        for r in created_qs:
            created_payload.append({
                "id": r.id,
                "title": r.title,
                "description": r.description,
                "priority": r.priority,
                "tags": list(r.tags_json or []),
                "created_at": timezone.localtime(r.created_at).strftime("%Y-%m-%d"),
                "status": r.status,
            })
        return JsonResponse({"created": created_payload})

    # Back-compat: accept single manual requirement fields
    title = (request.POST.get("title") or "").strip()
    description = (request.POST.get("description") or "").strip()
    priority = (request.POST.get("priority") or Requirement.Priority.MEDIUM).strip()
    tags = request.POST.getlist("tags[]") or []
    if not title and not description:
        return HttpResponseBadRequest("No input provided")
    r = Requirement.objects.create(
        setup=setup,
        title=title,
        description=description,
        priority=priority if priority in dict(Requirement.Priority.choices) else Requirement.Priority.MEDIUM,
        tags_json=tags,
        status=Requirement.Status.UNPROCESSED,
    )
    return JsonResponse({
        "created": [{
            "id": r.id,
            "title": r.title,
            "description": r.description,
            "priority": r.priority,
            "tags": list(r.tags_json or []),
            "created_at": timezone.localtime(r.created_at).strftime("%Y-%m-%d"),
            "status": r.status,
        }]
    })


@require_http_methods(["POST", "DELETE"]) 
def api_requirements_delete(request, pk: int, req_id: int):
    setup = get_object_or_404(Setup, pk=pk)
    r = get_object_or_404(Requirement, pk=req_id, setup=setup)
    r.delete()
    return JsonResponse({"ok": True})


@require_http_methods(["POST", "DELETE"])
def api_requirements_delete_all(request, pk: int):
    setup = get_object_or_404(Setup, pk=pk)
    # Delete all requirements and cascaded runs for this setup
    with transaction.atomic():
        Requirement.objects.filter(setup=setup).delete()
    return JsonResponse({"ok": True})


@require_http_methods(["GET"])
def api_setup_summary(request, pk: int):
    """Aggregate latest run detailed summaries for each requirement in a setup.

    Returns a combined plain text with each section containing:
    Requirements Text (title or description) followed by the detailed summary.
    Sections are separated by an em dash divider.
    """
    setup = get_object_or_404(Setup, pk=pk)
    requirements = setup.requirements.all().order_by("created_at")
    # Optional filter: comma-separated statuses in query param, e.g. ?statuses=unmet,partially_met
    statuses_raw = (request.GET.get("statuses") or "").strip()
    allowed_statuses: set[str] = set()
    if statuses_raw:
        try:
            allowed_statuses = set([s.strip() for s in statuses_raw.split(",") if s.strip()])
        except Exception:
            allowed_statuses = set()
    parts: list[str] = []

    for r in requirements:
        latest = (
            VerificationRun.objects.filter(requirement=r)
            .order_by("-created_at")
            .first()
        )
        if not latest:
            continue
        try:
            decision = latest.model_decision_json or {}
        except Exception:
            decision = {}
        # Skip if status filter provided and latest run status not in allowed set
        if allowed_statuses:
            try:
                status_raw = latest.status if isinstance(latest.status, str) else str(latest.status)
            except Exception:
                status_raw = str(latest.status)
            if status_raw not in allowed_statuses:
                continue
        # Broad support for possible keys
        detailed = None
        if isinstance(decision, dict):
            detailed = (
                decision.get("detailed_summary")
                or decision.get("details")
                or decision.get("summary_detailed")
                or decision.get("detailed")
                or decision.get("summary")
            )
        if not detailed:
            continue

        req_text = (r.title or "").strip()
        if not req_text:
            req_text = (r.description or "").strip()
        if not req_text:
            req_text = f"Requirement #{r.pk}"

        # Normalize status text for display (met, partially_met, unmet, error, processing)
        try:
            status_raw = latest.status if isinstance(latest.status, str) else str(latest.status)
        except Exception:
            status_raw = str(latest.status)
        status_disp = (status_raw or "").strip().lower()
        parts.append(f"{req_text} ({status_disp})\n{detailed}")

    combined = ("\n\n---\n\n".join(parts)) if parts else ""
    return JsonResponse({"text": combined, "count": len(parts)})


@require_http_methods(["GET"])
def api_requirement_summary(request, req_id: int):
    """Return the latest run detailed summary for a single requirement."""
    req = get_object_or_404(Requirement, pk=req_id)
    latest = (
        VerificationRun.objects.filter(requirement=req)
        .order_by("-created_at")
        .first()
    )
    if not latest:
        return JsonResponse({"text": "", "count": 0})
    try:
        decision = latest.model_decision_json or {}
    except Exception:
        decision = {}
    detailed = None
    if isinstance(decision, dict):
        detailed = (
            decision.get("detailed_summary")
            or decision.get("details")
            or decision.get("summary_detailed")
            or decision.get("detailed")
            or decision.get("summary")
        )
    if not detailed:
        return JsonResponse({"text": "", "count": 0})

    req_text = (req.title or "").strip()
    if not req_text:
        req_text = (req.description or "").strip()
    if not req_text:
        req_text = f"Requirement #{req.pk}"

    try:
        status_raw = latest.status if isinstance(latest.status, str) else str(latest.status)
    except Exception:
        status_raw = str(latest.status)
    status_disp = (status_raw or "").strip().lower()
    combined = f"{req_text} ({status_disp})\n{detailed}"
    return JsonResponse({"text": combined, "count": 1, "status": status_disp})


def runs_overview(request, req_id: int):
    req = get_object_or_404(Requirement, pk=req_id)
    # Provide acceptance criteria for header rendering (relational preferred, legacy JSON fallback)
    ac_list: list[dict] = []
    # Try relational criteria first
    try:
        for crit in req.criteria.all():
            # Combine name and text for concise display
            combined = f"{crit.name}: {crit.text}" if getattr(crit, "name", "") else getattr(crit, "text", "")
            if combined:
                st = (getattr(crit, "state", "") or "").strip().lower()
                met_val = True if st == "met" else (False if st == "unmet" else None)
                ac_list.append({"criteria": combined, "met": met_val})
    except Exception:
        pass
    # Fallback to legacy JSON if relational not present
    if not ac_list:
        try:
            raw = list(getattr(req, "acceptance_criteria_json", []) or [])
            idx = 1
            for item in raw:
                if isinstance(item, str):
                    ac_list.append({"criteria": f"AC-{idx}: {item}", "met": None})
                    idx += 1
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("criteria") or item.get("name") or item.get("description") or ""
                    if text:
                        ac_list.append({"criteria": f"AC-{idx}: {text}", "met": None})
                        idx += 1
        except Exception:
            pass
    return render(request, "setups/runs_overview.html", {"requirement": req, "requirement_ac_list": ac_list})


@require_http_methods(["GET"])
def api_runs_list(request, req_id: int):
    req = get_object_or_404(Requirement, pk=req_id)
    runs = (
        VerificationRun.objects.filter(requirement=req)
        .prefetch_related("interactions")
        .order_by("-created_at")
    )
    media_root = Path(getattr(settings, "MEDIA_ROOT", "")).resolve() if getattr(settings, "MEDIA_ROOT", None) else None
    media_url = getattr(settings, "MEDIA_URL", "/media/")
    if not media_url.endswith("/"):
        media_url = media_url + "/"

    def _to_media_url(raw_path: str) -> str:
        if not raw_path:
            return ""
        s = str(raw_path)
        s_norm = s.replace("\\", "/")
        if s_norm.startswith("http://") or s_norm.startswith("https://"):
            return s_norm
        idx = s_norm.find("/media/")
        if idx != -1:
            return s_norm[idx:]
        try:
            if media_root:
                rel = Path(s_norm).resolve().relative_to(media_root)
                return media_url + str(rel).replace("\\", "/")
        except Exception:
            pass
        parts = [p for p in s_norm.split("/") if p]
        if "media" in parts:
            m_idx = parts.index("media")
            tail = "/".join(parts[m_idx+1:])
            return media_url + tail
        return s_norm
    payload = []
    for r in runs:
        # Derive UI status: if run is marked processing but no display assigned yet, show waiting state
        try:
            status_raw = r.status if isinstance(r.status, str) else str(r.status)
        except Exception:
            status_raw = str(r.status)
        status_ui = status_raw
        try:
            if status_raw == VerificationRun.Status.PROCESSING and not r.display_str:
                status_ui = "waiting_for_display"
        except Exception:
            # Fallback compare to string literal
            if status_raw == "processing" and not r.display_str:
                status_ui = "waiting_for_display"
        # Extract token usage from usage_total_json if available
        usage = r.usage_total_json or {}
        def _num_or_none(val):
            try:
                if val is None:
                    return None
                if isinstance(val, (int, float)):
                    return int(val)
                return int(str(val).strip())
            except Exception:
                return None
        tokens_in = _num_or_none(usage.get("tokens_in"))
        tokens_out = _num_or_none(usage.get("tokens_out"))
        tokens_in_fmt = f"{tokens_in:,}" if tokens_in is not None else None
        tokens_out_fmt = f"{tokens_out:,}" if tokens_out is not None else None
        # Extract concise explanation from model decision json, if present
        try:
            decision = r.model_decision_json or {}
        except Exception:
            decision = {}
        explanation = (
            (decision.get("explanation") if isinstance(decision.get("explanation"), str) else None)
            or (decision.get("explanation_summary") if isinstance(decision.get("explanation_summary"), str) else None)
            or (decision.get("why") if isinstance(decision.get("why"), str) else None)
            or ""
        )

        payload.append(
            {
                "id": r.id,
                "status": status_ui,
                "created_at": timezone.localtime(r.created_at).strftime("%Y-%m-%d %H:%M"),
                "started_at": timezone.localtime(r.started_at).strftime("%Y-%m-%d %H:%M:%S"),
                "finished_at": timezone.localtime(r.finished_at).strftime("%Y-%m-%d %H:%M:%S"),
                "elapsed_s": r.elapsed_s,
                "steps_taken": r.steps_taken,
                "start_url": r.start_url,
                "current_url": r.current_url or "",
                "error": r.error or "",
                "last_screenshot_url": _to_media_url(r.last_screenshot or ""),
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "tokens_in_fmt": tokens_in_fmt,
                "tokens_out_fmt": tokens_out_fmt,
                "explanation": explanation,
            }
        )
    return JsonResponse({"runs": payload})


@require_http_methods(["GET"])
def api_requirement_latest_decision(request, req_id: int):
    """Return the latest run's model_decision_json for a requirement, or null if none."""
    req = get_object_or_404(Requirement, pk=req_id)
    latest = (
        VerificationRun.objects.filter(requirement=req)
        .order_by("-created_at")
        .first()
    )
    decision = latest.model_decision_json if latest and latest.model_decision_json else None
    status = latest.status if latest else None
    return JsonResponse({
        "requirement_id": req.id,
        "status": status,
        "model_decision_json": decision,
    })


@require_http_methods(["POST"])
def api_runs_start(request, req_id: int):
    req = get_object_or_404(Requirement, pk=req_id)
    setup = req.setup
    # Enqueue async task
    async_result = run_verification_task.delay(req.id)
    return JsonResponse({"started": True, "task_id": async_result.id})


@require_http_methods(["POST"])
def api_runs_start_all(request, pk: int):
    setup = get_object_or_404(Setup, pk=pk)
    reqs = setup.requirements.all()
    tasks = []
    for r in reqs:
        try:
            async_result = run_verification_task.delay(r.id)
            tasks.append({"requirement_id": r.id, "task_id": async_result.id})
        except Exception:
            tasks.append({"requirement_id": r.id, "task_id": None, "error": True})
    return JsonResponse({"started": True, "tasks": tasks})


def run_detail(request, run_id: int):
    run = get_object_or_404(
        VerificationRun.objects.select_related("requirement", "requirement__setup").prefetch_related("interactions"),
        pk=run_id,
    )
    requirement = run.requirement
    # Build a simple dict for interactions to avoid heavy logic in template
    media_root = Path(getattr(settings, "MEDIA_ROOT", "")).resolve() if getattr(settings, "MEDIA_ROOT", None) else None
    media_url = getattr(settings, "MEDIA_URL", "/media/")
    if not media_url.endswith("/"):
        media_url = media_url + "/"

    def _to_media_url(raw_path: str) -> str:
        if not raw_path:
            return ""
        s = str(raw_path)
        s_norm = s.replace("\\", "/")
        # Already a URL
        if s_norm.startswith("http://") or s_norm.startswith("https://"):
            return s_norm
        # If it already contains /media/, slice from there
        idx = s_norm.find("/media/")
        if idx != -1:
            return s_norm[idx:]
        # Try MEDIA_ROOT relative mapping
        try:
            if media_root:
                rel = Path(s_norm).resolve().relative_to(media_root)
                return media_url + str(rel).replace("\\", "/")
        except Exception:
            pass
        # As a fallback, locate 'media' path segment
        parts = [p for p in s_norm.split("/") if p]
        if "media" in parts:
            m_idx = parts.index("media")
            tail = "/".join(parts[m_idx+1:])
            return media_url + tail
        # Last resort: treat as already absolute path under server; return as-is
        return s_norm

    def _clean_message_text(text: str) -> str:
        try:
            if not text:
                return ""
            t = str(text).strip()
            # Hide JSON/code-fenced content
            if (t.startswith("{") and t.endswith("}")) or "```" in t:
                return ""
            # Heuristic: contains typical JSON keys
            if '"status"' in t and ('{"' in t or '\n{' in t):
                return ""
            return t
        except Exception:
            return ""

    # Helper: safely coerce token counts to int or None
    def _num_or_none(val):
        try:
            if val is None:
                return None
            if isinstance(val, (int, float)):
                return int(val)
            return int(str(val).strip())
        except Exception:
            return None

    interactions = []
    for it in run.interactions.all().order_by("turn_index"):
        raw_path = it.screenshot_path or ""
        screenshot_url = _to_media_url(raw_path)
        msg_text = _clean_message_text(it.message_text or "")
        # Per-interaction token usage (formatted like header)
        usage_obj = it.usage_json or {}
        ti_val = _num_or_none(usage_obj.get("tokens_in"))
        to_val = _num_or_none(usage_obj.get("tokens_out"))
        ti_fmt = f"{ti_val:,}" if ti_val is not None else None
        to_fmt = f"{to_val:,}" if to_val is not None else None
        interactions.append(
            {
                "turn_index": it.turn_index,
                "started_at": timezone.localtime(it.started_at).strftime("%Y-%m-%d %H:%M:%S"),
                "finished_at": timezone.localtime(it.finished_at).strftime("%Y-%m-%d %H:%M:%S"),
                "elapsed_s": it.elapsed_s,
                "model_response_id": it.model_response_id or "",
                "reasoning_summary": it.reasoning_summary or "",
                "message_text": msg_text,
                "screenshot_url": screenshot_url,
                "usage": it.usage_json or None,
                "tokens_in": ti_val,
                "tokens_out": to_val,
                "tokens_in_fmt": ti_fmt,
                "tokens_out_fmt": to_fmt,
                "action": {
                    "type": it.action_type,
                    "params": it.action_params_json,
                    "call_id": it.action_call_id,
                    "status": it.action_status,
                    "safety_checks": it.action_safety_checks_json,
                },
            }
        )
    # Compute formatted token usage (American thousands separator) for header

    usage = run.usage_total_json or {}
    tokens_in_val = _num_or_none(usage.get("tokens_in"))
    tokens_out_val = _num_or_none(usage.get("tokens_out"))
    tokens_present = (tokens_in_val is not None) or (tokens_out_val is not None)
    tokens_in_fmt = f"{tokens_in_val:,}" if tokens_in_val is not None else "-"
    tokens_out_fmt = f"{tokens_out_val:,}" if tokens_out_val is not None else "-"

    context = {
        "run": run,
        "requirement": requirement,
        "interactions": interactions,
        "tokens_present": tokens_present,
        "tokens_in_fmt": tokens_in_fmt,
        "tokens_out_fmt": tokens_out_fmt,
    }

    # Normalize model decision for UI
    decision = run.model_decision_json or {}
    ui_summary = {
        "status": decision.get("status"),
        "final_url": decision.get("final_url"),
        "explanation": decision.get("explanation") or decision.get("explanation_summary") or decision.get("why"),
        "detailed": decision.get("detailed_summary") or decision.get("details") or decision.get("summary_detailed"),
        "acceptance": [],
    }
    # Map criterion_name -> stored text for richer display
    name_to_text = {}
    try:
        for c in requirement.criteria.all():
            n = (getattr(c, "name", "") or "").strip().upper()
            if n:
                name_to_text[n] = getattr(c, "text", "") or ""
    except Exception:
        pass
    # Broadly support different schema variants for acceptance results
    ac = (
        decision.get("acceptance_criteria")
        or decision.get("acceptance")
        or decision.get("acceptanceCriteria")
        or decision.get("criteria_results")
        or decision.get("acceptance_results")
        or decision.get("acceptance_criteria_results")
        or decision.get("criteria")
        or decision.get("results")
        or []
    )
    if isinstance(ac, dict) and "items" in ac and isinstance(ac["items"], list):
        ac = ac["items"]
    if isinstance(ac, list):
        for item in ac:
            if isinstance(item, dict):
                nm = item.get("criterion_name") or item.get("name")
                txt = item.get("criteria") or item.get("criterion") or item.get("text") or item.get("description")
                if nm and not txt:
                    txt = name_to_text.get(str(nm).strip().upper()) or ""
                display = (f"{nm}: {txt}" if nm and txt else (txt or nm or ""))
                met_val = item.get("met") if isinstance(item.get("met"), bool) else None
                if met_val is None:
                    met_val = str(item.get("status", "")).strip().lower() in ["met", "pass", "true", "yes"]
                ui_summary["acceptance"].append({
                    "criteria": display,
                    "met": met_val,
                    "explanation": item.get("explanation") or item.get("why") or item.get("notes") or item.get("reason") or "",
                    "evidence": item.get("evidence") or item.get("evidence_text") or item.get("proof") or "",
                })
            elif isinstance(item, str):
                ui_summary["acceptance"].append({"criteria": item, "met": None, "explanation": "", "evidence": ""})
    elif isinstance(ac, dict):
        for key, val in ac.items():
            ui_summary["acceptance"].append({
                "criteria": key,
                "met": bool(val) if isinstance(val, (bool, int)) else (str(val).lower() in ["met", "pass", "true", "yes"]),
                "explanation": "",
                "evidence": "",
            })
    # Fallback to requirement's acceptance criteria if none parsed
    if not ui_summary["acceptance"]:
        try:
            for crit in requirement.criteria.all():
                ui_summary["acceptance"].append({
                    "criteria": f"{crit.name}: {crit.text}" if crit.name else crit.text,
                    "met": None,
                    "explanation": "",
                    "evidence": "",
                })
        except Exception:
            pass
    context["decision"] = ui_summary
    return render(request, "setups/run_detail.html", context)


@require_http_methods(["POST", "DELETE"])
def api_setup_delete(request, pk: int):
    setup = get_object_or_404(Setup, pk=pk)
    # Cascades via on_delete=models.CASCADE on related FKs
    setup.delete()
    return JsonResponse({"ok": True})


# ===============
# New endpoints for MCP consumption (HTTP-driven orchestration)
# ===============


@require_http_methods(["GET"])
def api_setup_next_unprocessed(request, pk: int):
    """Return the earliest unprocessed requirement for a setup with full details.

    If none exists, returns {"requirement": null}.
    """
    try:
        setup = Setup.objects.get(pk=pk)
    except Setup.DoesNotExist:
        return JsonResponse({})
    r = (
        Requirement.objects.filter(setup=setup, status=Requirement.Status.UNPROCESSED)
        .order_by("created_at")
        .first()
    )
    if not r:
        return JsonResponse({})
    payload = {
        "id": r.id,
        "framework_id": str(r.framework_id),
        "setup_id": setup.id,
        "setup_name": setup.name,
        "title": r.title,
        "description": r.description,
        "priority": r.priority,
        "tags": list(r.tags_json or []),
        "acceptance_criteria": [
            {"name": c.name, "text": c.text, "state": c.state}
            for c in r.criteria.all()
        ],
        "metadata": r.metadata_json or None,
        "status": r.status,
        "created_at": timezone.localtime(r.created_at).strftime("%Y-%m-%d %H:%M"),
    }
    return JsonResponse({"requirement": payload})


@require_http_methods(["GET"])
def api_requirements_unprocessed_in_setup(request, pk: int):
    """Return all unprocessed requirements for a specific setup with full details."""
    setup = get_object_or_404(Setup, pk=pk)
    q = Requirement.objects.filter(setup=setup, status=Requirement.Status.UNPROCESSED).order_by("created_at")
    items = []
    for r in q:
        items.append({
            "id": r.id,
            "framework_id": str(r.framework_id),
            "setup_id": setup.id,
            "setup_name": setup.name,
            "title": r.title,
            "description": r.description,
            "priority": r.priority,
            "tags": list(r.tags_json or []),
            "acceptance_criteria": [
                {"name": c.name, "text": c.text, "state": c.state}
                for c in r.criteria.all()
            ],
            "metadata": r.metadata_json or None,
            "status": r.status,
            "created_at": timezone.localtime(r.created_at).strftime("%Y-%m-%d %H:%M"),
        })
    return JsonResponse({"requirements": items})


@csrf_exempt
@require_http_methods(["POST"])
def api_verification_start_single(request, pk: int, req_id: int):
    """Start a verification run for a specific requirement within a setup.

    Returns a minimal payload focusing on model_decision_json (null when processing).
    """
    try:
        setup = Setup.objects.get(pk=pk)
    except Setup.DoesNotExist:
        return JsonResponse({})
    try:
        req = Requirement.objects.get(pk=req_id, setup=setup)
    except Requirement.DoesNotExist:
        return JsonResponse({})
    async_result = run_verification_task.delay(req.id)
    return JsonResponse({
        "started": True,
        "task_id": async_result.id,
        "requirement_id": req.id,
        "model_decision_json": None,
        "status": "processing",
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_verification_start_batch(request):
    """Start verification runs for multiple requirements given a JSON list of IDs.

    Payload: {"setup_id": <int>, "requirement_ids": [1,2,3]}
    Returns items with task ids and model_decision_json set to null (will be available after completion via runs APIs).
    """
    try:
        body = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        body = {}
    ids = body.get("requirement_ids")
    setup_id = body.get("setup_id")
    if not isinstance(ids, list) or not ids:
        return HttpResponseBadRequest("Missing or invalid requirement_ids list")
    try:
        setup_id_int = int(setup_id)
    except Exception:
        return HttpResponseBadRequest("Missing or invalid setup_id")
    # Ensure setup exists
    setup = get_object_or_404(Setup, pk=setup_id_int)
    items = []
    for rid in ids:
        try:
            req = Requirement.objects.get(pk=int(rid), setup=setup)
            async_result = run_verification_task.delay(req.id)
            items.append({
                "requirement_id": req.id,
                "setup_id": req.setup_id,
                "task_id": async_result.id,
                "model_decision_json": None,
                "status": "processing",
            })
        except Exception:
            items.append({
                "requirement_id": rid,
                "error": True,
                "reason": "not_found_or_setup_mismatch",
            })
    return JsonResponse({"started": True, "items": items})