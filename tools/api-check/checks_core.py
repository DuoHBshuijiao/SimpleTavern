"""核心接口的正向和负向检查，依据 docs/specs/BACKEND-API.md。

断言业务结果（改完读回确实变了），不看实现。规格没写的行为不判对错，记为规格未定义。
"""
import io
import json
import re
import time
import zipfile

from harness import assert_envelope, assert_rest_error, check, ensure, equal, unspecified
from mock_upstream import REPLY, USAGE

NOT_FOUND = ("not_found", "character_not_found", "chat_not_found", "worldbook_not_found", "message_not_found")
USER_TEXT = "核心检查用的消息。"


def _character(env, **fields):
    body = {"name": "核心角色", "description": "描述", "firstMessage": "", **fields}
    return env.api.json_ok("POST", "/api/characters", json=body)


def _chat_with_messages(env, *contents):
    character = _character(env)
    chat = env.api.json_ok("POST", "/api/chats", json={"characterId": character["id"], "title": "核心会话"})
    ids = []
    for index, content in enumerate(contents):
        role = "user" if index % 2 == 0 else "assistant"
        saved = env.api.json_ok("POST", f"/api/chats/{chat['id']}/messages", json={"role": role, "content": content})
        ids.append(saved["messages"][-1]["id"])
    return chat["id"], ids, character["id"]


def _openai_preset(env, base=None, fault="ok", key=None):
    api_key = env.fixtures["openai_key"] if key is None else key
    preset = {"id": "core-openai", "name": "核心 OpenAI", "baseUrl": base or (env.mock.url + "/v1"), "apiKey": api_key, "models": ["mock-model"],
              "protocol": "openai_compatible_chat", "promptCache": {"mode": "off"}}
    env.put_preset(preset)
    env.mock.reset(fault=fault)
    env.mock.api_key = env.fixtures["openai_key"]
    env.mock.expect_model = None
    return preset["id"]


# ---------- 通用约定 ----------
@check("core.request_id.echo_valid", "合法的 X-Request-Id 原样回传")
def _(env):
    value = "check-request-0001"
    response = env.api.get("/api/health", headers={"X-Request-Id": value})
    equal(response.headers.get("x-request-id"), value, "响应头")
    bad = env.api.get("/api/characters/no-such-id", headers={"X-Request-Id": value})
    equal(bad.json().get("requestId"), value, "错误信封 requestId")


@check("core.request_id.ignore_invalid", "不合法的 X-Request-Id 被忽略，服务端生成 req_ 加 32 位 hex")
def _(env):
    response = env.api.get("/api/health", headers={"X-Request-Id": "bad id!"})
    ensure(re.fullmatch(r"req_[0-9a-f]{32}", response.headers.get("x-request-id") or ""), f"应为服务端生成的 id：{response.headers.get('x-request-id')}")


@check("core.health", "GET /api/health 有规格列出的观测字段")
def _(env):
    body = env.api.json_ok("GET", "/api/health")
    equal(body.get("ok"), True, "ok")
    for key in ("locks", "contentRegex", "ttsCache", "migrationWarnings"):
        ensure(key in body, f"缺少 {key}")
    ensure(body["locks"].get("timeoutSec") == 30, f"locks.timeoutSec 应为 30：{body['locks'].get('timeoutSec')}")


# ---------- 角色 ----------
@check("core.character.create_read", "新建角色后，读回和列表都是提交的内容")
def _(env):
    created = _character(env, name="阿青", description="巷口的包子铺老板", personality="沉默", scenario="深夜", systemPrompt="SP", attachedWorldBookIds=["wb1"])
    ensure(created.get("id"), "应生成 id")
    ensure(created.get("createdAt") and created.get("updatedAt"), "应设置 createdAt 和 updatedAt")
    read = env.api.json_ok("GET", f"/api/characters/{created['id']}")
    for key, value in (("name", "阿青"), ("description", "巷口的包子铺老板"), ("personality", "沉默"), ("scenario", "深夜"), ("systemPrompt", "SP"), ("attachedWorldBookIds", ["wb1"])):
        equal(read.get(key), value, key)
    listed = env.api.json_ok("GET", "/api/characters")
    ensure(any(c["id"] == created["id"] and c["name"] == "阿青" for c in listed), "列表里应有这个角色")


@check("core.character.update", "更新后读回变了；createdAt 不变；URL 的 id 优先；updatedAt 前进")
def _(env):
    created = _character(env, name="旧名字")
    time.sleep(0.02)
    updated = env.api.json_ok("PUT", f"/api/characters/{created['id']}", json={**created, "id": "another-id", "name": "新名字", "createdAt": "2000-01-01T00:00:00Z"})
    equal(updated["id"], created["id"], "id 以 URL 为准")
    read = env.api.json_ok("GET", f"/api/characters/{created['id']}")
    equal(read["name"], "新名字", "name")
    equal(read["createdAt"], created["createdAt"], "createdAt 不变")
    ensure(read["updatedAt"] != created["updatedAt"], "updatedAt 应更新")
    equal(env.api.get("/api/characters/another-id").status_code, 404, "不该写出 another-id")


@check("core.character.delete_cascades", "删除角色后，角色和它的会话都读不到了")
def _(env):
    chat_id, _ids, character_id = _chat_with_messages(env, "你好")
    equal(env.api.json_ok("GET", f"/api/chats/{chat_id}")["messages"][0]["content"], "你好", "删除前会话确实存在")
    env.api.json_ok("DELETE", f"/api/characters/{character_id}")
    assert_rest_error(env.api.get(f"/api/characters/{character_id}"), 404, NOT_FOUND)
    assert_rest_error(env.api.get(f"/api/chats/{chat_id}"), 404, NOT_FOUND)
    ensure(all(c["id"] != character_id for c in env.api.json_ok("GET", "/api/characters")), "列表不该再有这个角色")


@check("core.character.get_missing", "读不存在的角色返回 404 和错误信封")
def _(env):
    assert_rest_error(env.api.get("/api/characters/no-such-id"), 404, NOT_FOUND)


