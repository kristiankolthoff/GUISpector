from __future__ import annotations

"""
MCP server (web orchestrator) for GUISpector
============================================

Purpose for LLM agents
----------------------
- Discover available Setups and their Requirements from the web backen1d.
- Start verification runs on the backend and receive a final decision in the
  same tool call (the MCP tool blocks internally by polling until completion).

Key idea
--------
The web backend runs verifications asynchronously (Celery + agent container).
This MCP server does not do the verification itself. Instead, it:
- Sends an HTTP request to start the run;
- Polls a "latest decision" HTTP endpoint;
- Returns only when a final decision (model_decision_json) is available, or a
  timeout is reached.

Why this helps an LLM
---------------------
The agent can write linear plans (“start verification → wait → consume
decision”) without implementing polling logic or concurrency. Use the
verification_run_single_sync or verification_run_batch_sync tools when you want
to block until results are ready; use the list tools to discover work to do.

All logging goes to stderr (never stdout) to preserve MCP stdio integrity.
"""

import os
import sys
import json
import logging
import asyncio
from typing import Any, Dict, List, Optional

import httpx
from mcp.server.fastmcp import FastMCP


# Configure stderr logging per MCP guidance (never stdout)
logging.basicConfig(
    level=logging.INFO,
    format="[MCP] %(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)


def _get_base_url() -> str:
    return os.environ.get("WEBAPP_BASE_URL", "http://localhost:8000").rstrip("/")


async def _http_get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """HTTP GET helper.

    Args:
        path: Path suffix to append to WEBAPP_BASE_URL
        params: Optional query parameters

    Returns:
        Parsed JSON response
    """
    url = f"{_get_base_url()}{path}"
    logging.debug("HTTP GET %s params=%s", url, params)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        logging.info("HTTP GET %s -> %s", url, resp.status_code)
        return resp.json()


async def _http_post(path: str, json_body: Optional[Dict[str, Any]] = None) -> Any:
    """HTTP POST helper with JSON body.

    Args:
        path: Path suffix to append to WEBAPP_BASE_URL
        json_body: Optional JSON body to send

    Returns:
        Parsed JSON response
    """
    url = f"{_get_base_url()}{path}"
    logging.debug("HTTP POST %s json=%s", url, json.dumps(json_body) if json_body is not None else None)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=json_body)
        resp.raise_for_status()
        logging.info("HTTP POST %s -> %s", url, resp.status_code)
        return resp.json()


# Internal HTTP helpers (not exposed as MCP tools)
async def _start_verification_single_http(setup_id: int, requirement_id: int) -> Dict[str, Any]:
    logging.info("Start single verification setup_id=%s requirement_id=%s", setup_id, requirement_id)
    return await _http_post(
        f"/setups/{int(setup_id)}/api/requirements/{int(requirement_id)}/verification/start/",
        json_body=None,
    )


async def _start_verification_batch_http(setup_id: int, requirement_ids: List[int]) -> Dict[str, Any]:
    logging.info("Start batch verification setup_id=%s count=%s", setup_id, len(requirement_ids or []))
    payload = {"setup_id": int(setup_id), "requirement_ids": [int(r) for r in (requirement_ids or [])]}
    return await _http_post("/requirements/api/verification/start_batch/", json_body=payload)


async def _get_latest_decision_http(requirement_id: int) -> Dict[str, Any]:
    logging.debug("Fetch latest decision requirement_id=%s", requirement_id)
    return await _http_get(f"/requirements/{int(requirement_id)}/api/decision/")


mcp = FastMCP("gui-spector-webapi")
logging.info("Registered MCP server instance: gui-spector-webapi")

# Internal polling configuration (not exposed to tool callers)
_POLL_INTERVAL_SECONDS_SINGLE = 10.0
_POLL_INTERVAL_SECONDS_BATCH = 10.0
_TIMEOUT_SECONDS_SINGLE = 1000.0
_TIMEOUT_SECONDS_BATCH = 5000.0


@mcp.tool()
async def setups_list() -> Dict[str, Any]:
    """List available Setups the agent can work on.

    Use this first to discover the setup identifier. You may also allow users
    to choose by name, then pass the corresponding id to other tools.

    Returns:
        Object with the key "setups" mapping to a list of setup dicts
    """
    logging.info("List setups")
    data = await _http_get("/setups/api/list/")
    # Pass through shape from Django: {"setups": [{id, name, ...}]}
    return data or {"setups": []}


@mcp.tool()
async def setup_next_unprocessed(setup_id: int) -> Dict[str, Any]:
    """Fetch the next unprocessed Requirement within a Setup.

    Call this when you want the “next item to work on” for a given setup.

    Args:
        setup_id: Identifier of the Setup

    Returns:
        Object with key "requirement" mapping to a requirement dict or null
    """
    logging.info("Next unprocessed requirement setup_id=%s", setup_id)
    data = await _http_get(f"/setups/{int(setup_id)}/api/next_unprocessed/")
    return data or {"requirement": None}


@mcp.tool()
async def requirements_unprocessed_in_setup(setup_id: int) -> Dict[str, Any]:
    """List all unprocessed Requirements for a given Setup.

    Args:
        setup_id: Identifier of the Setup

    Returns:
        Object with key "requirements" mapping to a list of requirement dicts
    """
    logging.info("List unprocessed requirements setup_id=%s", setup_id)
    data = await _http_get(f"/setups/{int(setup_id)}/api/requirements/unprocessed/")
    return data or {"requirements": []}


