# client.py — 统一 LLM 调用客户端
#
# 所有 Step 共用。封装 Anthropic SDK → DeepSeek v4-pro。
# 自动记录 token 用量，temperature 默认 0.3。

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from src.utils.network import check_proxy, is_proxy_configured

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 响应类型
# ═══════════════════════════════════════════════════════════════


@dataclass
class LLMResponse:
    """LLM 调用响应。

    Fields:
        content: 响应文本
        input_tokens: 输入 token 数
        output_tokens: 输出 token 数
        model: 使用的模型 ID
        finish_reason: 结束原因 (stop, length, tool_calls 等)
    """

    content: str
    input_tokens: int
    output_tokens: int
    model: str
    finish_reason: str

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ═══════════════════════════════════════════════════════════════
# LLM 客户端
# ═══════════════════════════════════════════════════════════════


class LLMClient:
    """统一 LLM 调用客户端。

    从 ~/.claude/settings.json 读取 ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL，
    通过 Anthropic SDK 调用 DeepSeek v4-pro。

    Usage:
        client = LLMClient()
        response = client.chat(
            messages=[{"role": "user", "content": "..."}],
            system="You are a helpful assistant."
        )
        print(response.content)
    """

    def __init__(
        self,
        model: str = "deepseek-v4-pro",
        temperature: float = 0.3,
    ) -> None:
        self._model = model
        self._temperature = temperature

        # ── 读取认证信息 ──
        settings_path = os.path.expanduser("~/.claude/settings.json")
        self._api_key: Optional[str] = None
        self._base_url: str = "https://api.anthropic.com"

        if os.path.exists(settings_path):
            with open(settings_path, encoding="utf-8") as f:
                settings = json.load(f)
            env = settings.get("env", {})
            self._api_key = env.get("ANTHROPIC_AUTH_TOKEN")
            self._base_url = env.get("ANTHROPIC_BASE_URL", self._base_url)

        if not self._api_key:
            logger.warning(
                "ANTHROPIC_AUTH_TOKEN not found in %s. "
                "LLM calls will fail until configured.",
                settings_path,
            )

        self._client: Any = None  # anthropic.Anthropic, lazy init

    # ── Public API ──────────────────────────────────────────

    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 4000,
        tools: Optional[list[dict[str, Any]]] = None,
        system: Optional[str] = None,
        thinking_budget_tokens: Optional[int] = 1600,
    ) -> LLMResponse:
        """同步 LLM 调用。

        Args:
            messages: 对话消息列表 [{"role": "user", "content": "..."}, ...]
            model: 覆盖默认 model
            temperature: 覆盖默认 temperature
            max_tokens: 最大输出 token 数（含 thinking），默认 4000
            tools: 可选的工具定义列表（OpenAI function-calling 格式）
            system: 可选的 system prompt
            thinking_budget_tokens: thinking 预算 token 数。
                None = 不传 thinking 参数（关闭扩展思考）。
                默认 1600，为实际内容保留 max_tokens - 1600。

        Returns:
            LLMResponse，含 content + token 用量

        Raises:
            LLMError: API 调用失败
        """
        self._ensure_client()

        try:
            import anthropic

            kwargs: dict[str, Any] = {
                "model": model or self._model,
                "max_tokens": max_tokens,
                "temperature": temperature if temperature is not None else self._temperature,
                "messages": messages,
            }
            if thinking_budget_tokens is not None:
                kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": min(thinking_budget_tokens, max_tokens - 100),
                }
            if system:
                kwargs["system"] = system
            if tools:
                kwargs["tools"] = self._convert_tools(tools)

            response = self._client.messages.create(**kwargs)

            # ── 提取文本（跳过 thinking blocks）──
            text_parts: list[str] = []
            for block in response.content:
                if hasattr(block, "text") and block.text:
                    text_parts.append(block.text)
                elif hasattr(block, "type") and block.type == "text":
                    text_parts.append(block.text)

            if not text_parts:
                # 边缘情况：thinking block 吃掉了全部 token 预算，
                # text block 不存在或为空。返回 thinking 的尾部作为降级内容。
                logger.warning(
                    "No text blocks in LLM response. "
                    "Likely max_tokens too low — thinking consumed entire budget. "
                    "Falling back to thinking content tail."
                )
                for block in response.content:
                    if hasattr(block, "thinking") and block.thinking:
                        tail = block.thinking[-500:]
                        text_parts.append(f"[FALLBACK from thinking block]: {tail}")
                        break
                if not text_parts:
                    text_parts.append("")

            content = "\n\n".join(text_parts)

            # ── token 用量 ──
            input_tokens = getattr(response.usage, "input_tokens", 0)
            output_tokens = getattr(response.usage, "output_tokens", 0)

            # ── finish reason ──
            finish_reason = getattr(
                response.stop_reason, "end_turn", None
            ) if hasattr(response, "stop_reason") else "unknown"

            logger.debug(
                "LLM call: model=%s, input=%d, output=%d, finish=%s",
                kwargs["model"],
                input_tokens,
                output_tokens,
                finish_reason,
            )

            return LLMResponse(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=kwargs["model"],
                finish_reason=str(finish_reason),
            )

        except Exception as e:
            raise LLMError(
                f"LLM API call failed: {e}"
            ) from e

    def check_connectivity(self) -> bool:
        """检查 LLM API 是否可达。

        检查代理连通性 + API key 存在。
        不做实际的 API 调用（避免消耗 token）。

        Returns:
            True 如果条件满足，False 否则。
        """
        if is_proxy_configured() and not check_proxy():
            logger.warning("LLM connectivity check: proxy configured but DOWN")
            return False
        if not self._api_key:
            logger.warning("LLM connectivity check: no API key")
            return False
        return True

    # ── Internal helpers ────────────────────────────────────

    def _ensure_client(self) -> None:
        """延迟初始化 Anthropic 客户端。"""
        if self._client is not None:
            return

        # Only check proxy if one is explicitly configured
        if is_proxy_configured() and not check_proxy():
            raise LLMError(
                "Proxy is configured (BIOMED_PROXY_HOST/BIOMED_PROXY_PORT) "
                "but unreachable. Start your proxy or unset those env vars "
                "to use direct connection."
            )
        if not self._api_key:
            raise LLMError(
                "ANTHROPIC_AUTH_TOKEN not configured. "
                "Set environment variable ANTHROPIC_AUTH_TOKEN, "
                "or configure it in ~/.claude/settings.json under 'env'."
            )

        import anthropic

        # all_proxy=socks5:// 会让 httpx 尝试 SOCKS 但可能缺 socksio 包。
        # http_proxy/https_proxy 已经足够路由流量，临时清掉 all_proxy。
        saved_env = {}
        for key in ("all_proxy", "ALL_PROXY"):
            if key in os.environ:
                saved_env[key] = os.environ.pop(key)

        try:
            self._client = anthropic.Anthropic(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        finally:
            for key, value in saved_env.items():
                os.environ[key] = value

        logger.info(
            "LLM client initialized: model=%s, base_url=%s",
            self._model,
            self._base_url,
        )

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """将 OpenAI function-calling 格式的工具定义转为 Anthropic tool 格式。

        Anthropic SDK 0.105+ 支持 OpenAI 兼容格式的 tools 参数，
        但字段名略有不同。此处做最小适配。
        """
        anthropic_tools = []
        for tool in tools:
            converted: dict[str, Any] = {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
            }
            params = tool.get("parameters", tool.get("input_schema", {}))
            if params:
                converted["input_schema"] = params
            anthropic_tools.append(converted)
        return anthropic_tools


# ═══════════════════════════════════════════════════════════════
# 异常
# ═══════════════════════════════════════════════════════════════


class LLMError(Exception):
    """LLM API 调用失败。"""
    pass
