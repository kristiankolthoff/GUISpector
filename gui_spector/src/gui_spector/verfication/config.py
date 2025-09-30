from typing import List, Tuple

# Define canonical identifiers for available agent models
OPENAI_COMPUTER_USE_PREVIEW = "computer-use-preview"

# List of available agent models for the UI (value, display)
AVAILABLE_AGENTS: List[Tuple[str, str]] = [
    (OPENAI_COMPUTER_USE_PREVIEW, "OpenAI GPT-4o (CUA)"),
]

# Default agent selection
DEFAULT_AGENT = OPENAI_COMPUTER_USE_PREVIEW


