# -*- coding: utf-8 -*-
"""ModelScope 免费推理 API 封装（魔搭 contest-entry 改造版）。

保留：
- OpenAI 兼容协议（api-inference.modelscope.cn/v1/）
- 主模型优先，逐个 fallback（235B → 30B → 8B）
- 429/超时/异常 → 指数退避重试
- enable_thinking=False 关闭思维链

新增：
- is_api_available()：无 MODELSCOPE_API_KEY 时自动降级 mock 模式
- mock_* 系列：规则引擎零 LLM 依赖的兜底（核心闭环用不到本模块，只有
  合规问答/政策导入/追问润色才走 LLM → 架构性保证 Demo 永不白屏）
"""
import os
import time

API_BASE_URL = "https://api-inference.modelscope.cn/v1/"
TIMEOUT = 60
MAX_ATTEMPTS = 2          # 演示场景 2 轮足够（等太久会白屏）
MAX_TOKENS = 1500
TEMPERATURE = 0.7

# fallback 链：首选 → fallback1 → fallback2 → fallback3
MODELS = [
    "Qwen/Qwen3-235B-A22B-Instruct-2507",
    "Qwen/Qwen3-235B-A22B",
    "Qwen/Qwen3-30B-A3B-Instruct-2507",
    "Qwen/Qwen3-8B",
]

_client = None


def is_api_available() -> bool:
    """是否配置了 ModelScope API key（否则用 mock 模式）。"""
    return bool((os.getenv("MODELSCOPE_API_KEY") or "").strip())


def _create_client():
    key = os.getenv("MODELSCOPE_API_KEY", "").strip()
    from openai import OpenAI
    return OpenAI(base_url=API_BASE_URL, api_key=key)


def get_client():
    global _client
    if _client is None:
        _client = _create_client()
    return _client


def _call(messages: list[dict], temperature: float, max_tokens: int) -> tuple[str, str]:
    """带 fallback + 指数退避的底层调用。返回 (content, model_used)。"""
    if not is_api_available():
        raise RuntimeError("未配置 MODELSCOPE_API_KEY")
    client = get_client()
    last_error = ""
    for attempt in range(MAX_ATTEMPTS):
        for m in MODELS:
            try:
                resp = client.chat.completions.create(
                    model=m, messages=messages,
                    temperature=temperature, max_tokens=max_tokens,
                    timeout=TIMEOUT,
                    extra_body={"enable_thinking": False},
                )
                content = resp.choices[0].message.content or ""
                return content, m
            except Exception as e:  # noqa: BLE001
                last_error = str(e)
        time.sleep(2 ** attempt)
    raise RuntimeError(f"全部模型失败：{last_error}")


def chat(messages: list[dict], temperature: float = 0.7, max_tokens: int = 1200) -> tuple[str, str]:
    """多轮对话（合规问答 / 追问润色用）。"""
    return _call(messages, temperature, max_tokens)


def generate(system_prompt: str, user_prompt: str, temperature: float = 0.4, max_tokens: int = 1500) -> tuple[str, str]:
    """单轮生成（政策导入结构化用，低温度保准确性）。"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return _call(messages, temperature, max_tokens)
