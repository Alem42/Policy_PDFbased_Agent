"""Default API/model catalog seed.

Phase one deliberately seeds Zhipu only. Other providers remain visible in the
key-management UI and can be entered manually, but are not represented here by
partial or speculative data. The list mirrors the Zhipu ``模型 API`` reference
index as checked on 2026-07-29.

Rows used by runtime selection have capability ``embedding`` or ``rerank``.
The remaining rows make every documented Model API interface discoverable in
the "Show all endpoints" view without leaking API keys into this table.
"""

from __future__ import annotations

CAPABILITIES = [
    "chat",
    "chat_async",
    "embedding",
    "rerank",
    "image",
    "image_async",
    "video",
    "audio",
    "voice",
    "tokenizer",
    "ocr",
    "async_result",
]

_ZHIPU = "https://open.bigmodel.cn/api/paas/v4"


def _e(
    capability: str,
    model: str,
    endpoint: str,
    dimensions: int | None = None,
    *,
    notes: str | None = None,
) -> dict:
    return {
        "provider": "zhipu",
        "provider_label": "Zhipu 智谱",
        "capability": capability,
        "model": model,
        "base_url": _ZHIPU,
        "endpoint": endpoint,
        "dimensions": dimensions,
        "openai_compatible": capability
        in {"chat", "chat_async", "embedding", "image", "image_async"},
        "notes": notes,
    }


DEFAULT_CATALOG: list[dict] = [
    # Selectable embedding and reranking models.
    _e(
        "embedding",
        "embedding-3",
        "/embeddings",
        2048,
        notes="可选维度 256/512/1024/2048",
    ),
    _e("embedding", "embedding-2", "/embeddings", 1024, notes="固定 1024 维"),
    _e("rerank", "rerank", "/rerank", notes="文本重排序"),

    # 对话补全：当前官方接口列出的文本模型。
    *[
        _e("chat", model, "/chat/completions", notes="对话补全")
        for model in (
            "glm-5.2",
            "glm-5.1",
            "glm-5-turbo",
            "glm-5",
            "glm-4.7",
            "glm-4.6",
            "glm-4.5-air",
            "glm-4.5-airx",
            "glm-4.5-flash",
            "glm-4-flash-250414",
            "glm-4-flashx-250414",
        )
    ],

    # Remaining Model API interfaces. Operation labels are intentional: these
    # rows are endpoint reference entries, not embedding/rerank picker options.
    _e("chat_async", "对话补全（异步）", "/async/chat/completions"),
    _e("image", "图像生成", "/images/generations"),
    _e("image_async", "图像生成（异步）", "/async/images/generations"),
    _e("tokenizer", "文本分词器", "/tokenizer"),
    _e("audio", "glm-tts", "/audio/speech", notes="文本转语音"),
    _e("audio", "glm-asr-2512", "/audio/transcriptions", notes="语音转文本"),
    _e("voice", "音色复刻", "/voice/clone"),
    _e("voice", "音色列表", "/voice/list"),
    _e("voice", "删除音色", "/voice/delete"),
    _e("ocr", "glm-ocr", "/layout_parsing", notes="文档解析"),
    _e("async_result", "查询异步结果", "/async-result/{id}"),
    _e("video", "视频生成（异步）", "/videos/generations"),
]