@check("core.character.update_missing", "更新不存在的角色：不是 500；如果创建了，读回要一致")
def _(env):
    response = env.api.put("/api/characters/no-such-update", json={"name": "x"})
    ensure(response.status_code < 500, f"不能是 500：{response.text[:200]}")
    if response.status_code == 200:
        equal(env.api.json_ok("GET", "/api/characters/no-such-update")["name"], "x", "读回")
        unspecified("PUT 不存在的角色会直接创建它，返回 200（规格没写；而 PUT 不存在的会话返回 404，两者不一致）")
    assert_rest_error(response, 404, NOT_FOUND)


@check("core.character.delete_missing", "删除不存在的角色不是 500，也不声称删了什么")
def _(env):
    response = env.api.delete("/api/characters/no-such-delete")
    ensure(response.status_code < 500, f"不能是 500：{response.text[:200]}")
    if response.status_code == 200:
        unspecified(f"删除不存在的角色返回 200：{response.text[:120]}（规格只列了 200 和 422，幂等还是 404 没写）")
    assert_rest_error(response, 404, NOT_FOUND)


@check("core.character.invalid_type", "字段类型错误返回 422 和字段位置，且不写入")
def _(env):
    before = len(env.api.json_ok("GET", "/api/characters"))
    body = assert_rest_error(env.api.post("/api/characters", json={"name": 123}), 422, ("request_validation_failed",))
    ensure("name" in str(body.get("detail")), f"detail 应指出字段：{body.get('detail')}")
    equal(len(env.api.json_ok("GET", "/api/characters")), before, "不该新增角色")


@check("core.character.invalid_nested", "attachedWorldBookIds 类型错误返回 422")
def _(env):
    assert_rest_error(env.api.post("/api/characters", json={"name": "x", "attachedWorldBookIds": "not-a-list"}), 422, ("request_validation_failed",))


@check("core.character.not_json", "请求体不是 JSON 时返回 422，不是 500")
def _(env):
    assert_rest_error(env.api.post("/api/characters", content=b"{not json", headers={"Content-Type": "application/json"}), 422, ("request_validation_failed",))


@check("core.character.path_traversal", "路径穿越形式的 id 读不到数据目录里的其他文件")
def _(env):
    for raw in ("..%2F..%2Fsettings", "..%5C..%5Csettings", "%2e%2e%2fsettings"):
        response = env.api.get(f"/api/characters/{raw}")
        ensure(response.status_code in (400, 404, 422), f"{raw} 应被拒绝，实际 {response.status_code}：{response.text[:200]}")
        ensure("apiPresets" not in response.text, f"{raw} 读到了设置文件")


# ---------- 会话 ----------
@check("core.chat.create_read", "新建会话后读回；开场白成为第一条助手消息")
def _(env):
    character = _character(env, firstMessage="你来了。")
    chat = env.api.json_ok("POST", "/api/chats", json={"characterId": character["id"], "title": "第一次"})
    read = env.api.json_ok("GET", f"/api/chats/{chat['id']}")
    equal(read["characterId"], character["id"], "characterId")
    equal(read["title"], "第一次", "title")
    equal(read["isGroup"], False, "isGroup")
    equal([(m["role"], m["content"]) for m in read["messages"]], [("assistant", "你来了。")], "开场白")


@check("core.chat.empty_first_message", "没有开场白的角色，新会话没有消息")
def _(env):
    character = _character(env, firstMessage="")
    chat = env.api.json_ok("POST", "/api/chats", json={"characterId": character["id"]})
    equal(env.api.json_ok("GET", f"/api/chats/{chat['id']}")["messages"], [], "messages")


@check("core.chat.create_for_missing_character", "给不存在的角色建会话返回 404，不是假成功")
def _(env):
    assert_rest_error(env.api.post("/api/chats", json={"characterId": "no-such-character"}), 404, NOT_FOUND)


@check("core.chat.create_missing_field", "缺少 characterId 返回 422")
def _(env):
    assert_rest_error(env.api.post("/api/chats", json={"title": "x"}), 422, ("request_validation_failed",))


@check("core.chat.list", "按角色列会话；summary=true 不含 messages")
def _(env):
    chat_id, _ids, character_id = _chat_with_messages(env, "你好")
    full = env.api.json_ok("GET", "/api/chats", params={"characterId": character_id})
    equal([c["id"] for c in full], [chat_id], "完整列表")
    equal(full[0]["messages"][0]["content"], "你好", "完整列表带消息")
    summary = env.api.json_ok("GET", "/api/chats", params={"characterId": character_id, "summary": "true"})
    equal([c["id"] for c in summary], [chat_id], "摘要列表")
    ensure(not summary[0].get("messages"), "摘要不应带 messages")


@check("core.chat.list_requires_character", "GET /api/chats 不带 characterId 返回 422")
def _(env):
    assert_rest_error(env.api.get("/api/chats"), 422, ("request_validation_failed",))


@check("core.chat.update_title", "更新标题和覆盖设置后读回变了")
def _(env):
    chat_id, _ids, _character_id = _chat_with_messages(env)
    env.api.json_ok("PUT", f"/api/chats/{chat_id}", json={"title": "新标题", "overrides": {"prompt": "会话提示", "params": {"temperature": 0.3}}})
    read = env.api.json_ok("GET", f"/api/chats/{chat_id}")
    equal(read["title"], "新标题", "title")
    equal(read["overrides"]["prompt"], "会话提示", "overrides.prompt")
    equal(read["overrides"]["params"]["temperature"], 0.3, "overrides.params.temperature")


@check("core.chat.update_invalid", "覆盖设置类型错误返回 422，原值不变")
def _(env):
    chat_id, _ids, _character_id = _chat_with_messages(env)
    env.api.json_ok("PUT", f"/api/chats/{chat_id}", json={"title": "原标题"})
    assert_rest_error(env.api.put(f"/api/chats/{chat_id}", json={"title": "改了", "overrides": "not-object"}), 422, ("request_validation_failed",))
    equal(env.api.json_ok("GET", f"/api/chats/{chat_id}")["title"], "原标题", "title 不变")