@mcp.tool()
async def requirements_list_in_setup(setup_id: int) -> Dict[str, Any]:
    """List all Requirements for a Setup (any status).

    Args:
        setup_id: Identifier of the Setup

    Returns:
        Object with key "requirements" mapping to a list of requirement dicts
    """
    logging.info("List requirements (all) setup_id=%s", setup_id)
    data = await _http_get(f"/setups/{int(setup_id)}/api/requirements/")
    return data or {"requirements": []}



@mcp.tool()
async def verification_run_single_sync(setup_id: int, requirement_id: int) -> Dict[str, Any]:
    """Verify one Requirement and BLOCK until the final decision is ready.

    Good for linear flows that want to “start → wait → consume result”.

    Args:
        setup_id: Identifier of the Setup that owns the requirement
        requirement_id: Identifier of the Requirement to verify

    Returns:
        Dict with keys: requirement_id, status, model_decision_json
    """
    # Kick off run via HTTP
    logging.info("Sync verify (single) start setup_id=%s requirement_id=%s", setup_id, requirement_id)
    await _start_verification_single_http(setup_id=setup_id, requirement_id=requirement_id)
    # Poll for decision
    import time as _time
    deadline = _time.time() + float(_TIMEOUT_SECONDS_SINGLE)
    while True:
        info = await _get_latest_decision_http(requirement_id=requirement_id)
        if info and info.get("model_decision_json"):
            logging.info("Sync verify (single) done requirement_id=%s status=%s", requirement_id, info.get("status"))
            return info
        if _time.time() >= deadline:
            logging.warning("Sync verify (single) timeout requirement_id=%s", requirement_id)
            return info or {"requirement_id": int(requirement_id), "status": None, "model_decision_json": None}
        await asyncio.sleep(float(_POLL_INTERVAL_SECONDS_SINGLE))


@mcp.tool()
async def verification_run_batch_sync(
    setup_id: int,
    requirement_ids: List[int],
) -> Dict[str, Any]:
    """Verify multiple Requirements and BLOCK until all decisions or timeout.

    Good for batch processing where the agent proceeds only after every item
    has a result. Items exceeding the timeout are returned with latest known
    status and listed under "pending".

    Args:
        setup_id: Identifier of the Setup that owns all requirement_ids
        requirement_ids: List of requirement identifiers to verify

    Returns:
        Dict with keys:
        - items: list of {requirement_id, status, model_decision_json}
        - pending: list of requirement ids that did not finish
        - timeout: boolean flag indicating a timeout occurred
    """
    # Kick off batch via HTTP
    logging.info("Sync verify (batch) start setup_id=%s count=%s", setup_id, len(requirement_ids or []))
    await _start_verification_batch_http(setup_id=int(setup_id), requirement_ids=requirement_ids)

    # Track results by id
    remaining: set[int] = set(int(r) for r in (requirement_ids or []))
    results: Dict[int, Dict[str, Any]] = {}

    import time as _time
    deadline = _time.time() + float(_TIMEOUT_SECONDS_BATCH)
    while remaining:
        completed_now: List[int] = []
        for rid in list(remaining):
            info = await _get_latest_decision_http(requirement_id=int(rid))
            # Consider decision complete when model_decision_json is present and status is terminal
            decision = info.get("model_decision_json") if isinstance(info, dict) else None
            status = info.get("status") if isinstance(info, dict) else None
            if decision:
                results[int(rid)] = info
                completed_now.append(int(rid))
        for rid in completed_now:
            logging.info("Sync verify (batch) item done requirement_id=%s status=%s", rid, (results.get(int(rid)) or {}).get("status"))
            remaining.discard(int(rid))
        if not remaining:
            break
        if _time.time() >= deadline:
            # Gather latest states for remaining and return
            for rid in list(remaining):
                info = await _get_latest_decision_http(requirement_id=int(rid))
                results[int(rid)] = info
            logging.warning("Sync verify (batch) timeout setup_id=%s pending=%s", setup_id, sorted(int(r) for r in remaining))
            return {
                "items": [
                    {
                        "requirement_id": k,
                        "status": (v or {}).get("status"),
                        "model_decision_json": (v or {}).get("model_decision_json"),
                    }
                    for k, v in results.items()
                ],
                "pending": sorted(int(r) for r in remaining),
                "timeout": True,
            }
        await asyncio.sleep(float(_POLL_INTERVAL_SECONDS_BATCH))

    # All done
    logging.info("Sync verify (batch) complete setup_id=%s items=%s", setup_id, len(results))
    return {
        "items": [
            {
                "requirement_id": k,
                "status": (v or {}).get("status"),
                "model_decision_json": (v or {}).get("model_decision_json"),
            }
            for k, v in results.items()
        ],
        "pending": [],
        "timeout": False,
    }


if __name__ == "__main__":
    try:
        if sys.stdin and sys.stdin.isatty():
            logging.warning(
                "Starting MCP server on stdio without a host attached (stdin is a TTY). "
                "Use an MCP host (e.g., Claude Desktop or MCP Inspector)."
            )
        logging.info("Starting MCP stdio server (webapi mode); base_url=%s", _get_base_url())
        mcp.run(transport="stdio")
        logging.info("MCP server stopped (stdio closed)")
    except Exception:
        logging.exception("MCP server crashed")
        raise


