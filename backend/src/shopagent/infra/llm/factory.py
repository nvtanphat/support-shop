"""LLM Model Factory supporting Gemini, Groq, and Fake providers."""

from __future__ import annotations

import logging
import os
from typing import Any
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from shopagent.core.config import get_models_config, get_settings

logger = logging.getLogger(__name__)


class FakeChatModel(BaseChatModel):
    """Deterministic fake chat model for fast, zero-network unit/integration tests."""

    canned_responses: list[str] = [
        "Dạ em là trợ lý ShopLab. Em có thể hỗ trợ quý khách kiểm tra đơn hàng hoặc hướng dẫn thủ tục đổi trả ạ."
    ]
    current_idx: int = 0

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Any:
        from langchain_core.outputs import ChatGeneration, ChatResult

        response_text = self.canned_responses[self.current_idx % len(self.canned_responses)]
        self.current_idx += 1
        msg = AIMessage(content=response_text)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Any:
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def get_chat_model(role: str = "agent_primary") -> BaseChatModel:
    """Instantiate a chat model based on role configuration in config/models.yaml."""
    settings = get_settings()
    models_cfg = get_models_config().get("roles", {})
    role_cfg = models_cfg.get(role, {})

    provider = role_cfg.get("provider", "gemini")
    model_name = role_cfg.get("model", "gemini-3.5-flash-lite")
    temperature = role_cfg.get("temperature", 0.0)

    # Resolve environment variable placeholders
    if isinstance(provider, str) and provider.startswith("${"):
        env_var = provider.strip("${}").strip()
        provider = getattr(settings, env_var, "gemini")
    if isinstance(model_name, str) and model_name.startswith("${"):
        env_var = model_name.strip("${}").strip()
        model_name = getattr(settings, env_var, "gemini-3.5-flash-lite")

    api_key = settings.GEMINI_API_KEY or os.environ.get("GOOGLE_API_KEY")

    if provider == "fake":
        # Disallow silent fallback to FakeChatModel when primary LLM is a real provider
        if role == "agent_fallback" and settings.LLM_PRIMARY_PROVIDER != "fake":
            raise ValueError(
                "Không được phép fallback âm thầm sang FakeChatModel khi hệ thống cấu hình chạy LLM thật. "
                "Cần cấu hình model dự phòng thật hoặc báo lỗi gián đoạn kết nối minh bạch."
            )
        return FakeChatModel()

    if not api_key:
        raise ValueError(
            f"LLM provider '{provider}' for role '{role}' requires a valid GEMINI_API_KEY or GOOGLE_API_KEY."
        )

    if provider == "gemini":
        try:
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                temperature=temperature,
                timeout=30.0,
            )
        except Exception as e:
            logger.error("Failed to initialize ChatGoogleGenerativeAI(%s): %s", model_name, e)
            raise RuntimeError(f"Could not initialize Gemini model '{model_name}': {e}") from e

    raise ValueError(f"Unsupported LLM provider '{provider}' for role '{role}'.")