@check("core.chat.missing", "不存在的会话：读、改、删都不是 500 或假成功")
def _(env):
    assert_rest_error(env.api.get("/api/chats/no-such-chat"), 404, NOT_FOUND)
    assert_rest_error(env.api.put("/api/chats/no-such-chat", json={"title": "x"}), 404, NOT_FOUND)
    response = env.api.delete("/api/chats/no-such-chat")
    ensure(response.status_code < 500, f"删除不能是 500：{response.text[:200]}")
    if response.status_code == 200:
        unspecified(f"删除不存在的会话返回 200：{response.text[:120]}（规格没写）")
    assert_rest_error(response, 404, NOT_FOUND)


@check("core.chat.delete", "删除后读不到，也不在角色的列表里")
def _(env):
    chat_id, _ids, character_id = _chat_with_messages(env, "你好")
    equal([c["id"] for c in env.api.json_ok("GET", "/api/chats", params={"characterId": character_id})], [chat_id], "删除前列表里有这个会话")
    env.api.json_ok("DELETE", f"/api/chats/{chat_id}")
    assert_rest_error(env.api.get(f"/api/chats/{chat_id}"), 404, NOT_FOUND)
    equal(env.api.json_ok("GET", "/api/chats", params={"characterId": character_id}), [], "列表")


@check("core.chat.search", "全文检索命中对应消息，查不到时为空，缺 q 返回 422")
def _(env):
    chat_id, ids, _character_id = _chat_with_messages(env, "第一条普通内容", "第二条含暗号青鸟")
    found = env.api.json_ok("GET", f"/api/chats/{chat_id}/search", params={"q": "青鸟"})
    text = json.dumps(found, ensure_ascii=False)
    ensure(ids[1] in text, f"应命中第二条：{text[:300]}")
    ensure(ids[0] not in text, f"不应命中第一条：{text[:300]}")
    empty = env.api.json_ok("GET", f"/api/chats/{chat_id}/search", params={"q": "没有这个词"})
    ensure(ids[1] not in json.dumps(empty, ensure_ascii=False), "不该有结果")
    assert_rest_error(env.api.get(f"/api/chats/{chat_id}/search"), 422, ("request_validation_failed",))


@check("core.chat.fork", "分叉保留锚点及之前的消息，记录来源，原会话不变")
def _(env):
    chat_id, ids, _character_id = _chat_with_messages(env, "一", "二", "三", "四")
    fork = env.api.json_ok("POST", f"/api/chats/{chat_id}/fork", json={"forkAtMessageId": ids[1], "newChatName": "分叉"})
    ensure(fork["id"] != chat_id, "应是新会话")
    equal([m["content"] for m in fork["messages"]], ["一", "二"], "分叉的消息")
    equal(fork.get("forkedFromChatId"), chat_id, "forkedFromChatId")
    equal(fork.get("forkedFromMessageId"), ids[1], "forkedFromMessageId")
    equal(fork.get("title"), "分叉", "newChatName")
    equal([m["content"] for m in env.api.json_ok("GET", f"/api/chats/{chat_id}")["messages"]], ["一", "二", "三", "四"], "原会话不变")
    lineage = env.api.json_ok("GET", f"/api/chats/{chat_id}/fork-lineage")
    ensure(fork["id"] in json.dumps(lineage), f"源会话的溯源应列出分叉：{json.dumps(lineage)[:300]}")


@check("core.chat.fork_missing", "从不存在的消息或会话分叉不是 500 或假成功")
def _(env):
    chat_id, _ids, _character_id = _chat_with_messages(env, "一")
    assert_rest_error(env.api.post(f"/api/chats/{chat_id}/fork", json={"forkAtMessageId": "no-such"}), 404, NOT_FOUND)
    assert_rest_error(env.api.post("/api/chats/no-such-chat/fork", json={"forkAtMessageId": "x"}), 404, NOT_FOUND)


# ---------- 消息 ----------
@check("core.message.append", "追加消息后按顺序读回")
def _(env):
    chat_id, _ids, _character_id = _chat_with_messages(env, "第一条", "第二条")
    read = env.api.json_ok("GET", f"/api/chats/{chat_id}")
    equal([(m["role"], m["content"]) for m in read["messages"]], [("user", "第一条"), ("assistant", "第二条")], "消息")
    ensure(all(m.get("id") and m.get("ts") for m in read["messages"]), "每条消息应有 id 和 ts")


@check("core.message.append_invalid", "非法 role、缺 content、错类型返回 422，且不写入")
def _(env):
    chat_id, _ids, _character_id = _chat_with_messages(env, "第一条")
    for body in ({"role": "wizard", "content": "x"}, {"role": "user"}, {"role": "user", "content": 123}):
        assert_rest_error(env.api.post(f"/api/chats/{chat_id}/messages", json=body), 422, ("request_validation_failed",))
    equal(len(env.api.json_ok("GET", f"/api/chats/{chat_id}")["messages"]), 1, "消息数不变")


@check("core.message.append_missing_chat", "向不存在的会话追加返回 404")
def _(env):
    assert_rest_error(env.api.post("/api/chats/no-such-chat/messages", json={"role": "user", "content": "x"}), 404, NOT_FOUND)


@check("core.message.update", "更新消息后读回变了，其他消息不变")
def _(env):
    chat_id, ids, _character_id = _chat_with_messages(env, "原文", "回复")
    env.api.json_ok("PUT", f"/api/chats/{chat_id}/messages/{ids[0]}", json={"role": "user", "content": "改后的文字"})
    read = env.api.json_ok("GET", f"/api/chats/{chat_id}")
    equal([m["content"] for m in read["messages"]], ["改后的文字", "回复"], "消息内容")
    equal(read["messages"][0]["id"], ids[0], "id 不变")


@check("core.message.update_missing", "更新不存在的消息返回 404")
def _(env):
    chat_id, _ids, _character_id = _chat_with_messages(env, "原文")
    assert_rest_error(env.api.put(f"/api/chats/{chat_id}/messages/no-such", json={"role": "user", "content": "x"}), 404, NOT_FOUND)
    equal([m["content"] for m in env.api.json_ok("GET", f"/api/chats/{chat_id}")["messages"]], ["原文"], "消息不变")


