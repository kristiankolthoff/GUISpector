from typing import Optional, Text, Dict, Any, Tuple

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models.chat_models import BaseChatModel


class LLM:

    MODEL_GPT_4O = "model_gpt_4o"
    MODEL_GPT_4O_MINI = "model_gpt_4o_mini"
    MODEL_GPT_4_1 = "model_gpt_4_1"
    MODEL_GPT_4_1_MINI = "model_gpt_4_1_mini"
    MODEL_GPT_4_1_NANO = "model_gpt_4_1_nano"
    MODEL_O3 = "model_o3"
    MODEL_GEMINI_2_0_FLASH = "model_gemini_2.0_flash"
    MODEL_GEMINI_2_5_PRO = "model_gemini_2.5_pro"
    MODEL_GEMINI_2_5_FLASH = "model_gemini_2.5_flash"
    MODEL_CLAUDE_SONNET_3_7 = "model_claude_sonnet"
    MODEL_CLAUDE_SONNET_4 = "model_claude_sonnet_4"


    def __init__(self, model_name: Optional[Text] = MODEL_GPT_4_1, temperature: Optional[float] = 0.05,
                max_tokens: Optional[int] = 32000, max_retries: Optional[int] = 2,
                timeout: Optional[int] = None, api_key: Optional[Text] = None):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.timeout = timeout
        self.api_key = api_key
        self.client = LLM.get_llm_client(model_name=model_name, temperature=temperature,
                                         max_tokens=max_tokens, max_retries=max_retries, timeout=timeout, api_key=api_key)

    def invoke(self, prompt) -> Tuple[Text, Dict[str, Any]]:
        #print(f"Invoking {self.model_name} with prompt: {prompt}")
        if self.model_name == LLM.MODEL_CLAUDE_SONNET_4:
            # Claude Sonnet 4 responses have a special format that does not conform
            # to the other model formats, therefore this custom accessing is required
            response = self.client.invoke(prompt)
            return response.content[1].get("text"), {}
        response = self.client.invoke(prompt)
        return response.content, response.usage_metadata

    @staticmethod
    def get_llm_client(model_name: Optional[Text] = MODEL_GPT_4O,
                       temperature: Optional[float] = 0.2,
                       max_tokens: Optional[int] = 4000,
                       max_retries: Optional[int] = 2,
                       timeout: Optional[int] = None,
                       api_key: Optional[Text] = None) -> BaseChatModel:
        client_kwargs = {}
        if api_key is not None:
            client_kwargs["api_key"] = api_key
        if model_name == LLM.MODEL_GPT_4O:
            return ChatOpenAI(
                    model="gpt-4o",
                    temperature=temperature,
                    timeout=timeout,
                    max_retries=max_retries,
                    max_tokens=16384,
                    **client_kwargs)
        elif model_name == LLM.MODEL_GPT_4O_MINI:
            return ChatOpenAI(
                    model="gpt-4o-mini",
                    temperature=temperature,
                    timeout=timeout,
                    max_retries=max_retries,
                    max_tokens=16384,
                    **client_kwargs)
        elif model_name == LLM.MODEL_GPT_4_1:
            return ChatOpenAI(
                    model="gpt-4.1",
                    temperature=temperature,
                    timeout=timeout,
                    max_retries=max_retries,
                    max_tokens=32000,
                    **client_kwargs)
        elif model_name == LLM.MODEL_GPT_4_1_MINI:
            return ChatOpenAI(
                    model="gpt-4.1-mini",
                    temperature=temperature,
                    timeout=timeout,
                    max_retries=max_retries,
                    max_tokens=32000,
                    **client_kwargs)
        elif model_name == LLM.MODEL_GPT_4_1_NANO:
            return ChatOpenAI(
                    model="gpt-4.1-nano",
                    temperature=temperature,
                    timeout=timeout,
                    max_retries=max_retries,
                    max_tokens=32000,
                    **client_kwargs)
        elif model_name == LLM.MODEL_O3:
            return ChatOpenAI(model="o3",
                    reasoning_effort="low",
                    timeout=timeout,
                    max_retries=max_retries,
                    max_tokens=32000,
                    **client_kwargs)
        elif model_name == LLM.MODEL_GEMINI_2_0_FLASH:
            return ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                temperature=temperature,
                timeout=timeout,
                max_retries=max_retries,
                max_tokens=8192,
                **client_kwargs)
        elif model_name == LLM.MODEL_GEMINI_2_5_PRO:
            return ChatGoogleGenerativeAI(
                model="gemini-2.5-pro",
                temperature=temperature,
                thinking_budget=500,
                max_retries=max_retries,
                max_tokens=32000,
                **client_kwargs)
        elif model_name == LLM.MODEL_GEMINI_2_5_FLASH:
            return ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                temperature=temperature,
                timeout=timeout,
                max_retries=max_retries,
                max_tokens=32000,
                **client_kwargs)
        elif model_name == LLM.MODEL_CLAUDE_SONNET_3_7:
            return ChatAnthropic(
                model="claude-3-7-sonnet-latest",
                temperature=temperature,
                timeout=timeout,
                max_retries=max_retries,
                max_tokens=32000,
                **client_kwargs)
        elif model_name == LLM.MODEL_CLAUDE_SONNET_4:
            return ChatAnthropic(
                model="claude-sonnet-4-20250514",
                thinking={
                    "type": "enabled",
                    "budget_tokens": 1024
                },
                timeout=timeout,
                max_retries=max_retries,
                max_tokens=32000,
                **client_kwargs)
        # Ensure all code paths return a value
        raise ValueError(f"Unknown model_name: {model_name}")

    def to_dict(self) -> Dict[Text, Any]:
        return {'model_name': self.model_name, 'temperature': self.temperature,
                'max_tokens': self.max_tokens, 'max_retries': self.max_retries, 'timeout': self.timeout}

    def __str__(self):
        return (f"LLM(model_name={self.model_name}, temperature={self.temperature}, "
                f"max_tokens={self.max_tokens}, max_retries={self.max_retries}, "
                f"timeout={self.timeout})")

    def __repr__(self):
        return (f"LLM(model_name={self.model_name!r}, temperature={self.temperature!r}, "
                f"max_tokens={self.max_tokens!r}, max_retries={self.max_retries!r}, "
                f"timeout={self.timeout!r})")

    def __eq__(self, other):
        if not isinstance(other, LLM):
            return False
        return (self.model_name == other.model_name and
                self.temperature == other.temperature and
                self.max_tokens == other.max_tokens and
                self.max_retries == other.max_retries and
                self.timeout == other.timeout)

    def __hash__(self):
        return hash((self.model_name, self.temperature, self.max_tokens, self.max_retries, self.timeout))

