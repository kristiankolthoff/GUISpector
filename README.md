## GUISpector: An MLLM Agent Framework for Automated Verification of Natural Language Requirements in GUI Prototypes

This repository contains the supplementary material and implementation for our submission to the ICSE26 Demo track on the work on verifying natural language (NL) requirements in graphical user interface (GUI) prototypes using a multi‑modal LLM-based agent. The system is designed to integrate seamlessly with developer workflows and LLM-driven programming agents, providing actionable verification feedback and a closed feedback loop for iterative improvement.

## Introduction and Overview

<img src="https://raw.githubusercontent.com/kristiankolthoff/GUISpector/refs/heads/main/webapp/media/static/overview/overview_gui_spector.png" width="100%">

GUISpector adapts a multi‑modal LLM agent to interpret and operationalize NL requirements, autonomously planning and executing verification trajectories over GUI applications. It systematically extracts detailed NL feedback from the verification process—highlighting satisfied, partially satisfied, and unmet acceptance criteria—to guide developers in refining their GUI artifacts, or to directly inform LLM-based code generation.

An integrated web application unifies these capabilities, allowing practitioners to:
- supervise verification runs,
- inspect agent rationales and feedback,
- manage setups, requirements, inputs, and the end‑to‑end verification process.

We evaluated GUISpector on 150 requirements with 900 acceptance criteria across diverse GUIs, demonstrating effective detection of satisfaction and violations, and highlighting its potential for seamless integration into automated LLM-driven development workflows.

A short video presentation showcasing the system is available here:

<a href="https://youtu.be/JByYF6BNQeE" target="_blank">
  <img src="https://raw.githubusercontent.com/kristiankolthoff/GUISpector/refs/heads/main/webapp/media/static/youtube/gui_spector_youtube.png" alt="Watch the video" style="max-width:100%;"/>
</a>


## Project Structure

- `gui_spector`: Core Python package with the agent orchestration, verification pipeline, LLM integration, Playwright/Docker execution backends, and utilities. Managed with Poetry.
- `webapp`: Prototypical Django web application demonstrating the system end‑to‑end (data models, Celery tasks, Channels websockets, views, and templates).
- `mcp`: Model Context Protocol (MCP) server and resources to let LLM hosts (e.g., Claude Desktop, Cursor) orchestrate verification runs over the web API. Includes a recommended orchestration prompt.
- `evaluation`: Example apps, gold‑standard annotations, and result stubs for local experiments.
- `docker-compose.yml`, `Dockerfile.celery`, `Dockerfile.agent`: Infrastructure for MySQL, Redis, Celery worker, and a multi‑display VNC agent container (Xvfb + Xfce + Firefox) used during automated verification.

---

## Installation & Setup

This section guides you through setting up GUISpector locally using Docker for infra and a local Python environment for the web application.

### 1) Clone the Repository

```bash
git clone https://github.com/kristiankolthoff/GUISpector.git && cd GUISpector
```

### 2) Install Docker & Docker Compose

Ensure [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) are installed. These will run MySQL, Redis, RedisInsight, the Celery worker, and the agent container.

### 3) Start Required Services (MySQL, Redis, Celery worker, Agent)

From the project root, build and start the containers:

```bash
docker-compose up -d --build
```

This will:
- start MySQL on `localhost:3306`
- start Redis on `localhost:6379` (RedisInsight on `localhost:5540`)
- start the Celery worker (reads the same code as the web app)
- start the agent container with multiple VNC displays exposed on ports `5900..5904` (password `secret`)

You can connect with a VNC viewer to a display (e.g., `localhost:5900`) if you want to observe agent sessions.

### 4) Create a Python 3.10 environment and install dependencies

GUISpector uses Poetry for dependency management of the core package. Choose one of the following:

- With Conda:

```bash
conda create -n guispector python=3.10.18 -y \
  && conda activate guispector \
  && cd gui_spector \
  && python -m pip install --upgrade pip \
  && pip install poetry \
  && poetry install
```

- With venv:

```bash
python3.10 -m venv .venv \
  && source .venv/bin/activate \
  && cd gui_spector \
  && python -m pip install --upgrade pip \
  && pip install poetry \
  && poetry install
```

Optional (for local Playwright usage):

```bash
poetry run playwright install --with-deps
```

### 5) Run Django migrations

From the project root:

```bash
cd webapp && python manage.py migrate
```