@check("core.message.delete", "删除后读回少了这一条，其他消息和顺序不变")
def _(env):
    chat_id, ids, _character_id = _chat_with_messages(env, "一", "二", "三")
    env.api.json_ok("DELETE", f"/api/chats/{chat_id}/messages/{ids[1]}")
    equal([m["content"] for m in env.api.json_ok("GET", f"/api/chats/{chat_id}")["messages"]], ["一", "三"], "消息")


@check("core.message.delete_missing", "删除不存在的消息不是 500，也不动现有消息")
def _(env):
    chat_id, _ids, _character_id = _chat_with_messages(env, "一")
    response = env.api.delete(f"/api/chats/{chat_id}/messages/no-such")
    ensure(response.status_code < 500, f"不能是 500：{response.text[:200]}")
    equal([m["content"] for m in env.api.json_ok("GET", f"/api/chats/{chat_id}")["messages"]], ["一"], "消息不变")
    if response.status_code == 200:
        unspecified("删除不存在的消息返回 200（规格没写）")
    assert_rest_error(response, 404, NOT_FOUND)


# ---------- 世界书 ----------
def _worldbook(env, **fields):
    body = {"name": "核心世界书", "entries": [{"title": "条目一", "regex": "长廊", "content": "长廊很长", "enabled": True, "orderIndex": 0}], **fields}
    return env.api.json_ok("POST", "/api/worldbooks", json=body)


@check("core.worldbook.create_read", "新建世界书后读回和列表都一致")
def _(env):
    book = _worldbook(env, globalActive=True)
    read = env.api.json_ok("GET", f"/api/worldbooks/{book['id']}")
    equal(read["name"], "核心世界书", "name")
    equal(read["globalActive"], True, "globalActive")
    equal([(e["title"], e["regex"], e["content"], e["enabled"]) for e in read["entries"]], [("条目一", "长廊", "长廊很长", True)], "entries")
    ensure(any(b["id"] == book["id"] for b in env.api.json_ok("GET", "/api/worldbooks")), "列表里应有")


@check("core.worldbook.update", "更新条目后读回变了")
def _(env):
    book = _worldbook(env)
    entries = [{"title": "条目二", "regex": "灯", "content": "灯很亮", "enabled": False, "orderIndex": 1}]
    env.api.json_ok("PUT", f"/api/worldbooks/{book['id']}", json={**book, "name": "改名", "entries": entries})
    read = env.api.json_ok("GET", f"/api/worldbooks/{book['id']}")
    equal(read["name"], "改名", "name")
    equal([(e["title"], e["enabled"]) for e in read["entries"]], [("条目二", False)], "entries")


@check("core.worldbook.delete", "删除后读不到，也不在列表里")
def _(env):
    book = _worldbook(env)
    equal(env.api.json_ok("GET", f"/api/worldbooks/{book['id']}")["name"], "核心世界书", "删除前世界书确实存在")
    env.api.json_ok("DELETE", f"/api/worldbooks/{book['id']}")
    assert_rest_error(env.api.get(f"/api/worldbooks/{book['id']}"), 404, NOT_FOUND)
    ensure(all(b["id"] != book["id"] for b in env.api.json_ok("GET", "/api/worldbooks")), "列表不该再有")


@check("core.worldbook.invalid", "缺 name 或 entries 类型错误返回 422，且不写入")
def _(env):
    before = len(env.api.json_ok("GET", "/api/worldbooks"))
    assert_rest_error(env.api.post("/api/worldbooks", json={"entries": []}), 422, ("request_validation_failed",))
    assert_rest_error(env.api.post("/api/worldbooks", json={"name": "x", "entries": "bad"}), 422, ("request_validation_failed",))
    equal(len(env.api.json_ok("GET", "/api/worldbooks")), before, "不该新增")


@check("core.worldbook.get_missing", "读不存在的世界书返回 404")
def _(env):
    assert_rest_error(env.api.get("/api/worldbooks/no-such-book"), 404, NOT_FOUND)


@check("core.worldbook.update_missing", "更新不存在的世界书：不是 500；如果创建了，读回要一致")
def _(env):
    response = env.api.put("/api/worldbooks/no-such-update", json={"name": "x"})
    ensure(response.status_code < 500, f"不能是 500：{response.text[:200]}")
    if response.status_code == 200:
        equal(env.api.json_ok("GET", "/api/worldbooks/no-such-update")["name"], "x", "读回")
        unspecified("PUT 不存在的世界书会直接创建它，返回 200（规格没写）")
    assert_rest_error(response, 404, NOT_FOUND)


def _lore_book(env, **fields):
    entries = [{"title": "暗号", "regex": "青鸟", "content": "WBMARKER-青鸟的传说", "enabled": True, "orderIndex": 0},
               {"title": "停用", "regex": "青鸟", "content": "WBMARKER-停用条目", "enabled": False, "orderIndex": 1}]
    return _worldbook(env, entries=entries, **fields)


def _sent_for(env, chat_id, message):
    env.mock.reset()
    env.mock.api_key = env.fixtures["openai_key"]
    result = env.generate(chat_id, message)
    ensure(result.succeeded, result.summary())
    return json.dumps(env.mock.calls("openai")[0].json, ensure_ascii=False)


@check("core.worldbook.injected_global", "全局世界书：关键词命中才注入；停用的条目不注入；移除后不再注入")
def _(env):
    preset_id = _openai_preset(env)
    env.set_stream(True)
    book = _lore_book(env, globalActive=True)
    try:
        hit = _sent_for(env, env.new_chat(preset_id, "mock-model"), "你听说过青鸟吗？")
        ensure("WBMARKER-青鸟的传说" in hit, "命中时内容应发给上游")
        ensure("WBMARKER-停用条目" not in hit, "停用的条目不该注入")
        miss = _sent_for(env, env.new_chat(preset_id, "mock-model"), "今天天气不错。")
        ensure("WBMARKER" not in miss, "没有命中时不该注入")
        excluded = env.new_chat(preset_id, "mock-model")
        env.api.json_ok("PUT", f"/api/chats/{excluded}", json={"overrides": {"presetId": preset_id, "params": {"model": "mock-model"}, "worldBookGlobalExclusions": [book["id"]]}})
        ensure("WBMARKER" not in _sent_for(env, excluded, "你听说过青鸟吗？"), "规格：从本会话移除的全局世界书，生成时不再注入")
    finally:
        env.api.json_ok("DELETE", f"/api/worldbooks/{book['id']}")


