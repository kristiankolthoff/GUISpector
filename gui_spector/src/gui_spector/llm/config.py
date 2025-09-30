from gui_spector.llm.llm import LLM
# List of available models with display names for frontend
AVAILABLE_MODELS = [
        (LLM.MODEL_GPT_4O, "GPT-4o"),
        (LLM.MODEL_GPT_4O_MINI, "GPT-4o Mini"),
        (LLM.MODEL_GPT_4_1, "GPT-4.1"),
        (LLM.MODEL_GPT_4_1_MINI, "GPT-4.1 Mini"),
        (LLM.MODEL_GPT_4_1_NANO, "GPT-4.1 Nano"),
        (LLM.MODEL_O3, "o3"),
        (LLM.MODEL_GEMINI_2_0_FLASH, "Gemini 2.0 Flash"),
        (LLM.MODEL_GEMINI_2_5_FLASH, "Gemini 2.5 Flash"),
        (LLM.MODEL_GEMINI_2_5_PRO, "Gemini 2.5 Pro"),
        (LLM.MODEL_CLAUDE_SONNET_3_7, "Claude Sonnet 3.7"),
        (LLM.MODEL_CLAUDE_SONNET_4, "Claude Sonnet 4"),
    ]