### 6) Start the web server (Daphne)

```bash
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

The web interface will be available at [http://localhost:8000](http://localhost:8000).

### 7) Configure API keys in the running app

Open the web interface and navigate to the Settings page. Provide at least your OpenAI API key (required). Optionally add Google and Anthropic keys. Save the settings before running verifications.

---

## Running GUISpector

You can explore the system and run verifications over your own setups and requirements:

1. Ensure Docker services are running:
   ```bash
   docker-compose up -d
   ```
2. Activate your virtual environment and start Daphne from `webapp` if it’s not running yet:
   ```bash
   daphne -b 0.0.0.0 -p 8000 config.asgi:application
   ```
3. In the web UI:
   - create a Setup,
   - add Requirements (with acceptance criteria and optional inputs),
   - start a Verification Run from the Setup page and watch status updates live.

During runs, the Celery worker coordinates with the agent container to execute multi‑step verification trajectories and returns natural‑language feedback for refinement.

---

## Using the MCP Server (Optional, Recommended for Agent Workflows)

GUISpector ships an MCP server so LLM hosts (e.g., Claude Desktop, Cursor) can orchestrate verification runs via tools rather than manual UI actions. The server communicates with the web app over HTTP and blocks until results are available.

### Prerequisites

- Web app running at `http://localhost:8000` (or set `WEBAPP_BASE_URL` accordingly)
- Your Python environment activated (from step 4 above)

### Start the MCP server manually (stdio)

```bash
python mcp/web_mcp_server.py
```

Environment variable (optional):

```bash
export WEBAPP_BASE_URL="http://localhost:8000"
```

### Attach from Claude Desktop

Create a JSON file at `%APPDATA%\Claude\mcp\servers\gui-spector-webapi.json` on Windows (adjust paths for your environment):

```json
{
  "command": "C:\\path\\to\\venv\\Scripts\\python.exe",
  "args": [
    "-u",
    "C:\\path\\to\\repo\\mcp\\web_mcp_server.py"
  ],
  "env": {
    "WEBAPP_BASE_URL": "http://localhost:8000"
  }
}
```

Restart Claude Desktop, then enable the `gui-spector-webapi` server in the MCP settings UI.

### Attach from Cursor

Add an entry to your Cursor MCP configuration (Settings → MCP Servers). For example:

```json
{
  "mcpServers": {
    "gui-spector-webapi": {
      "command": "C:\\path\\to\\venv\\Scripts\\python.exe",
      "args": [
        "-u",
        "C:\\path\\to\\repo\\mcp\\web_mcp_server.py"
      ],
      "env": {
        "WEBAPP_BASE_URL": "http://localhost:8000"
      }
    }
  }
}
```

After attaching, the following MCP tools are available to the host:
- `setups_list`
- `setup_next_unprocessed`
- `requirements_unprocessed_in_setup`
- `requirements_list_in_setup`
- `verification_run_single_sync`
- `verification_run_batch_sync`

### Use the provided orchestration prompt

Open and copy the contents of `mcp/prompt.txt`, then paste it as the initial instruction in the same chat where the GUISpector MCP server is attached. The prompt instructs the agent to:
- iterate over unprocessed requirements of a chosen setup,
- run verifications in a loop,
- use returned feedback to modify the codebase,
- trigger a live reload by calling the helper script:

```bash
python mcp/touch_save.py "C:\\absolute\\path\\to\\changed_file.ext" && sleep 2 && echo reload-ready
```

Repeat until requirements are satisfied or the loop limit is reached.

---

## Troubleshooting

- **Database or Redis connection errors**: Confirm containers are running via `docker-compose ps`. The web app defaults to `DATABASE_HOST=127.0.0.1`, `REDIS_HOST=127.0.0.1` for local use; the Celery container uses the internal service names.
- **Missing API keys**: Provide at least an OpenAI API key in the app Settings page before running verifications. Google and Anthropic keys are optional.
- **Playwright/browsers**: If using local Playwright execution, run `poetry run playwright install --with-deps`.
- **Celery not processing tasks**: Make sure the `celery` service is up and logs are clean. Restart with `docker-compose up -d --build` if needed.
- **Agent VNC access**: Connect to `localhost:5900` (password `secret`) to observe a display if desired. Increase `NUM_DISPLAYS` via `docker-compose.yml` if you need more parallelism.
- **Clean up containers**: `docker-compose down --remove-orphans`.

---

