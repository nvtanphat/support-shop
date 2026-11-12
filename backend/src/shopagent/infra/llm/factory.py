"""LLM Model Factory supporting Gemini with multi-key failover rotation and Fake providers."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import Field

from shopagent.core.config import get_models_config, get_settings

logger = logging.getLogger(__name__)


class GeminiKeyManager:
    """Manages a pool of Gemini API keys with thread-safe round-robin and quota rotation."""

    def __init__(self, keys: list[str]) -> None:
        self.keys = [k.strip() for k in keys if k.strip()]
        self.current_idx = 0

    @property
    def has_keys(self) -> bool:
        return bool(self.keys)

    def rotate(self) -> str:
        if not self.keys:
            return ""
        self.current_idx = (self.current_idx + 1) % len(self.keys)
        logger.info("Chuyển sang Gemini API Key index %d/%d", self.current_idx + 1, len(self.keys))
        return self.keys[self.current_idx]


class RotatingBoundModel:
    """Wraps bound tools models across multiple API keys for transparent quota failover."""

    def __init__(self, bound_models: list[Any], key_manager: GeminiKeyManager) -> None:
        self.bound_models = bound_models
        self.key_manager = key_manager

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        errors = []
        n = len(self.bound_models)
        for _ in range(n):
            idx = self.key_manager.current_idx
            model = self.bound_models[idx]
            try:
                return await model.ainvoke(input, config=config, **kwargs)
            except Exception as e:
                err_msg = str(e)
                if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg or "quota" in err_msg.lower():
                    logger.warning(
                        "Gemini API key index %d gặp lỗi hạn ngạch (429 RESOURCE_EXHAUSTED). Đang tự động đổi sang key tiếp theo...",
                        idx + 1,
                    )
                    self.key_manager.rotate()
                    errors.append(e)
                    continue
                raise
        if errors:
            raise errors[-1]
        raise RuntimeError("Không có Gemini model nào khả dụng trong pool.")

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        errors = []
        n = len(self.bound_models)
        for _ in range(n):
            idx = self.key_manager.current_idx
            model = self.bound_models[idx]
            try:
                return model.invoke(input, config=config, **kwargs)
            except Exception as e:
                err_msg = str(e)
                if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg or "quota" in err_msg.lower():
                    logger.warning(
                        "Gemini API key index %d gặp lỗi hạn ngạch (429 RESOURCE_EXHAUSTED). Đang tự động đổi sang key tiếp theo...",
                        idx + 1,
                    )
                    self.key_manager.rotate()
                    errors.append(e)
                    continue
                raise
        if errors:
            raise errors[-1]
        raise RuntimeError("Không có Gemini model nào khả dụng trong pool.")


class RotatingChatGoogleGenerativeAI(BaseChatModel):
    """ChatGoogleGenerativeAI with automatic multi-key rotation upon 429 quota exhaustion."""

    models: list[Any] = Field(default_factory=list)
    key_manager: Any = None

    @property
    def _llm_type(self) -> str:
        return "rotating-chat-google-generative-ai"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Any:
        bound_models = [m.bind_tools(tools, **kwargs) for m in self.models]
        return RotatingBoundModel(bound_models=bound_models, key_manager=self.key_manager)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Any:
        errors = []
        n = len(self.models)
        for _ in range(n):
            idx = self.key_manager.current_idx
            model = self.models[idx]
            try:
                return model._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as e:
                err_msg = str(e)
                if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg or "quota" in err_msg.lower():
                    logger.warning("Gemini API key index %d gặp 429, đổi sang key tiếp theo...", idx + 1)
                    self.key_manager.rotate()
                    errors.append(e)
                    continue
                raise
        if errors:
            raise errors[-1]
        raise RuntimeError("Tất cả API keys trong pool đều bị cạn kiệt.")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Any:
        errors = []
        n = len(self.models)
        for _ in range(n):
            idx = self.key_manager.current_idx
            model = self.models[idx]
            try:
                return await model._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as e:
                err_msg = str(e)
                if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg or "quota" in err_msg.lower():
                    logger.warning("Gemini API key index %d gặp 429, đổi sang key tiếp theo...", idx + 1)
                    self.key_manager.rotate()
                    errors.append(e)
                    continue
                raise
        if errors:
            raise errors[-1]
        raise RuntimeError("Tất cả API keys trong pool đều bị cạn kiệt.")


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

    if provider == "fake":
        # Disallow silent fallback to FakeChatModel when primary LLM is a real provider
        if role == "agent_fallback" and settings.LLM_PRIMARY_PROVIDER != "fake":
            raise ValueError(
                "Không được phép fallback âm thầm sang FakeChatModel khi hệ thống cấu hình chạy LLM thật. "
                "Cần cấu hình model dự phòng thật hoặc báo lỗi gián đoạn kết nối minh bạch."
            )
        return FakeChatModel()

    keys = settings.get_gemini_api_keys()
    if not keys:
        raise ValueError(
            f"LLM provider '{provider}' for role '{role}' requires at least one valid GEMINI_API_KEY or GOOGLE_API_KEY."
        )

    if provider == "gemini":
        try:
            if len(keys) == 1:
                return ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=keys[0],
                    temperature=temperature,
                    timeout=30.0,
                )
            # Multi-key rotation pool
            models = [
                ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=k,
                    temperature=temperature,
                    timeout=30.0,
                )
                for k in keys
            ]
            km = GeminiKeyManager(keys)
            return RotatingChatGoogleGenerativeAI(models=models, key_manager=km)
        except Exception as e:
            logger.error("Failed to initialize ChatGoogleGenerativeAI(%s): %s", model_name, e)
            raise RuntimeError(f"Could not initialize Gemini model '{model_name}': {e}") from e

    raise ValueError(f"Unsupported LLM provider '{provider}' for role '{role}'.")