@check("core.worldbook.injected_session", "绑定到会话的世界书（sessionChatIds）命中时注入，其他会话不受影响")
def _(env):
    preset_id = _openai_preset(env)
    env.set_stream(True)
    bound = env.new_chat(preset_id, "mock-model")
    other = env.new_chat(preset_id, "mock-model")
    book = _lore_book(env, sessionChatIds=[bound])
    try:
        ensure("WBMARKER-青鸟的传说" in _sent_for(env, bound, "你听说过青鸟吗？"), "绑定的会话应注入")
        ensure("WBMARKER" not in _sent_for(env, other, "你听说过青鸟吗？"), "未绑定的会话不该注入")
    finally:
        env.api.json_ok("DELETE", f"/api/worldbooks/{book['id']}")


@check("core.worldbook.attachment_note", "记录只设 worldBookAttachments 时是否注入")
def _(env):
    preset_id = _openai_preset(env)
    env.set_stream(True)
    book = _lore_book(env)
    chat_id = env.new_chat(preset_id, "mock-model")
    attachment = {"worldBookId": book["id"], "scanDepth": 5, "insertDepth": 1}
    saved = env.api.json_ok("PUT", f"/api/chats/{chat_id}", json={"overrides": {"presetId": preset_id, "params": {"model": "mock-model"}, "worldBookIds": [book["id"]], "worldBookAttachments": [attachment]}})
    equal(saved["overrides"]["worldBookAttachments"][0]["worldBookId"], book["id"], "绑定保存")
    sent = _sent_for(env, chat_id, "你听说过青鸟吗？")
    env.api.json_ok("DELETE", f"/api/worldbooks/{book['id']}")
    unspecified(f"会话只设 worldBookIds 和 worldBookAttachments、不设 sessionChatIds 时，命中关键词{'会' if 'WBMARKER' in sent else '不会'}注入（规格称附件是“会话内绑定的一本世界书”，但没写它单独能否触发注入）")


# ---------- 设置 ----------
@check("core.settings.round_trip", "修改设置后读回变了")
def _(env):
    settings = env.settings()
    settings.update(themeId="violet", messageFontSize=18, pageBackgroundOpacity=0.29, worldBookEntryScanDepthDefault=7, reasoningEchoBack="off")
    env.api.json_ok("PUT", "/api/settings", json=settings)
    read = env.settings()
    for key in ("themeId", "messageFontSize", "pageBackgroundOpacity", "worldBookEntryScanDepthDefault", "reasoningEchoBack"):
        equal(read[key], settings[key], key)
    env.update_settings(reasoningEchoBack="preset")


@check("core.settings.preset_round_trip", "预设的协议、鉴权风格和 providerParams 读回不变")
def _(env):
    preset = {"id": "core-roundtrip", "name": "往返", "baseUrl": "http://127.0.0.1:1", "apiKey": "k", "models": ["m"], "protocol": "anthropic_messages", "authStyle": "bearer", "providerParams": {"region": "us-east-1"}}
    env.put_preset(preset)
    read = [p for p in env.settings()["apiPresets"] if p["id"] == "core-roundtrip"][0]
    for key in ("name", "baseUrl", "models", "protocol", "authStyle", "providerParams"):
        equal(read[key], preset[key], key)


@check("core.settings.preset_defaults", "没写 protocol 的预设补默认值 openai_compatible_chat")
def _(env):
    env.put_preset({"id": "core-default", "name": "默认", "baseUrl": "http://127.0.0.1:1", "apiKey": "k"})
    read = [p for p in env.settings()["apiPresets"] if p["id"] == "core-default"][0]
    equal(read["protocol"], "openai_compatible_chat", "protocol")


def _settings_rejected(env, changes, label):
    before = env.settings()
    body = {**before, **changes}
    assert_rest_error(env.api.put("/api/settings", json=body), 422, ("request_validation_failed",), label=label)
    after = env.settings()
    for key in changes:
        equal(after.get(key), before.get(key), f"{key} 不变")


@check("core.settings.out_of_range", "超出范围的数值返回 422，原值不变（规格写了范围的字段）")
def _(env):
    _settings_rejected(env, {"webgpuBackgroundTargetFps": 500}, "帧率超范围")
    _settings_rejected(env, {"pageBackgroundOpacity": 2}, "透明度超范围")
    _settings_rejected(env, {"ttsAudioCacheLimitMb": 1}, "缓存上限超范围")


@check("core.settings.wrong_type", "字段类型错误返回 422，原值不变")
def _(env):
    _settings_rejected(env, {"apiPresets": "not-a-list"}, "apiPresets 错类型")
    _settings_rejected(env, {"llm": "not-an-object"}, "llm 错类型")
    _settings_rejected(env, {"reasoningEchoBack": "maybe"}, "枚举值不对")


# ---------- 备份 ----------
def _backup(env, scope):
    response = env.api.get("/api/settings/backup", params={"scope": scope})
    equal(response.status_code, 200, f"备份 {scope} 的状态")
    try:
        archive = zipfile.ZipFile(io.BytesIO(response.content))
    except zipfile.BadZipFile as exc:
        raise AssertionError(f"备份 {scope} 不是 ZIP：{response.content[:80]!r}") from exc
    ensure(archive.testzip() is None, f"备份 {scope} 的 ZIP 损坏")
    return response.content, archive


@check("core.backup.scopes", "三种范围的 ZIP：basic 只有设置，with_characters 加角色，with_chats 加会话")
def _(env):
    chat_id, _ids, character_id = _chat_with_messages(env, "备份范围")
    _content, basic = _backup(env, "basic")
    names = basic.namelist()
    ensure(any("settings" in n for n in names), f"basic 应有设置：{names[:20]}")
    ensure(not any(character_id in n or chat_id in n for n in names), f"basic 不应有角色或会话：{names[:20]}")
    _content, with_characters = _backup(env, "with_characters")
    ensure(any(character_id in n for n in with_characters.namelist()), f"with_characters 应有这个角色：{with_characters.namelist()[:20]}")
    ensure(not any(chat_id in n for n in with_characters.namelist()), "with_characters 不应有会话")
    _content, with_chats = _backup(env, "with_chats")
    ensure(any(chat_id in n for n in with_chats.namelist()), f"with_chats 应有这个会话：{with_chats.namelist()[:20]}")


