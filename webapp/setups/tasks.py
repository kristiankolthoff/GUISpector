from __future__ import annotations

from celery import shared_task
from celery.schedules import crontab
from django.utils import timezone
from pathlib import Path
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings

from .models import Requirement, VerificationRun, AcceptanceCriterion
from .mappers import model_to_framework, framework_run_to_models, inputs_model_to_framework
from gui_spector.verfication.agent import VerficationRunner, PROMPT_TEMPLATE_V1
from gui_spector.computers.docker import DockerComputer
from .resource_manager import DisplayPool
from settings.models import set_api_keys_from_settings


def _broadcast(req_id: int, event: dict) -> None:
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"runs_{req_id}",
            {"type": "run.progress", "payload": event},
        )
        # If this event includes a setup_id and state, also notify setups group
        setup_id = event.get("setup_id")
        setup_state = event.get("setup_state")
        if setup_id and setup_state:
            payload = {"setup_id": setup_id, "state": setup_state}
            # forward counters when provided
            if "num_met" in event:
                payload["num_met"] = event.get("num_met")
            if "num_unmet" in event:
                payload["num_unmet"] = event.get("num_unmet")
            if "num_processing" in event:
                payload["num_processing"] = event.get("num_processing")
            if "num_error" in event:
                payload["num_error"] = event.get("num_error")
            if "num_unprocessed" in event:
                payload["num_unprocessed"] = event.get("num_unprocessed")
            async_to_sync(channel_layer.group_send)(
                "setups",
                {"type": "setup.update", "payload": payload},
            )
    except Exception:
        pass


