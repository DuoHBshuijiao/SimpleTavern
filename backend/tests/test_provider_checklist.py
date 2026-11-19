import json
import os
import struct
import tempfile
import unittest
import zlib
from unittest.mock import patch

import httpx

from app.errors import AppError
from app.llm import aws_eventstream, gemini_cache_store
from app.llm.prompt_cache import PromptCachePlan
from app.llm.providers import anthropic_messages, bedrock_converse, mistral_conversations, openai_compatible_chat
from app.llm.providers import gemini_generate_content as gemini, openai_responses as responses
from app.llm.providers.openai_compatible_chat import ChatCompletionMessage, StreamChunk
from app.llm.types import ANTHROPIC_MESSAGES_PROTOCOL, GEMINI_GENERATE_CONTENT_PROTOCOL, OPENAI_RESPONSES_PROTOCOL, GenerationConfig
from app.routes.assistant import _assistant_messages_to_openai
from app.routes import web_search as web_search_routes
from app.schemas import ApiPreset, ChatMessage, Settings
from app.services.native_web import WebPlan, resolve_web_plan
from app.services import generate_web_search_runtime
from app.services import tts_platform
from app.tokenizer_service import trim_assistant_openai_messages_to_context


def sse(events):
    return "".join("data: " + json.dumps(event) + "\n\n" for event in events)


class ProviderChecklistTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.dict(os.environ, {"SIMPLETAVERN_DATA_DIR": directory.name}))

    async def mock_provider(self, provider, response):
        requests = []
        def handler(request):
            requests.append(json.loads(request.content))
            return response
        client = await self.enterAsyncContext(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        self.enterContext(patch.object(provider, "get_async_http_client", return_value=client))
        return requests

    async def test_openai_compatible_empty_choices_accepts_prompt_metadata_and_valid_usage(self):
        annotation = {"prompt_index": 0, "content_filter_results": {"hate": {"filtered": False, "severity": "safe"}}}
        metadata = [
            {"id": "", "object": "", "created": 0, "model": "", "choices": [], key: [annotation], "usage": None}
            for key in ("prompt_filter_results", "prompt_annotations")
        ]
        usage = {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}
        content = {"choices": [{"index": 0, "delta": {"content": "Fixture answer"}, "finish_reason": None}]}
        stream_kwargs = {"base_url": "https://example.org/v1", "api_key": "mock", "model": "fixture",
                         "messages": [{"role": "user", "content": "Fixture prompt"}]}
        for usage_frame in ({"choices": [], "usage": usage}, {"usage": usage}):
            wire = sse([*metadata, content, usage_frame]) + "data: [DONE]\n\n"
            await self.mock_provider(openai_compatible_chat, httpx.Response(200, text=wire))
            chunks = [chunk async for chunk in openai_compatible_chat.stream_chat_completions(**stream_kwargs)]
            self.assertEqual(chunks[-1].kind, "finish")
            self.assertTrue(all(chunk.kind == "content" for chunk in chunks[:-1]))
            self.assertEqual("".join(chunk.text for chunk in chunks[:-1]), "Fixture answer")
            self.assertEqual(chunks[-1].usage, openai_compatible_chat.usage_public(usage))

        bad_frames = [
            sse([{"choices": []}]),
            sse([{"choices": [], "prompt_filter_results": "bad"}]),
            sse([{"choices": [], "prompt_annotations": ["bad"]}]),
            sse([{"choices": [], "usage": "bad"}]),
            sse([{"choices": None, "usage": usage}]),
            sse([{"choices": ["bad"]}]),
            "data: {not-json}\n\n",
        ]
        for bad_frame, expected_error in [(frame, "stream_event_invalid") for frame in bad_frames] + [("", "stream_interrupted")]:
            with self.subTest(expected_error=expected_error, bad_frame=bad_frame):
                await self.mock_provider(openai_compatible_chat, httpx.Response(200, text=sse([*metadata, content]) + bad_frame))
                chunks = []
                with self.assertRaises(AppError) as error:
                    async for chunk in openai_compatible_chat.stream_chat_completions(**stream_kwargs):
                        chunks.append(chunk)
                self.assertEqual(error.exception.code, expected_error)
                self.assertTrue(all(chunk.kind == "content" for chunk in chunks))
                self.assertEqual("".join(chunk.text for chunk in chunks), "Fixture answer")

        await self.mock_provider(openai_compatible_chat, httpx.Response(200, text=sse(metadata) + "data: [DONE]\n\n"))
        with self.assertRaises(AppError) as error:
            _ = [chunk async for chunk in openai_compatible_chat.stream_chat_completions(**stream_kwargs)]
        self.assertEqual(error.exception.code, "provider_response_invalid")

    def test_anthropic_ga_web_fetch_respects_preset_toggle_and_needs_no_beta_header(self):
        preset = ApiPreset(name="fixture", baseUrl="https://api.anthropic.com", webSearchFetchEnabled=True)
        settings = Settings(apiPresets=[preset])
        for enabled in (True, False):
            preset.webSearchFetchEnabled = enabled
            plan = resolve_web_plan(settings, requested=True, protocol=ANTHROPIC_MESSAGES_PROTOCOL,
                                    base_url=preset.baseUrl, preset_id=preset.id)
            wire = anthropic_messages.AnthropicMessagesAdapter().build_request(
                base_url=preset.baseUrl, api_key="mock", messages=[{"role":"user","content":"fixture"}],
                config=GenerationConfig(model="claude-fixture", tools=plan.tools),
            )
            self.assertEqual(any(tool["type"] == "web_fetch_20250910" for tool in wire.json_body["tools"]), enabled)
            self.assertNotIn("anthropic-beta", {key.lower() for key in wire.headers})

    async def test_cloud_tts_uses_provider_url_and_reports_rejected_audio(self):
        urls = []
        def minimax_error(request):
            urls.append(str(request.url))
            return httpx.Response(200, json={"base_resp":{"status_code":1004,"status_msg":"Synthetic service refusal"}})
        for base_url in ("https://api.minimaxi.com", "https://api.minimaxi.com/v1/t2a_v2"):
            platform = tts_platform.MiniMaxTtsPlatform("mock", base_url)
            await platform._client.aclose()
            platform._client = await self.enterAsyncContext(httpx.AsyncClient(
                base_url=platform._base_url, transport=httpx.MockTransport(minimax_error),
            ))
            with self.assertRaises(Exception) as error:
                await platform.synthesize(tts_platform.SynthesisRequest(text="短句", voice_id="fixture"))
            self.assertIn("Synthetic service refusal", str(error.exception))
        self.assertEqual(urls, ["https://api.minimaxi.com/v1/t2a_v2"] * 2)

        platform = tts_platform.GlmTtsPlatform("mock")
        await platform._client.aclose()
        def glm_error(request):
            urls.append(str(request.url))
            return httpx.Response(200, json={"error":{"message":"Synthetic JSON error"}})
        platform._client = await self.enterAsyncContext(httpx.AsyncClient(
            base_url=platform._base_url, transport=httpx.MockTransport(glm_error),
        ))
        with self.assertRaises(ValueError):
            await platform.synthesize(tts_platform.SynthesisRequest(text="长" * 1025, voice_id="fixture"))
        self.assertEqual(len(urls), 2)
        with self.assertRaises(Exception) as error:
            await platform.synthesize(tts_platform.SynthesisRequest(text="短句", voice_id="fixture"))
        self.assertIn("Synthetic JSON error", str(error.exception))
        self.assertIn("open.bigmodel.cn", urls[-1])

    def test_system_turns_preserve_relative_order_for_all_adapters(self):
        messages = [
            {"role":"system","content":"STATIC-FIXTURE"},
            {"role":"system","content":"DYNAMIC-START","_system_turn":True},
            {"role":"assistant","content":"REPLY-ONE"},
            {"role":"system","content":"DEPTH-INJECTION","_system_turn":True},
            {"role":"assistant","content":"REPLY-TWO"},
        ]
        for convert in (anthropic_messages._convert_messages, gemini._convert_messages,
                        responses._convert_input, bedrock_converse._convert_messages, mistral_conversations._convert_messages):
            with self.subTest(adapter=convert.__module__):
                leading, turns = convert(messages)
                self.assertIn("STATIC-FIXTURE", json.dumps(leading))
                self.assertNotIn("DYNAMIC-START", json.dumps(leading))
                ordered = json.dumps(turns)
                offsets = [ordered.index(text) for text in ("DYNAMIC-START", "REPLY-ONE", "DEPTH-INJECTION", "REPLY-TWO")]
                self.assertEqual(offsets, sorted(offsets))
                self.assertNotIn("prefix", turns[-1])

    async def test_gemini_stable_prefix_reuses_cache_and_separates_accounts(self):
        plan = PromptCachePlan(protocol="gemini_generate_content",mode="explicit",ttl=3600)
        def payload(text):
            return gemini._payload_from_config(messages=[
                {"role":"system","content":"Static fixture"},
                {"role":"system","content":text,"_system_turn":True},
            ], config=GenerationConfig(model="gemini-fixture"))
        cached = ["cachedContents/first", "cachedContents/second"]
        with patch.object(gemini_cache_store, "create_cached_content", side_effect=cached) as create:
            opts = {"plan":plan,"model":"gemini-fixture","api_root":"https://generativelanguage.googleapis.com/v1beta"}
            first = await gemini_cache_store.attach_explicit_cache(payload("first turn"), api_key="account-a", **opts)
            second = await gemini_cache_store.attach_explicit_cache(payload("second turn"), api_key="account-a", **opts)
            foreign = await gemini_cache_store.attach_explicit_cache(payload("second turn"), api_key="account-b", **opts)
        self.assertEqual(first["cachedContent"], second["cachedContent"])
        self.assertNotEqual(second["cachedContent"], foreign["cachedContent"])
        self.assertEqual(create.await_count,2)
        self.assertIn("second turn", json.dumps(second["contents"]))

    async def test_anthropic_signed_thinking_is_replayed_in_independent_search_tools(self):
        tool_use = {"type":"tool_use","id":"t1","name":"web_search","input":{"query":"fixture"}}
        signature = {"type":"thinking","thinking":"private fixture","signature":"opaque-upstream-signature"}
        call = {"id":"t1","type":"function","function":{"name":"web_search","arguments":'{"query":"fixture"}'}}
        plans = WebPlan("independent", [{"type":"function","function":{"name":"web_search","parameters":{}}}])
        opts = dict(messages=[{"role":"user","content":"fixture"}],base_url="https://api.anthropic.com",
            api_key="mock",model="claude-fixture",temperature=None,top_p=None,max_tokens=None,extra_body={},
            settings=Settings(),web_search_enabled=True,protocol=ANTHROPIC_MESSAGES_PROTOCOL,web_plan=plans)
        requests = []
        def record(params):
            _, turns = anthropic_messages._convert_messages(params["messages"])
            requests.append(turns)

        async def streamed(**params):
            record(params)
            first = len(requests) == 1
            if first:
                yield StreamChunk(kind="reasoning",text="private fixture")
            else:
                yield StreamChunk(kind="content",text="after tools")
            yield StreamChunk(kind="finish",tool_calls=[call] if first else None,
                              provider_content=[signature, tool_use] if first else None)

        async def completed(**params):
            record(params)
            first = len(requests) == 1
            return ChatCompletionMessage(role="assistant",content="" if first else "after tools",
                reasoning_content="private fixture" if first else None,tool_calls=[call] if first else None,
                provider_content=[signature,tool_use] if first else None)

        with patch.object(generate_web_search_runtime, "execute_web_tool", return_value={"ok":True}):
            with patch.object(generate_web_search_runtime,"stream_chat_completions",streamed):
                events = [event async for event in generate_web_search_runtime.iter_web_search_stream_events(**opts)]
                self.assertEqual(events[-1]["content_saved"], "after tools")
                self.assertIn(signature, requests[1][1]["content"])
            requests.clear()
            with patch.object(generate_web_search_runtime,"chat_completions_message",completed):
                result = await generate_web_search_runtime.nonstream_web_search_rounds(**opts)
                self.assertEqual(result[0], "after tools")
                self.assertIn(signature, requests[1][1]["content"])

    def test_gemini_roundtrip_preserves_wire_id_and_signature(self):
        data = {"candidates": [{"content": {"parts": [{
            "functionCall": {"id": "native-123", "name": "web_search", "args": {"query": "fixture"}},
            "thoughtSignature": "test-signature",
        }]}}]}
        _, _, calls = gemini._extract_text_thoughts_and_tool_calls(data)
        messages = [
            ChatMessage(role="assistant", content="", tool_calls=calls),
            ChatMessage(role="tool", content='{"ok":true}', tool_call_id="native-123"),
        ]
        history = _assistant_messages_to_openai([ChatMessage.model_validate_json(m.model_dump_json()) for m in messages])
        _, items = gemini._convert_messages(history)
        call = items[0]["parts"][0]
        self.assertEqual(call["thoughtSignature"], "test-signature")
        self.assertEqual(call["functionCall"]["id"], "native-123")
        self.assertEqual(items[1]["parts"][0]["functionResponse"]["id"], "native-123")

    async def test_gemini_independent_search_continues_after_tool_result(self):
        protocol = GEMINI_GENERATE_CONTENT_PROTOCOL
        base_url = "https://generativelanguage.googleapis.com/v1beta"
        settings = Settings(webSearch={"tavily": {"apiKey": "fixture-search-key"}})
        plan = resolve_web_plan(settings, requested=True, protocol=protocol,
                                base_url=base_url, gemini_search="independent")
        self.assertTrue(plan.local)
        calls = []

        def respond(request):
            payload = json.loads(request.content)
            calls.append(payload)
            if len(calls) == 1:
                parts = [{"thoughtSignature": "fixture-signature", "functionCall": {
                    "id": "fixture-search", "name": "web_search", "args": {"query": "sample query"},
                }}]
            else:
                parts = [{"text": "Answer after search"}]
            return httpx.Response(200, json={"candidates": [{
                "content": {"parts": parts}, "finishReason": "STOP",
            }]})

        client = await self.enterAsyncContext(httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        with patch.object(gemini, "get_async_http_client", return_value=client):
            with patch.object(generate_web_search_runtime, "execute_web_tool",
                              return_value={"ok": True, "result": "fixture tool result"}) as search:
                result = await generate_web_search_runtime.nonstream_web_search_rounds(
                    messages=[{"role": "user", "content": "fixture"}], base_url=base_url, api_key="fixture",
                    model="gemini-fixture", temperature=None, top_p=None, max_tokens=None, extra_body={},
                    settings=settings, web_search_enabled=True, protocol=protocol, web_plan=plan,
                )
        self.assertEqual(result[0], "Answer after search")
        self.assertEqual(search.await_args.kwargs["args"], {"query": "sample query"})
        self.assertEqual(len(calls), 2)
        self.assertIn("web_search", json.dumps(calls[0]["tools"][0]["functionDeclarations"]))
        self.assertIn("fixture-signature", json.dumps(calls[1]["contents"]))
        second_round_parts = calls[1]["contents"][-1]["parts"]
        response = second_round_parts[0]["functionResponse"]
        self.assertEqual(response["id"], "fixture-search")
        self.assertIn("fixture tool result", json.dumps(response["response"]))

    async def test_quota_response_preserves_successful_services_when_one_times_out(self):
        settings = Settings(webSearch={
            "tavily": {"apiKey": "fixture-tavily"}, "bocha": {"apiKey": "fixture-bocha"},
        })
        good = {"ok": True, "data": {"remaining": 42}}
        with patch.object(web_search_routes, "load_settings", return_value=settings):
            for failing, succeeding in (("tavily", "bocha"), ("bocha", "tavily")):
                fetchers = {"tavily": "fetch_tavily_usage", "bocha": "fetch_bocha_remaining"}
                with patch.object(web_search_routes, fetchers[failing], side_effect=httpx.ReadTimeout("fixture")):
                    with patch.object(web_search_routes, fetchers[succeeding], return_value=good):
                        response = await web_search_routes.web_search_status()
                payload = json.loads(response.body)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(payload[succeeding], good)
                self.assertEqual(payload[failing]["ok"], False)
                self.assertIn(failing, payload[failing]["message"])

    async def test_gemini_stream_keeps_tool_fragments_reasoning_whitespace_and_sources(self):
        def candidate(*parts, **fields):
            return {"candidates": [{"content": {"parts": parts}, **fields}]}
        events = [
            candidate({"text":"a ", "thought":True}),
            candidate({"text":"b\n", "thought":True}),
            candidate({"thoughtSignature":"opaque", "functionCall":{"id":"native-1", "name":"web_search", "willContinue":True}}),
            candidate({"functionCall":{"id":"native-1", "partialArgs":[{"jsonPath":"$.query", "stringValue":"alpha ", "willContinue":True}], "willContinue":True}}),
            candidate({"functionCall":{"id":"native-1", "partialArgs":[{"jsonPath":"$.query", "stringValue":"beta"}], "willContinue":True}}),
            candidate({"functionCall":{"id":"native-1", "partialArgs":[{"jsonPath":"$.filters[0].active", "boolValue":True}]}}),
            candidate({"functionCall":{"name":"same", "args":{"number":1}}}),
            candidate({"functionCall":{"name":"same", "args":{"number":2}}}),
            candidate({"text":"answer"}, finishReason="STOP", groundingMetadata={"groundingChunks":[
                {"web":{"uri":"https://example.org/source","title":"Fixture source"}},
            ]}),
        ]
        recorded = await self.mock_provider(gemini, httpx.Response(200, text=sse(events)))
        config = GenerationConfig(model="gemini-fixture", stream=True, extra_body={"toolConfig": {
            "functionCallingConfig": {"streamFunctionCallArguments": True},
        }})
        chunks = [chunk async for chunk in gemini.stream_gemini(
            base_url="https://generativelanguage.googleapis.com/v1beta",
            api_key="mock", messages=[{"role":"user", "content":"hello"}], config=config,
        )]
        self.assertTrue(recorded[0]["toolConfig"]["functionCallingConfig"]["streamFunctionCallArguments"])
        self.assertEqual("".join(chunk.text for chunk in chunks if chunk.kind == "reasoning"), "a b\n")
        self.assertIn("https://example.org/source", "".join(chunk.text for chunk in chunks if chunk.kind == "content"))
        calls = chunks[-1].tool_calls
        self.assertEqual(len({call["id"] for call in calls}), 3)
        self.assertEqual(calls[0]["_gemini_thought_signature"], "opaque")
        self.assertEqual(json.loads(calls[0]["function"]["arguments"]), {"query":"alpha beta","filters":[{"active":True}]})
        same_name_calls = calls[1:]
        tool_round = [
            {"role": "assistant", "content": "", "tool_calls": same_name_calls},
            *({"role": "tool", "tool_call_id": call["id"], "content": "{}"} for call in same_name_calls),
        ]
        latest = {"role": "user", "content": "Latest request"}
        with patch("app.tokenizer_service.count_tokens", return_value=0):
            with patch("app.tokenizer_service.count_tokens_for_messages", side_effect=len):
                retained = trim_assistant_openai_messages_to_context([*tool_round, latest], 4)
                dropped = trim_assistant_openai_messages_to_context([*tool_round, latest], 3)
        self.assertEqual(retained, [*tool_round, latest])
        self.assertFalse(any(msg.get("tool_calls") or msg["role"] == "tool" for msg in dropped))

    async def test_gemini_missing_terminal_is_an_error(self):
        await self.mock_provider(gemini, httpx.Response(200, text=sse([
            {"candidates":[{"content":{"parts":[{"text":"partial"}]}}]},
        ])))
        stream = gemini.stream_gemini(
            base_url="https://generativelanguage.googleapis.com/v1beta", api_key="mock",
            messages=[{"role":"user","content":"fixture"}], config=GenerationConfig(model="gemini-fixture",stream=True),
        )
        parts = []
        with self.assertRaises(AppError) as error:
            async for chunk in stream:
                if chunk.kind == "content":
                    parts.append(chunk.text)
        self.assertEqual("".join(parts), "partial")
        self.assertEqual(error.exception.code, "stream_incomplete")

    def test_gemini_rejects_requested_image_output_before_provider(self):
        with self.assertRaises(AppError) as error:
            gemini._payload_from_config(messages=[{"role":"user","content":"image"}], config=GenerationConfig(
                model="gemini-fixture", extra_body={"generationConfig":{"responseModalities":["TEXT","IMAGE"]}},
            ))
        self.assertEqual(error.exception.status_code, 422)
        self.assertIn("图片", error.exception.message)

    async def test_responses_refusal_is_body_and_encrypted_reasoning_replays(self):
        opaque = {"type":"reasoning", "id":"rs_fixture", "summary":[], "encrypted_content":"opaque-fixture"}
        output = [opaque, {"type":"message","id":"msg_fixture","content":[{"type":"refusal","refusal":"Fixture refusal"}]}]
        recorded = await self.mock_provider(responses, httpx.Response(200, json={"output":output, "status":"completed"}))
        config = GenerationConfig(model="gpt-fixture", extra_body={"reasoning":{"effort":"medium"}})
        result = await responses.complete_responses(
            base_url="https://api.openai.com/v1", api_key="mock", config=config, as_message=True,
            messages=[{"role":"user","content":[{"type":"text","text":"hello"},{"type":"image_url","image_url":{"url":"data:image/png;base64,AAAA"}}]}],
        )
        self.assertEqual(result.content, "Fixture refusal")
        self.assertEqual(result.provider_content, [opaque])
        self.assertIn("reasoning.encrypted_content", recorded[0]["include"])
        self.assertEqual(recorded[0]["input"][0]["content"][1]["type"], "input_image")
        history = _assistant_messages_to_openai([ChatMessage.model_validate_json(ChatMessage(
            role="assistant", content=result.content, responsesReasoning=result.provider_content,
        ).model_dump_json())])
        self.assertEqual(responses._convert_input(history)[1][0], opaque)

    async def test_native_web_footers_keep_all_search_links_with_and_without_citations(self):
        urls = [f"https://example.org/search/{index}" for index in range(25)]
        citation = {"url": urls[0], "title": "Cited result"}
        answer = "Fixture answer."
        messages = [{"role": "user", "content": "Search fixture"}]
        search_results = {
            "type": "web_search_call", "id": "ws_fixture", "status": "completed",
            "action": {"type": "search", "query": "fixture", "sources": [
                {"type": "url", "url": url} for url in urls
            ]},
        }
        output_message = {
            "type": "message", "id": "msg_fixture", "content": [{
                "type": "output_text", "text": answer, "annotations": [
                    {"type": "url_citation", "start_index": 0, "end_index": len(answer), **citation},
                ],
            }],
        }
        tool_use = {
            "type": "server_tool_use", "id": "srvtoolu_fixture", "name": "web_search", "input": {"query": "fixture"},
        }
        result_block = {
            "type": "web_search_tool_result", "tool_use_id": "srvtoolu_fixture", "content": [
                {"type": "web_search_result", "url": url, "title": f"Result {index}", "encrypted_content": "fixture"}
                for index, url in enumerate(urls)
            ],
        }
        web_citation = {"type": "web_search_result_location", "cited_text": "Fixture", "encrypted_index": "fixture", **citation}
        text_block = {"type": "text", "text": answer, "citations": [web_citation]}
        anthropic_events = [
            {"type": "message_start", "message": {"id": "msg_fixture", "usage": {"input_tokens": 1}}},
            {"type": "content_block_start", "index": 0, "content_block": tool_use},
            {"type": "content_block_stop", "index": 0},
            {"type": "content_block_start", "index": 1, "content_block": result_block},
            {"type": "content_block_stop", "index": 1},
            {"type": "content_block_start", "index": 2, "content_block": {"type": "text", "text": "", "citations": []}},
            {"type": "content_block_delta", "index": 2, "delta": {"type": "text_delta", "text": answer}},
            {"type": "content_block_delta", "index": 2, "delta": {"type": "citations_delta", "citation": web_citation}},
            {"type": "content_block_stop", "index": 2},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 1}},
            {"type": "message_stop"},
        ]
        responses_events = [
            {"type": "response.output_item.done", "output_index": 0, "item": search_results},
            {"type": "response.output_text.delta", "delta": answer},
            {"type": "response.completed", "response": {"output": [
                {"type": "web_search_call", "id": "ws_fixture", "status": "completed"}, output_message,
            ]}},
        ]

        for adapter, complete, stream, base_url, model, tool, output, events in (
            (responses, responses.complete_responses, responses.stream_responses, "https://api.openai.com/v1", "gpt-fixture",
             {"type": "web_search"}, {"status": "completed", "output": [search_results, output_message]}, responses_events),
            (anthropic_messages, anthropic_messages.complete_anthropic, anthropic_messages.stream_anthropic,
             "https://api.anthropic.com", "claude-fixture", {"type": "web_search_20250305", "name": "web_search"},
             {"stop_reason": "end_turn", "content": [tool_use, result_block, text_block]}, anthropic_events),
        ):
            for streaming in (False, True):
                with self.subTest(adapter=adapter.__name__, streaming=streaming):
                    response = httpx.Response(200, text=sse(events)) if streaming else httpx.Response(200, json=output)
                    requests = await self.mock_provider(adapter, response)
                    extra = {"include": ["message.output_text.logprobs"]} if adapter is responses else None
                    kwargs = {"base_url": base_url, "api_key": "mock", "messages": messages,
                              "config": GenerationConfig(model=model, stream=streaming, tools=[tool], extra_body=extra)}
                    if streaming:
                        chunks = [chunk async for chunk in stream(**kwargs)]
                        self.assertEqual(chunks[-1].kind, "finish")
                        text = "".join(chunk.text for chunk in chunks if chunk.kind == "content")
                    else:
                        text = (await complete(**kwargs)).text
                    self.assertTrue(text.startswith(answer + "\n\n来源："))
                    self.assertIn(f"[Cited result](<{urls[0]}>)", text)
                    for url in urls:
                        self.assertEqual(text.count(f"(<{url}>)"), 1, url)
                    if adapter is responses:
                        self.assertEqual(requests[0]["include"], [
                            "message.output_text.logprobs", "reasoning.encrypted_content", "web_search_call.action.sources",
                        ])

    async def test_responses_stream_emits_refusal_once_and_retains_partial_text_at_limit(self):
        events = [
            {"type":"response.refusal.delta","delta":"Fixture "},
            {"type":"response.refusal.delta","delta":"refusal"},
            {"type":"response.refusal.done","refusal":"Fixture refusal"},
            {"type":"response.incomplete","response":{"incomplete_details":{"reason":"max_output_tokens"}, "output":[]}},
        ]
        await self.mock_provider(responses, httpx.Response(200, text=sse(events)))
        chunks = [chunk async for chunk in responses.stream_responses(
            base_url="https://api.openai.com/v1", api_key="mock",
            messages=[{"role":"user","content":"fixture"}], config=GenerationConfig(model="gpt-fixture",stream=True),
        )]
        self.assertEqual("".join(chunk.text for chunk in chunks if chunk.kind == "content"), "Fixture refusal")
        self.assertEqual(chunks[-1].usage["finishReason"], "length")

    async def test_responses_replays_encrypted_reasoning_in_tool_followups(self):
        plan = WebPlan("independent", [{"type": "function", "function": {"name": "web_search", "parameters": {}}}])
        recorded = []
        reasoning_items = [
            {"type": "reasoning", "id": f"rs_offline{seq}", "summary": [], "encrypted_content": f"mock-encrypted-{seq}"}
            for seq in (1, 2)
        ]

        def handle(request):
            recorded.append(json.loads(request.content))
            seq = len(recorded)
            if seq <= 2:
                output = [reasoning_items[seq - 1], {
                    "type": "function_call", "id": f"fc_offline{seq}", "call_id": f"call_offline{seq}",
                    "name": "web_search", "arguments": json.dumps({"query": f"fixture {seq}"}),
                }]
            else:
                output = [{"type": "message", "content": [{"type": "output_text", "text": "Fixture done"}]}]
            return httpx.Response(200, json={"output": output, "status": "completed"})

        client = await self.enterAsyncContext(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        with patch.object(responses, "get_async_http_client", return_value=client):
            with patch.object(generate_web_search_runtime, "execute_web_tool", return_value={"ok": True}):
                result = await generate_web_search_runtime.nonstream_web_search_rounds(
                    messages=[{"role": "user", "content": "fixture"}], base_url="https://api.openai.com/v1", api_key="fixture",
                    model="gpt-fixture", temperature=None, top_p=None, max_tokens=None, extra_body={},
                    settings=Settings(), web_search_enabled=True, protocol=OPENAI_RESPONSES_PROTOCOL, web_plan=plan,
                )
        self.assertEqual(result[0], "Fixture done")
        self.assertEqual(len(recorded), 3)
        for seq, payload in enumerate(recorded[1:], start=1):
            self.assertIn(reasoning_items[seq - 1], payload["input"])
            self.assertTrue(any(item.get("type") == "function_call_output" and item.get("call_id") == f"call_offline{seq}"
                                for item in payload["input"]))

    async def test_aws_yields_good_frame_before_bad_crc_in_same_read(self):
        def frame(payload, offset=0):
            prelude = struct.pack(">II", 16 + len(payload), 0)
            raw = prelude + struct.pack(">I", zlib.crc32(prelude)) + payload
            return raw + struct.pack(">I", zlib.crc32(raw) ^ offset)

        response = httpx.Response(200, content=frame(b"prefix") + frame(b"terminal", 1))
        frames = aws_eventstream.aiter_event_frames(response, source="fixture", provider="bedrock", protocol="fixture")
        self.assertEqual((await anext(frames)).payload, b"prefix")
        with self.assertRaises(AppError) as error:
            await anext(frames)
        self.assertEqual(error.exception.code, "stream_event_invalid")