@check("core.backup.invalid_scope", "不认识的 scope 不是 500，也不能静默退回别的范围")
def _(env):
    response = env.api.get("/api/settings/backup", params={"scope": "everything"})
    ensure(response.status_code < 500, f"不能是 500：{response.text[:200]}")
    if response.status_code == 200:
        unspecified("不认识的 scope 返回 200 并给出了某个范围的备份（规格只写了三种范围，没写非法值的处理）")
    ensure(response.status_code in (400, 422), f"应是 4xx：{response.status_code}")
    assert_envelope(response.json())


@check("core.backup.restore", "with_chats 备份导入到另一个空数据目录，角色、会话、消息、世界书、设置都能读回")
def _(env):
    book = _worldbook(env, name="备份世界书")
    character = _character(env, name="备份角色", description="备份描述", attachedWorldBookIds=[book["id"]])
    chat = env.api.json_ok("POST", "/api/chats", json={"characterId": character["id"], "title": "备份会话"})
    for role, content in (("user", "备份消息一"), ("assistant", "备份消息二")):
        env.api.json_ok("POST", f"/api/chats/{chat['id']}/messages", json={"role": role, "content": content})
    env.update_settings(themeId="amber", messageFontSize=21)
    env.put_preset({"id": "backup-preset", "name": "备份预设", "baseUrl": "http://127.0.0.1:1", "apiKey": "backup-api-key-value", "models": ["m"], "protocol": "anthropic_messages"})
    content, _archive = _backup(env, "with_chats")

    target = env.second_backend()
    equal(target.json_ok("GET", "/api/characters"), [], "目标应是空数据目录")
    response = target.post("/api/import", files={"file": ("backup.zip", content, "application/zip")})
    equal(response.status_code, 200, f"导入状态 {response.text[:300]}")
    result = response.json()
    ensure("imported" in result and "warnings" in result, f"导入结果应有 imported 和 warnings：{str(result)[:300]}")

    read = target.get(f"/api/characters/{character['id']}")
    equal(read.status_code, 200, f"角色应恢复，导入结果 {str(result)[:300]}")
    equal(read.json()["name"], "备份角色", "角色名")
    equal(read.json()["description"], "备份描述", "角色描述")
    chat_read = target.get(f"/api/chats/{chat['id']}")
    equal(chat_read.status_code, 200, "会话应恢复")
    equal(chat_read.json()["title"], "备份会话", "会话标题")
    equal([(m["role"], m["content"]) for m in chat_read.json()["messages"]], [("user", "备份消息一"), ("assistant", "备份消息二")], "消息")
    listed = target.json_ok("GET", "/api/chats", params={"characterId": character["id"]})
    ensure(any(c["id"] == chat["id"] for c in listed), "恢复后会话应在角色的列表里")
    restored_book = target.get(f"/api/worldbooks/{book['id']}")
    equal(restored_book.status_code, 200, "世界书应恢复")
    equal(restored_book.json()["name"], "备份世界书", "世界书名")
    settings = target.json_ok("GET", "/api/settings")
    equal(settings["themeId"], "amber", "设置 themeId")
    equal(settings["messageFontSize"], 21, "设置 messageFontSize")
    ensure(any(p["id"] == "backup-preset" for p in settings["apiPresets"]), "预设应恢复")


@check("core.backup.keys_note", "记录备份是否含 API Key")
def _(env):
    env.put_preset({"id": "backup-key", "name": "含 Key", "baseUrl": "http://127.0.0.1:1", "apiKey": "BACKUPKEYMARKER1234567890", "models": ["m"]})
    _content, archive = _backup(env, "basic")
    contained = any(b"BACKUPKEYMARKER1234567890" in archive.read(n) for n in archive.namelist())
    unspecified(f"basic 备份{'含' if contained else '不含'} API Key 明文（规格只写了“设置备份不包含令牌”，指 OAuth；T-814 要作者记录这一点）")


@check("core.import.garbage", "导入不是备份的文件时返回错误信封，不是 500，也不写入")
def _(env):
    before = len(env.api.json_ok("GET", "/api/characters"))
    response = env.api.post("/api/import", files={"file": ("garbage.zip", b"this is not a zip", "application/zip")})
    ensure(response.status_code < 500, f"不能是 500：{response.status_code} {response.text[:200]}")
    if response.status_code == 200:
        result = response.json()
        ensure(not result.get("imported"), f"垃圾文件不能算导入成功：{str(result)[:300]}")
        unspecified(f"垃圾文件返回 200 且 imported 为空：{str(result)[:160]}（规格没写失败时的状态码）")
    assert_envelope(response.json())
    equal(len(env.api.json_ok("GET", "/api/characters")), before, "不该新增角色")


@check("core.import.missing_file", "导入不带文件返回 422")
def _(env):
    assert_rest_error(env.api.post("/api/import"), 422, ("request_validation_failed",))


@check("core.restart.persists", "数据落盘：后端重启后，设置、角色、会话和世界书都还在")
def _(env):
    target = env.second_backend()
    settings = target.json_ok("GET", "/api/settings")
    settings["themeId"] = "rose"
    target.json_ok("PUT", "/api/settings", json=settings)
    character = target.json_ok("POST", "/api/characters", json={"name": "重启角色"})
    chat = target.json_ok("POST", "/api/chats", json={"characterId": character["id"]})
    target.json_ok("POST", f"/api/chats/{chat['id']}/messages", json={"role": "user", "content": "重启前的消息"})
    book = target.json_ok("POST", "/api/worldbooks", json={"name": "重启世界书"})
    target = env.restart_second()
    equal(target.json_ok("GET", "/api/settings")["themeId"], "rose", "themeId")
    equal(target.json_ok("GET", f"/api/characters/{character['id']}")["name"], "重启角色", "角色")
    equal(target.json_ok("GET", f"/api/chats/{chat['id']}")["messages"][-1]["content"], "重启前的消息", "消息")
    equal(target.json_ok("GET", f"/api/worldbooks/{book['id']}")["name"], "重启世界书", "世界书")


