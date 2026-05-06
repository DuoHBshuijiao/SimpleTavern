"""SillyTavern MVU directive import agent.

导入期使用：把完整 ST 角色卡上下文交给 LLM，由其通过内存工具写入
SimpleTavern 的角色级 MVU 指令与初始状态表。本模块不做磁盘写入。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.llm.openai_compat import chat_completions_message
from app.schemas import (
    StatusTableDef,
    build_reasoning_request_config,
    filter_reasoning_extra_body_for_upstream,
)
from app.services.st_mvu_compat import extract_st_mvu_import_context, validate_st_mvu_compat_result
from app.mvu_model_resolve import resolve_mvu_model_from_settings
from app.storage import load_settings


@dataclass(frozen=True)
class StMvuImportAgentRunContext:
    base_url: str
    api_key: str
    model: str
    temperature: float | None = None
    max_tool_turns: int = 6
    extra_body: dict[str, Any] | None = None


@dataclass
class _ImportDraft:
    directive: str = ""
    initial_tables: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    worldbook_marks: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0
    finished: bool = False


def _tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "st_mvu_set_directive",
                "description": "写入 SimpleTavern 角色卡的 MVU 指令。必须是可执行的长期维护规则，不要粘贴原始 JS。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directive": {"type": "string", "description": "MVU 运行时指令。"},
                        "summary": {"type": "string", "description": "一句话说明生成依据。"},
                        "warnings": {"type": "array", "items": {"type": "string"}},
                        "worldbookMarks": {"type": "array", "items": {"type": "object"}},
                        "confidence": {"type": "number"},
                    },
                    "required": ["directive"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "st_mvu_define_initial_table",
                "description": "申请一张新会话初始状态栏表格，导入后写入 CharacterCard.initialStateTables。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "columns": {"type": "array", "items": {"type": "string"}},
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "field": {"type": "string"},
                                    "cells": {"type": "object"},
                                },
                                "required": ["field"],
                                "additionalProperties": True,
                            },
                        },
                    },
                    "required": ["name", "columns", "rows"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "st_mvu_finish",
                "description": "确认 MVU 导入分析完成。调用前应已写入 directive，并按需申请初始状态栏。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "warnings": {"type": "array", "items": {"type": "string"}},
                        "worldbookMarks": {"type": "array", "items": {"type": "object"}},
                        "confidence": {"type": "number"},
                    },
                    "additionalProperties": False,
                },
            },
        },
    ]


def _default_run_context() -> StMvuImportAgentRunContext:
    settings = load_settings()
    model = resolve_mvu_model_from_settings(settings)
    if not model:
        raise RuntimeError(
            "MVU 导入 Agent 模型未配置，请在全局设置中指定 MVU 模型或默认模型。",
        )

    base_url = (settings.llm.baseUrl or "").strip()
    api_key = settings.llm.apiKey or ""

    llm_presets = [
        p for p in (settings.apiPresets or [])
        if (getattr(p, "presetKind", None) or "") != "tts"
    ]

    preset_for_model = None
    if llm_presets:
        preset_for_model = next(
            (p for p in llm_presets if p.models and model in p.models),
            None,
        )
    if preset_for_model and (preset_for_model.baseUrl or "").strip():
        base_url = preset_for_model.baseUrl.strip()
        api_key = preset_for_model.apiKey or ""

    if not base_url and llm_presets:
        fb = next((p for p in llm_presets if (p.baseUrl or "").strip()), None)
        if fb:
            base_url = fb.baseUrl.strip()
            api_key = fb.apiKey or ""

    if not base_url:
        raise RuntimeError(
            "MVU 导入 API 基础地址未配置：请在全局设置填写「默认 API 基础地址」，"
            "或确保至少有一个非 TTS 的 API 预设填写了 Base URL。"
        )

    reasoning_cfg = build_reasoning_request_config(settings)
    thinking_enabled = reasoning_cfg["thinking_enabled"]
    extra_body = filter_reasoning_extra_body_for_upstream(model, reasoning_cfg["extra_body"])
    temperature: float | None = None
    if not thinking_enabled:
        temperature = settings.generationDefaults.temperature

    return StMvuImportAgentRunContext(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=temperature,
        extra_body=extra_body,
    )


def _system_prompt() -> str:
    return (
        "你是 SimpleTavern 的 SillyTavern MVU 导入兼容 Agent。"
        "你的任务是在导入时阅读完整 ST 角色卡上下文，理解角色需要维护的状态表和状态更新规则。"
        "必须通过工具写入结果：先调用 st_mvu_set_directive 写入角色卡 MVU 指令，"
        "再按需调用 st_mvu_define_initial_table 申请初始状态栏，最后调用 st_mvu_finish。"
        "不要执行或复刻 Tavern Helper JS；不可转换的 regex_scripts/HTML/UI 脚本也必须作为语义线索理解。"
        "指令应描述运行时如何根据对话维护状态，不要把原始脚本、HTML 或世界书正文整段塞入指令。"
        "状态表字段要来自角色卡中真实有效的变量/状态需求；缺乏依据时使用待观察，而不是编造数值。"
    )


def _tool_result(content: dict[str, Any], tool_call_id: str) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(content, ensure_ascii=False),
    }


def _apply_tool(name: str, args: dict[str, Any], draft: _ImportDraft) -> dict[str, Any]:
    if name == "st_mvu_set_directive":
        directive = str(args.get("directive") or "").strip()
        if not directive:
            return {"ok": False, "error": "directive is required"}
        draft.directive = directive
        if isinstance(args.get("warnings"), list):
            draft.warnings.extend(str(w).strip() for w in args["warnings"] if str(w).strip())
        if isinstance(args.get("worldbookMarks"), list):
            draft.worldbook_marks = args["worldbookMarks"]
        if isinstance(args.get("summary"), str) and args["summary"].strip():
            draft.summary = args["summary"].strip()
        if isinstance(args.get("confidence"), (int, float)):
            draft.confidence = float(args["confidence"])
        return {"ok": True, "directiveLength": len(draft.directive)}

    if name == "st_mvu_define_initial_table":
        try:
            table = StatusTableDef.model_validate({
                "name": str(args.get("name") or "").strip(),
                "columns": args.get("columns"),
                "rows": args.get("rows"),
            })
        except Exception as e:
            return {"ok": False, "error": str(e)}
        draft.initial_tables.append(table.model_dump(mode="json"))
        return {"ok": True, "table": table.model_dump(mode="json")}

    if name == "st_mvu_finish":
        draft.finished = True
        if isinstance(args.get("summary"), str) and args["summary"].strip():
            draft.summary = args["summary"].strip()
        if isinstance(args.get("warnings"), list):
            draft.warnings.extend(str(w).strip() for w in args["warnings"] if str(w).strip())
        if isinstance(args.get("worldbookMarks"), list):
            draft.worldbook_marks = args["worldbookMarks"]
        if isinstance(args.get("confidence"), (int, float)):
            draft.confidence = float(args["confidence"])
        return {"ok": True}

    return {"ok": False, "error": f"unknown tool: {name}"}


async def run_st_mvu_import_agent(
    raw: dict[str, Any],
    *,
    run_ctx: StMvuImportAgentRunContext | None = None,
) -> dict[str, Any]:
    """运行导入期 MVU Agent，返回 validate_st_mvu_compat_result 可接受的结果。"""
    ctx = run_ctx or _default_run_context()
    context = extract_st_mvu_import_context(raw)
    draft = _ImportDraft()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _system_prompt()},
        {
            "role": "user",
            "content": (
                "请分析以下 SillyTavern 角色卡完整有效上下文，并通过工具写入 SimpleTavern MVU 导入结果：\n\n"
                + json.dumps(context, ensure_ascii=False)
            ),
        },
    ]

    for _ in range(ctx.max_tool_turns):
        resp = await chat_completions_message(
            base_url=ctx.base_url,
            api_key=ctx.api_key,
            model=ctx.model,
            messages=messages,
            temperature=ctx.temperature,
            tools=_tools(),
            extra_body=ctx.extra_body,
        )
        assistant_msg: dict[str, Any] = {
            "role": resp.role or "assistant",
            "content": resp.content or "",
        }
        if resp.reasoning_content:
            assistant_msg["reasoning_content"] = resp.reasoning_content
        if resp.tool_calls:
            assistant_msg["tool_calls"] = resp.tool_calls
        messages.append(assistant_msg)

        if not resp.tool_calls:
            break
        for tc in resp.tool_calls:
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            raw_args = str(fn.get("arguments") or "{}")
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {}
            result = _apply_tool(name, args, draft)
            messages.append(_tool_result(result, str(tc.get("id") or name)))
        if draft.finished and draft.directive:
            break

    if not draft.directive and not draft.initial_tables:
        raise RuntimeError("MVU 导入 Agent 未通过工具写入指令或初始状态栏。")

    return validate_st_mvu_compat_result({
        "mode": "directive",
        "applied": True,
        "directive": draft.directive,
        "initialStateTables": draft.initial_tables,
        "worldbookMarks": draft.worldbook_marks,
        "warnings": list(dict.fromkeys(draft.warnings)),
        "confidence": draft.confidence,
        "summary": draft.summary or f"MVU Agent 已生成指令，初始状态表 {len(draft.initial_tables)} 张。",
    })