def _update_acceptance_states_from_decision(requirement: Requirement, decision: dict) -> None:
    """Update AcceptanceCriterion.state rows based on model_decision_json.

    Expects decision to contain an array at key "acceptance_criteria_results" where each
    item is a dict with keys: criterion_name (e.g., "AC-1") and met (bool).
    Missing or malformed entries are ignored. Other keys in decision are ignored.
    """
    try:
        if not isinstance(decision, dict):
            return
        results = decision.get("acceptance_criteria_results") or []
        if not isinstance(results, list) or not results:
            return
        # Build map of name -> AcceptanceCriterion
        by_name = {}
        try:
            for c in requirement.criteria.all():
                n = (c.name or "").strip().upper()
                if n:
                    by_name[n] = c
        except Exception:
            return
        updates: list[tuple[AcceptanceCriterion, str]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            name_raw = item.get("criterion_name") or item.get("name") or item.get("criterion")
            if not name_raw:
                continue
            name_key = str(name_raw).strip().upper()
            if not name_key:
                continue
            target = by_name.get(name_key)
            if not target:
                continue
            met_val = item.get("met")
            if isinstance(met_val, bool):
                new_state = AcceptanceCriterion.State.MET if met_val else AcceptanceCriterion.State.UNMET
            else:
                status_raw = str(item.get("status", "")).strip().lower()
                if status_raw in ["met", "pass", "true", "yes", "1"]:
                    new_state = AcceptanceCriterion.State.MET
                elif status_raw in ["unmet", "fail", "false", "no", "0"]:
                    new_state = AcceptanceCriterion.State.UNMET
                else:
                    continue
            if target.state != new_state:
                updates.append((target, new_state))
        for obj, st in updates:
            try:
                obj.state = st
                obj.save(update_fields=["state"])
            except Exception:
                pass
    except Exception:
        # Never fail the task because of state sync
        pass

@shared_task(bind=True)
def run_verification_task(self, requirement_id: int) -> int:
    # Ensure API keys from latest settings are applied before any LLM/agent usage
    try:
        set_api_keys_from_settings()
    except Exception:
        pass
    req = Requirement.objects.get(pk=requirement_id)
    setup = req.setup
    pool = DisplayPool(lease_ttl_seconds=int(getattr(setup, 'agent_timeout_seconds', 120)))

    # Create a pending VerificationRun first (no display yet)
    pending = VerificationRun.objects.create(
        requirement=req,
        status=VerificationRun.Status.PROCESSING,
        started_at=timezone.now(),
        finished_at=timezone.now(),
        elapsed_s=0.0,
        start_url=setup.start_url,
        current_url=None,
        steps_taken=0,
        run_dir=str(Path("runs") / "pending"),
        display_str=None,
    )
    # Mark requirement/setup as processing immediately so refresh reflects state
    try:
        req.status = Requirement.Status.PROCESSING
        req.save(update_fields=["status"]) 
    except Exception:
        pass
    try:
        setup.state = setup.State.PROCESSING
        setup.save(update_fields=["state"]) 
    except Exception:
        pass
    # Include current counters
    try:
        num_met = setup.requirements.filter(status=Requirement.Status.MET).count()
        num_unmet = setup.requirements.filter(status=Requirement.Status.UNMET).count()
        num_processing = setup.requirements.filter(status=Requirement.Status.PROCESSING).count()
        num_error = setup.requirements.filter(status=Requirement.Status.ERROR).count()
        num_unprocessed = setup.requirements.filter(status=Requirement.Status.UNPROCESSED).count()
    except Exception:
        num_met = None
        num_unmet = None
        num_processing = None
        num_error = None
        num_unprocessed = None
    # Notify UI that this run is queued and waiting for a display
    _broadcast(
        req.id,
        {
            "phase": "waiting_for_display",
            "run_id": pending.id,
            "requirement_id": req.id,
            "requirement_status": req.status,
            "setup_id": setup.id,
            "setup_state": setup.state,
            "num_met": num_met,
            "num_unmet": num_unmet,
            "num_processing": num_processing,
            "num_error": num_error,
            "num_unprocessed": num_unprocessed,
        },
    )

    # Block until a display is available
    disp = pool.acquire(requirement_id, block_timeout=0)  # 0 = wait indefinitely
    # Update run with acquired display
    pending.display_str = disp
    pending.save()

    # Notify UI that the run actually started processing with a display
    req.status = Requirement.Status.PROCESSING
    req.save()
    try:
        setup.state = setup.State.PROCESSING
        setup.save(update_fields=["state"])
    except Exception:
        pass
    # Include current counters
    try:
        num_met = setup.requirements.filter(status=Requirement.Status.MET).count()
        num_unmet = setup.requirements.filter(status=Requirement.Status.UNMET).count()
        num_processing = setup.requirements.filter(status=Requirement.Status.PROCESSING).count()
        num_error = setup.requirements.filter(status=Requirement.Status.ERROR).count()
        num_unprocessed = setup.requirements.filter(status=Requirement.Status.UNPROCESSED).count()
    except Exception:
        num_met = None
        num_unmet = None
        num_processing = None
        num_error = None
        num_unprocessed = None
    _broadcast(req.id, {"phase": "started", "run_id": pending.id, "requirement_status": req.status, "setup_id": setup.id, "setup_state": setup.state, "num_met": num_met, "num_unmet": num_unmet, "num_processing": num_processing, "num_error": num_error, "num_unprocessed": num_unprocessed})

    def progress_cb(ev: dict):
        # ev: {event: 'turn', step_counter, turn_elapsed_s, reasoning_summary, message_text, screenshot_path, last_action{type,status}}
        # Heartbeat while we have progress
        pool.heartbeat(disp)
        payload = {"phase": "progress", "run_id": pending.id, **ev}
        # If we have a filesystem screenshot path, convert to MEDIA URL for the frontend
        try:
            sp = ev.get("screenshot_path")
            if sp:
                p = Path(sp).resolve()
                media_root = Path(settings.MEDIA_ROOT).resolve()
                if media_root in p.parents or p == media_root:
                    rel = p.relative_to(media_root).as_posix()
                    payload["screenshot_url"] = f"{settings.MEDIA_URL.rstrip('/')}/{rel}"
        except Exception:
            pass
        _broadcast(req.id, payload)

    data_root = Path(__file__).resolve().parent.parent / "media" / "runs"
    data_root.mkdir(exist_ok=True, parents=True)
    # Deterministic run directory with zero-padded IDs: runs/SSS/RRR/NNN
    run_dir = data_root / f"{setup.id:03d}" / f"{req.id:03d}" / f"{pending.id:03d}"
    run_dir.mkdir(exist_ok=False, parents=True)
    # Persist run_dir early so UI/debug can see it immediately
    pending.run_dir = str(run_dir)
    pending.save(update_fields=["run_dir"])
    try:
        attempts = 0
        max_retries = int(getattr(setup, 'max_retries', 2))
        last_exception = None
        result = None
        while attempts <= max_retries:
            try:
                with DockerComputer(display=disp) as computer:
                    runner = VerficationRunner(
                        computer=computer,
                        acknowledge_safety_check_callback=lambda msg: True,
                        run_dir=run_dir,
                        prompt_name=PROMPT_TEMPLATE_V1,
                    )
                    fw_req = model_to_framework(req)
                    fw_inputs = inputs_model_to_framework(setup)
                    result = runner.run(
                        requirement=fw_req,
                        start_url=setup.start_url,
                        inputs=fw_inputs,
                        print_steps=True,
                        show_images=False,
                        debug=False,
                        progress_callback=progress_cb,
                        max_reasoning_steps=getattr(setup, 'max_reasoning_steps', None),
                    )
                # If we reached here, we have a result without exception
                last_exception = None
                break
            except Exception as run_exc:
                last_exception = run_exc
                attempts += 1
                print(f"Run error: {run_exc} attempts: {attempts}")
                computer.cleanup_browser()
                if attempts > max_retries:
                    raise

        run_model, interactions = framework_run_to_models(req, result)
        for field in [
            "status",
            "finished_at",
            "elapsed_s",
            "current_url",
            "steps_taken",
            "run_dir",
            "model_decision_json",
            "error",
            "usage_total_json",
            "last_screenshot",
        ]:
            setattr(pending, field, getattr(run_model, field))
        pending.save()
        # Persisted; now sync acceptance criterion states from final decision
        try:
            _update_acceptance_states_from_decision(req, pending.model_decision_json or {})
        except Exception:
            pass
        # Update requirement status based on run result
        from .mappers import verificationrun_status_to_requirement_status
        req.status = verificationrun_status_to_requirement_status(pending.status)
        req.save()
        # Update setup state: processing if any requirement processing, else ready (success)
        try:
            if req.setup.requirements.filter(status=Requirement.Status.PROCESSING).exists():
                setup.state = setup.State.PROCESSING
            else:
                setup.state = setup.State.READY
            setup.save(update_fields=["state"])
        except Exception:
            pass
        if interactions:
            for it in interactions:
                it.run = pending
                it.save()

        # Include last_screenshot_url if available
        payload = {
            "phase": "finished",
            "run_id": pending.id,
            "status": pending.status,
            "elapsed_s": pending.elapsed_s,
            "steps_taken": pending.steps_taken,
            "requirement_status": req.status,
        }
        try:
            if pending.last_screenshot:
                p = Path(pending.last_screenshot).resolve()
                media_root = Path(settings.MEDIA_ROOT).resolve()
                if media_root in p.parents or p == media_root:
                    rel = p.relative_to(media_root).as_posix()
                    payload["last_screenshot_url"] = f"{settings.MEDIA_URL.rstrip('/')}/{rel}"
        except Exception:
            pass
        payload["setup_id"] = setup.id
        payload["setup_state"] = setup.state
        try:
            payload["num_met"] = setup.requirements.filter(status=Requirement.Status.MET).count()
            payload["num_unmet"] = setup.requirements.filter(status=Requirement.Status.UNMET).count()
            payload["num_processing"] = setup.requirements.filter(status=Requirement.Status.PROCESSING).count()
            payload["num_error"] = setup.requirements.filter(status=Requirement.Status.ERROR).count()
            payload["num_unprocessed"] = setup.requirements.filter(status=Requirement.Status.UNPROCESSED).count()
        except Exception:
            pass
        _broadcast(req.id, payload)
    except Exception as e:
        # Mark run as error on any unexpected exception
        pending.status = VerificationRun.Status.ERROR
        pending.finished_at = timezone.now()
        try:
            pending.elapsed_s = (pending.finished_at - pending.started_at).total_seconds()
        except Exception:
            pending.elapsed_s = 0.0
        print(f"Run error: {e}")
        import traceback
        traceback.print_exc()
        pending.error = str(e)
        pending.save()
        # Sync acceptance criterion states from final decision in error path
        try:
            _update_acceptance_states_from_decision(req, pending.model_decision_json or {})
        except Exception:
            pass
        # Update requirement status to error/unmet
        from .mappers import verificationrun_status_to_requirement_status
        req.status = verificationrun_status_to_requirement_status(pending.status)
        req.save()
        # Update setup state: processing if any requirement processing, else ready (success)
        try:
            if req.setup.requirements.filter(status=Requirement.Status.PROCESSING).exists():
                setup.state = setup.State.PROCESSING
            else:
                setup.state = setup.State.READY
            setup.save(update_fields=["state"])
        except Exception:
            pass
        payload = {
            "phase": "finished",
            "run_id": pending.id,
            "status": pending.status,
            "elapsed_s": pending.elapsed_s,
            "steps_taken": pending.steps_taken,
            "requirement_status": req.status,
        }
        try:
            if pending.last_screenshot:
                p = Path(pending.last_screenshot).resolve()
                media_root = Path(settings.MEDIA_ROOT).resolve()
                if media_root in p.parents or p == media_root:
                    rel = p.relative_to(media_root).as_posix()
                    payload["last_screenshot_url"] = f"{settings.MEDIA_URL.rstrip('/')}/{rel}"
        except Exception:
            pass
        payload["setup_id"] = setup.id
        payload["setup_state"] = setup.state
        try:
            payload["num_met"] = setup.requirements.filter(status=Requirement.Status.MET).count()
            payload["num_unmet"] = setup.requirements.filter(status=Requirement.Status.UNMET).count()
            payload["num_processing"] = setup.requirements.filter(status=Requirement.Status.PROCESSING).count()
            payload["num_error"] = setup.requirements.filter(status=Requirement.Status.ERROR).count()
            payload["num_unprocessed"] = setup.requirements.filter(status=Requirement.Status.UNPROCESSED).count()
        except Exception:
            pass
        _broadcast(req.id, payload)
    finally:
        # Release display
        try:
            computer.cleanup_browser()
            pool.release(disp)
        except Exception as e:
            print(f"Error releasing display: {e}")
    return pending.id


@shared_task
def reap_display_leases() -> int:
    pool = DisplayPool()
    return pool.reap_expired()