# ---------- 生成错误路径 ----------
def _gen_error(result, label):
    ensure(not result.hung and not result.transport_error, f"{label}：{result.summary()}")
    ensure(not result.succeeded, f"{label}：不能假成功：{result.summary()}")
    error = result.error
    ensure(error, f"{label}：应有错误信封：{result.summary()}")
    assert_envelope(error, label)
    return error


@check("core.generate.chat_missing", "会话不存在：流式和非流式都返回结构化的不存在错误")
def _(env):
    for stream in (True, False):
        env.set_stream(stream)
        result = env.generate("no-such-chat", USER_TEXT)
        error = _gen_error(result, f"streamEnabled={stream}")
        ensure(error["code"] in NOT_FOUND, f"code 应表示会话不存在：{error['code']}")
        if not result.is_sse:
            equal(result.status, 404, "HTTP 状态")
    env.set_stream(True)


@check("core.generate.invalid_body", "缺 chatId、userMessage 错类型返回 422")
def _(env):
    assert_rest_error(env.api.post("/api/generate/stream", json={"userMessage": "x"}), 422, ("request_validation_failed",))
    assert_rest_error(env.api.post("/api/generate/stream", json={"chatId": "x", "userMessage": 5}), 422, ("request_validation_failed",))
    assert_rest_error(env.api.post("/api/generate/draft-help", json={"chatId": "x", "mode": "bad"}), 422, ("request_validation_failed",))


@check("core.generate.preset_missing", "会话指向不存在的预设：返回结构化错误，不发上游，不写假回复")
def _(env):
    _openai_preset(env)
    env.set_stream(True)
    chat_id = env.new_chat()
    env.api.json_ok("PUT", f"/api/chats/{chat_id}", json={"overrides": {"presetId": "no-such-preset", "params": {"model": "mock-model"}}})
    result = env.generate(chat_id, USER_TEXT)
    ensure(not env.mock.requests, f"不该发上游：{env.mock.requests}")
    _gen_error(result, "预设不存在")
    messages = env.read_chat(chat_id)["messages"]
    ensure(not any(m["role"] == "assistant" for m in messages), "不该写助手消息")


def _upstream_error(status, stream):
    def run(env):
        preset_id = _openai_preset(env, fault=f"http_{status}")
        env.set_stream(stream)
        chat_id = env.new_chat(preset_id, "mock-model")
        result = env.generate(chat_id, USER_TEXT)
        ensure(env.mock.calls("openai"), f"应到上游：{result.summary()}")
        error = _gen_error(result, f"上游 {status}")
        if status == 401:
            equal(error["code"], "provider_auth_failed", "code")
        if error.get("upstreamStatus") is not None:
            equal(error["upstreamStatus"], status, "upstreamStatus")
        messages = env.read_chat(chat_id)["messages"]
        ensure(any(m["role"] == "user" and m["content"] == USER_TEXT for m in messages), "用户消息不能丢")
        ensure(not any(m["role"] == "assistant" for m in messages), "不该写助手消息")
        env.set_stream(True)
    return run


check("core.generate.upstream_401_stream", "流式上游 401：provider_auth_failed，用户消息保留")(_upstream_error(401, True))
check("core.generate.upstream_429_once", "非流式上游 429：结构化错误，用户消息保留")(_upstream_error(429, False))
check("core.generate.upstream_500_stream", "流式上游 500：结构化错误，用户消息保留")(_upstream_error(500, True))


@check("core.generate.upstream_unreachable", "上游连不上：502 或 SSE 错误，不悬挂")
def _(env):
    preset_id = _openai_preset(env, base=f"http://127.0.0.1:{env.closed_port}/v1")
    env.set_stream(True)
    chat_id = env.new_chat(preset_id, "mock-model")
    result = env.generate(chat_id, USER_TEXT, deadline=45.0)
    error = _gen_error(result, "连不上")
    ensure(error["code"] not in NOT_FOUND, f"错误应来自上游连接，而不是资源不存在：{error['code']}")
    messages = env.read_chat(chat_id)["messages"]
    ensure(any(m["role"] == "user" and m["content"] == USER_TEXT for m in messages), "用户消息不能丢")
    ensure(not any(m["role"] == "assistant" for m in messages), "不该写助手消息")


@check("core.generate.malformed_upstream", "上游 200 但 JSON 畸形（非流式）：不算成功")
def _(env):
    preset_id = _openai_preset(env, fault="malformed_json")
    env.set_stream(False)
    chat_id = env.new_chat(preset_id, "mock-model")
    result = env.generate(chat_id, USER_TEXT, deadline=45.0)
    env.set_stream(True)
    ensure(env.mock.calls("openai"), f"应到上游：{result.summary()}")
    _gen_error(result, "畸形 JSON")
    equal(env.usage_summary(chat_id).get("completedCount"), 0, "completedCount")


@check("core.generate.success_end_to_end", "成功路径：SSE 事件顺序、落盘、账本和 requestId 一致")
def _(env):
    preset_id = _openai_preset(env)
    env.set_stream(True)
    chat_id = env.new_chat(preset_id, "mock-model")
    request_id = f"check-generate-{int(time.time() * 1000)}"
    result = env.generate(chat_id, USER_TEXT, headers={"X-Request-Id": request_id})
    ensure(result.succeeded, result.summary())
    names = [name for name, _data in result.events]
    equal(names[0], "meta", "第一个事件")
    equal(names[-1], "done", "最后一个事件")
    equal(result.meta.get("requestId"), request_id, "meta.requestId")
    last = env.read_chat(chat_id)["messages"][-1]
    equal(last["content"], REPLY, "落盘")
    equal(last["generationMetadata"].get("requestId"), request_id, "generationMetadata.requestId")
    ensure("apiKey" not in json.dumps(last["generationMetadata"]), "generationMetadata 不能有密钥字段")
    events = env.api.json_ok("GET", "/api/usage/events", params={"scope": "chat", "chatId": chat_id})
    equal(events["total"], 1, "账本事件数")
    equal(events["items"][0].get("status"), "completed", "账本 status")
    equal(env.usage_summary(chat_id).get("inputTokens"), USAGE["input"], "账本 inputTokens")


