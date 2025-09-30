FROM python:3.10

RUN apt-get update && apt-get install -y netcat-openbsd

WORKDIR /app

RUN pip install poetry

# Install Python dependencies via Poetry with cache-friendly layering
WORKDIR /app/gui_spector
COPY ./gui_spector/pyproject.toml ./gui_spector/poetry.lock ./
RUN poetry config virtualenvs.create false \
 && poetry install --no-interaction --no-ansi --no-root

# Now copy the actual project sources
COPY ./gui_spector .

# Removed requirements.txt installation, now using only Poetry for dependencies

RUN ls -l /app/gui_spector/src/gui_spector
#RUN python -c "import gui_rerank.llm.llm; print('Import works!')"

COPY ./webapp ./webapp

WORKDIR /app/webapp

ENV PYTHONPATH="/app/webapp"

CMD ["python", "-m", "celery", "-A", "config", "worker", "-l", "info"]
