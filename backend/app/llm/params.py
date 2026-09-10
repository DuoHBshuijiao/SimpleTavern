"""T-821 参数注册表入口。

思考深度 / Fast / 缓存计划的实现分别在 ``resolution.py`` 与 ``prompt_cache.py``；
本模块按任务卡路径做再导出，避免调用方四处找符号。
"""

from __future__ import annotations

from app.llm.prompt_cache import PromptCachePlan, build_prompt_cache_plan
from app.llm.resolution import (
    build_request_extras,
    clamp_reasoning_effort,
    prepare_llm_request,
    preview_resolution,
    resolve_protocol,
    resolve_request,
)

__all__ = [
    "PromptCachePlan",
    "build_prompt_cache_plan",
    "build_request_extras",
    "clamp_reasoning_effort",
    "prepare_llm_request",
    "preview_resolution",
    "resolve_protocol",
    "resolve_request",
]