@check("core.generate.merge_new_version", "mergeAssistantIntoMessageId 把输出并入已有消息的新版本，不新增消息")
def _(env):
    preset_id = _openai_preset(env)
    env.set_stream(True)
    chat_id = env.new_chat(preset_id, "mock-model")
    first = env.generate(chat_id, USER_TEXT)
    ensure(first.succeeded, first.summary())
    message_id = first.done["assistantMessageId"]
    count = len(env.read_chat(chat_id)["messages"])
    second = env.generate(chat_id, USER_TEXT, appendUserMessage=False, mergeAssistantIntoMessageId=message_id)
    ensure(second.succeeded, second.summary())
    messages = env.read_chat(chat_id)["messages"]
    equal(len(messages), count, "消息数不变")
    target = [m for m in messages if m["id"] == message_id][0]
    ensure(len(target.get("greetingVariants") or []) == 2, f"应有两个版本：{target.get('greetingVariants')}")


@check("core.generate.anthropic_thinking_budget", "anthropic_messages：默认 max_tokens 加思考档位时，budget_tokens 小于 max_tokens（Anthropic 文档）")
def _(env):
    preset_id = _anthropic_preset(env)
    env.set_stream(True)
    chat_id = env.new_chat(preset_id, "claude-sonnet-4-5-20250929", reasoning="medium")
    result = env.generate(chat_id, USER_TEXT)
    calls = env.mock.calls("anthropic")
    ensure(calls, f"应到上游：{result.summary()}")
    body = calls[0].json
    thinking = body.get("thinking") or {}
    ensure(thinking.get("type") == "enabled", f"这个模型应是预算式思考：{thinking}")
    ensure(thinking["budget_tokens"] < body["max_tokens"], f"budget_tokens={thinking['budget_tokens']} 不小于 max_tokens={body['max_tokens']}，真实 API 按文档应拒绝")


def _anthropic_preset(env, fault="ok", **options):
    env.put_preset({"id": "core-anthropic", "name": "核心 Anthropic", "baseUrl": env.mock.url, "apiKey": env.fixtures["openai_key"], "models": ["claude-sonnet-4-5-20250929"], "protocol": "anthropic_messages", "promptCache": {"mode": "off"}})
    env.mock.reset(fault=fault, **options)
    env.mock.api_key = env.fixtures["openai_key"]
    env.mock.expect_model = None
    return "core-anthropic"


def _empty_output(protocol):
    def run(env):
        preset_id = _openai_preset(env, fault="empty_output") if protocol == "openai" else _anthropic_preset(env, fault="empty_output")
        env.set_stream(False)
        chat_id = env.new_chat(preset_id, "mock-model", reasoning="none")
        result = env.generate(chat_id, USER_TEXT, deadline=45.0)
        env.set_stream(True)
        ensure(env.mock.calls(protocol), f"应到上游：{result.summary()}")
        last = env.read_chat(chat_id)["messages"][-1]
        ensure(not result.succeeded, f"上游 200 但没有任何输出，不能算成功：{result.summary()[:300]}；最后一条消息 role={last['role']}")
        _gen_error(result, "空输出")
    return run


check("core.generate.empty_output_openai", "OpenAI 兼容：上游 200 但响应没有 choices，不能算成功")(_empty_output("openai"))
check("core.generate.empty_output_anthropic", "Anthropic：上游 200 但响应没有 content，不能算成功")(_empty_output("anthropic"))


def _echo_leak(protocol, stream):
    def run(env):
        key = env.fixtures["openai_key"]
        preset_id = _openai_preset(env, fault="http_401")
        env.mock.reset(fault="http_401", echo_secret=True)
        env.mock.api_key = key
        env.set_stream(stream)
        chat_id = env.new_chat(preset_id, "mock-model", reasoning="none")
        env.api.json_ok("DELETE", "/api/http-log")
        result = env.generate(chat_id, USER_TEXT, deadline=45.0)
        env.set_stream(True)
        ensure(env.mock.calls(protocol), f"应到上游：{result.summary()}")
        error = _gen_error(result, "上游 401")
        ensure(key not in result.raw.decode("utf-8", "replace"), f"规格：message 和 detail 里的密钥要打码。错误体含明文 Key：message={str(error.get('message'))[:120]} detail={str(error.get('detail'))[:120]}")
        logs = env.api.get("/api/http-log").text
        ensure(key not in logs, "HTTP 日志列表含明文 Key")
    return run


check("core.secrets.upstream_echo_stream", "上游错误信息回显 Key 时，流式错误和 HTTP 日志列表里要打码（规格：错误信封 message、detail）")(_echo_leak("openai", True))
check("core.secrets.upstream_echo_once", "上游错误信息回显 Key 时，非流式错误和 HTTP 日志列表里要打码")(_echo_leak("openai", False))


# ---------- 账本和日志 ----------
@check("core.usage.chat_missing", "按不存在的会话查用量返回 chat_not_found")
def _(env):
    for path in ("/api/usage/summary", "/api/usage/models", "/api/usage/events"):
        assert_rest_error(env.api.get(path, params={"scope": "chat", "chatId": "no-such-chat"}), 404, ("chat_not_found",), label=path)


@check("core.usage.limit_range", "usage/events 的 limit 超出 1 到 200 返回 422")
def _(env):
    for limit in (0, 201):
        assert_rest_error(env.api.get("/api/usage/events", params={"limit": limit}), 422, label=f"limit={limit}")


@check("core.http_log.missing", "读不存在的 HTTP 日志记录返回 404")
def _(env):
    assert_rest_error(env.api.get("/api/http-log/no-such-record"), 404, NOT_FOUND + ("http_log_not_found", "record_not_found"))


@check("core.no_external_network", "核心检查期间后端没有访问外网模型服务")
def _(env):
    hosts = [h for h in env.mock.proxy_attempts if any(word in h for word in ("amazonaws", "googleapis", "mistral", "anthropic", "openai"))]
    ensure(not hosts, f"访问了外网：{hosts}")
