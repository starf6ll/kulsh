import unittest
import tempfile
import json
import os
import time
from pathlib import Path
from collections import deque
from unittest.mock import AsyncMock, patch

from src import ai, util


class OutputTests(unittest.TestCase):
    def test_inline_timestamp_is_a_whole_separator(self):
        parts, _ = util.process_ai_response("первое [20:39 (только что)] второе")
        self.assertEqual(parts, ["первое", "второе"])

    def test_time_is_removed_without_splitting(self):
        parts, _ = util.process_ai_response("первое [20:39 (только что)] второе", False)
        self.assertEqual(parts, ["первое второе"])

    def test_code_and_ordinary_time_survive(self):
        self.assertIn("[20:39]", util.strip_time_prefixes("```\n[20:39]\n```"))
        self.assertEqual(util.strip_time_prefixes("встреча в 20:39"), "встреча в 20:39")

    def test_history_preserves_timestamps(self):
        messages = util.memory_to_messages(deque([{"type": "bot", "text": "привет", "time": "20:39"}]))
        self.assertEqual(messages[0]["text"], "[20:39] привет")

    def test_usage_tokens_ignore_cached_input(self):
        usage = {"prompt_tokens": 10000, "completion_tokens": 200,
                 "prompt_tokens_details": {"cached_tokens": 8000}}
        self.assertEqual(ai._usage_tokens(usage, "x"), 2200)

    def test_private_config_hides_random_setting(self):
        from src import ui
        random_label = util.tr("ru", "cfg_random")
        self.assertNotIn(random_label, ui.config_text("tg", 42, 42))
        self.assertIn(random_label, ui.config_text("tg", -100, 42))

    def test_system_role_is_not_embedded_in_user_content(self):
        messages = ai._to_openai_messages([{"role": "user", "parts": [{"text": "hi"}]}], "rules", True)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_easy_uses_luna_first(self):
        with patch.object(ai, "_jev_complexity", AsyncMock(return_value="easy")):
            result = await ai._pick_auto_models(False, "привет", False, "tg", 1, "default")
        self.assertEqual(result[0], "gpt-6-luna")
        self.assertFalse(any(ai.is_paid_model(m) for m in result))

    async def test_sol_is_never_in_free_pool(self):
        with patch.object(ai, "_jev_complexity", AsyncMock(return_value="easy")):
            result = await ai._pick_auto_models(False, "привет", False, "tg", 1, "default")
        self.assertNotIn("gpt-6.1-sol", result)

    async def test_hard_vision_and_paid_constraints(self):
        with patch.object(ai, "_jev_complexity", AsyncMock(return_value="hard")):
            result = await ai._pick_auto_models(True, "сложная задача", False, "tg", 1, "default")
        self.assertNotIn("deepseek-v4-pro", result)
        self.assertFalse(any(ai.is_paid_model(m) for m in result))

    async def test_observer_prompt_is_user_message_and_skips_summary(self):
        key = "tg_-100"
        ai.long_term_memory[key] = {
            "facts": ["Фолз любит чай " + "x" * 200],
            "events": [{"date": "12.11", "text": "тест"}],
            "summary": "СТАРОЕ РЕЗЮМЕ",
        }
        captured = []

        async def fake_chat(provider, url, api_key, model_name, messages, temp, on_delta=None):
            captured.extend(messages)
            return "тихо тут", None

        try:
            with patch.object(ai, "_pick_auto_models", AsyncMock(return_value=["deepseek-v4.1-flash"])), \
                    patch.object(ai, "_ask_openai_chat", fake_chat):
                out = await ai.ask_ai_async(
                    prompt="Посмотри на историю чата.",
                    context_type="observer",
                    messages=[{"role": "user", "text": "привет"}],
                    chat_id=-100, user_id=0,
                )
            self.assertEqual(out, "тихо тут")
        finally:
            ai.long_term_memory.pop(key, None)
        system = captured[0]["content"]
        self.assertNotIn("СТАРОЕ РЕЗЮМЕ", system)  # автономный пост не тянет сводку
        self.assertTrue(system.rstrip().endswith("с текста."))
        self.assertEqual(captured[-1]["role"], "user")
        self.assertIn("Ты молча наблюдаешь за чатом", captured[-1]["content"])

    async def test_summary_incremental_and_no_repeat_call(self):
        key = "test_summary"
        ai.long_term_memory.pop(key, None)
        older = [{"role": "user", "text": "hello"}]
        try:
            with patch.object(ai, "_ask_openai_chat", AsyncMock(return_value=("summary", None))) as call, \
                    patch.object(ai, "save_long_term_memory"):
                self.assertEqual(await ai._compact_history(key, older), "summary")
                self.assertEqual(await ai._compact_history(key, older), "summary")
                self.assertEqual(call.await_count, 1)
        finally:
            ai.long_term_memory.pop(key, None)


class SecretTests(unittest.TestCase):
    def test_update_env_merges_only_keys_without_echo(self):
        from src import admin_panel
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(util, "BASE_DIR", directory), \
                patch.dict("os.environ", {}, clear=False):
            Path(directory, ".env").write_text("OTHER=keep\n", encoding="utf-8")
            admin_panel._update_env_secrets("EXAMPLE_API_KEY=abc123\nOTHER=overwrite\n")
            content = Path(directory, ".env").read_text(encoding="utf-8")
            self.assertIn("OTHER=keep", content)
            self.assertIn("EXAMPLE_API_KEY='abc123'", content)


class AgentTests(unittest.IsolatedAsyncioTestCase):
    def test_agent_markers_are_extracted(self):
        cleaned, markers, _ = util.extract_utility_markers(
            "ок !tell петя :: привет, это от пети\n!notify_owner странное сообщение\n!refuse спам"
        )
        self.assertIn("tell:петя\x1fпривет, это от пети", markers)
        self.assertIn("notify_owner:странное сообщение", markers)
        self.assertIn("refuse:спам", markers)
        self.assertEqual(cleaned, "ок")

    def test_tell_keeps_platform_prefix_target(self):
        cleaned, markers, _ = util.extract_utility_markers("!tell tg:-100123 :: привет")
        self.assertEqual(markers, ["tell:tg:-100123\x1fпривет"])
        self.assertEqual(cleaned, "")

    def test_tell_empty_payload_does_not_become_colon(self):
        cleaned, markers, _ = util.extract_utility_markers("!tell tg:-100 ::")
        self.assertEqual(markers, ["tell:tg:-100\x1f"])
        self.assertEqual(cleaned, "")

    def test_tell_absorbs_image_block_from_next_line(self):
        cleaned, markers, _ = util.extract_utility_markers(
            '!tell Кенты :: вот\n!image\n```json\n{"width":100}\n```\nготово'
        )
        self.assertEqual(cleaned, "готово")
        self.assertEqual(len(markers), 1)
        self.assertTrue(markers[0].startswith("tell:Кенты\x1fвот !image"))
        self.assertIn('"width":100', markers[0])

    def test_agent_actions_are_removed_before_image_processing(self):
        cleaned, actions = util.extract_agent_actions(
            'ща\n!tell Кенты :: !image\n```json\n{"prompt":"мопс"}\n```'
        )
        self.assertEqual(cleaned, "ща")
        self.assertEqual(len(actions), 1)
        self.assertTrue(actions[0].startswith("tell:Кенты\x1f!image"))
        self.assertIn('"prompt":"мопс"', actions[0])

    def test_duplicate_tells_are_not_deduped(self):
        markers = ["tell:Кенты\x1fпривет", "tell:Кенты\x1fпривет", "sticker", "sticker"]
        self.assertEqual(
            util.dedupe_markers(markers),
            ["tell:Кенты\x1fпривет", "tell:Кенты\x1fпривет", "sticker"],
        )

    def test_memory_fact_is_trimmed(self):
        long_fact = "Петя: " + "а" * 1000
        cleaned = ai._clean_memory_fact(long_fact)
        self.assertLessEqual(len(cleaned), ai.MEMORY_FACT_MAX_CHARS)
        self.assertTrue(cleaned.startswith("Петя:"))

    def test_reply_target(self):
        self.assertEqual(util.take_reply_target("!reply:123 привет"), ("привет", 123))
        self.assertEqual(util.take_reply_target("привет"), ("привет", None))

    def test_reply_markers_survive_response_processing(self):
        segments, _ = util.process_ai_response(
            "!reply:123 привет!separate!reply:456 пока", separate_enabled=True
        )
        self.assertEqual([util.take_reply_target(seg) for seg in segments],
                         [("привет", 123), ("пока", 456)])

    async def test_cross_chat_to_user_needs_no_source_permission(self):
        from src import agent
        old_groups, old_contacts, old_text = agent._groups, agent._contacts, agent._send_text
        try:
            agent._groups = {}
            agent._contacts = {"tg:1": {"platform": "tg", "id": 1, "display": "Петя",
                                        "username": "petya", "private": True}}
            agent._send_text = AsyncMock(return_value=True)
            result = await agent.tell("tg", 9, False, 2, "петя", "привет")
            self.assertTrue(result["ok"])
            self.assertEqual(result["name"], "Петя")
        finally:
            agent._groups, agent._contacts, agent._send_text = old_groups, old_contacts, old_text

    async def test_cross_chat_into_group_follows_target_setting(self):
        from src import agent, chats
        old_groups, old_text, old_chats = agent._groups, agent._send_text, chats._chats
        try:
            agent._groups = {}
            agent._send_text = AsyncMock(return_value=True)
            chats._chats = {"tg:-100": {"platform": "tg", "id": -100,
                                        "kind": "group", "title": "Кенты"}}
            result = await agent.tell("tg", 9, False, 2, "Кенты", "привет")
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "cross_chat_disabled")
            agent._groups = {"tg_-100": {"cross_chat_enabled": True}}
            result = await agent.tell("tg", 9, False, 2, "Кенты", "привет")
            self.assertTrue(result["ok"])
            self.assertEqual(result["target"], "chat")
        finally:
            agent._groups, agent._send_text, chats._chats = old_groups, old_text, old_chats

    async def test_owner_alias_resolves_without_contact_history(self):
        from src import agent
        old_contacts, old_text = agent._contacts, agent._send_text
        try:
            agent._contacts = {}
            agent._send_text = AsyncMock(return_value=True)
            result = await agent.tell("tg", 9, True, 2, "фолз", "привет")
            self.assertTrue(result["ok"])
        finally:
            agent._contacts, agent._send_text = old_contacts, old_text

    def test_image_model_labels_are_human_readable(self):
        from src.image_gen import image_model_label
        self.assertEqual(image_model_label("auto", "ru"), "🎲 Авто")
        self.assertEqual(image_model_label("auto", "en"), "🎲 Auto")
        self.assertEqual(image_model_label("flare", "ru"), "GPT Image 2.5 Flare")
        self.assertEqual(image_model_label("sunburst", "ru"), "GPT Image 2.5 Sunburst")
        self.assertEqual(image_model_label("paint", "ru"), "Kulsh (SVG)")

    def test_group_toggles_have_expected_defaults(self):
        from src import agent
        old_groups = agent._groups
        try:
            agent._groups = {}
            self.assertFalse(agent.cross_chat_allowed("tg", -100, False))
            self.assertTrue(agent.cross_chat_allowed("tg", 42, True))
            self.assertTrue(agent.autonomous_allowed("tg", -100))
        finally:
            agent._groups = old_groups

    async def test_autonomous_post_uses_observer_when_history_exists(self):
        from src import loops
        memory = deque([{"type": "bot", "ts": 1, "text": "я тут сам с собой"}])
        with patch.object(loops, "get_chat_memory", return_value=memory), \
                patch.object(loops, "memory_to_messages", return_value=[{"role": "model", "text": "..."}]), \
                patch.object(loops, "ask_ai_async", AsyncMock(return_value="раз!separateдва")) as ask, \
                patch.object(loops.agent, "deliver_message", AsyncMock(return_value=True)), \
                patch.object(loops, "add_bot_memory"):
            await loops._autonomous_post("tg", -100, 0)
        self.assertEqual(ask.await_args.kwargs["context_type"], "observer")
        self.assertIsNotNone(ask.await_args.kwargs["messages"])

    async def test_autonomous_post_uses_random_without_history(self):
        from src import loops
        memory = deque()
        with patch.object(loops, "get_chat_memory", return_value=memory), \
                patch.object(loops, "ask_ai_async", AsyncMock(return_value="тихо тут")) as ask, \
                patch.object(loops.agent, "deliver_message", AsyncMock(return_value=True)), \
                patch.object(loops, "add_bot_memory"):
            await loops._autonomous_post("tg", -100, 0)
        self.assertEqual(ask.await_args.kwargs["context_type"], "random")

    async def test_autonomous_post_never_writes_to_private_chat(self):
        from src import loops
        with patch.object(loops, "ask_ai_async", AsyncMock(return_value="x")) as ask, \
                patch.object(loops.agent, "deliver_message", AsyncMock(return_value=True)) as send:
            await loops._autonomous_post("tg", 42, 0)
        ask.assert_not_awaited()
        send.assert_not_awaited()

    async def test_autonomous_candidates_skip_private_chats(self):
        from src import chats, loops
        old_chats = chats._chats
        try:
            chats._chats = {
                "tg:-100": {"platform": "tg", "id": -100, "kind": "group", "title": "Кенты"},
                "tg:42": {"platform": "tg", "id": 42, "kind": "private", "title": "Личка"},
            }
            found = await loops._autonomous_candidates("tg")
            self.assertEqual([entry["id"] for entry in found], [-100])
        finally:
            chats._chats = old_chats

    def test_gpt_sol_is_paid_like_grok(self):
        from src import util
        self.assertTrue(util.is_paid_model("gpt-6.1-sol"))
        self.assertEqual(util.MODEL_PRICING["gpt-6.1-sol"]["input"],
                         util.MODEL_PRICING["grok-4.7"]["input"])
        self.assertEqual(util.MODEL_PRICING["gpt-6.1-sol"]["output"],
                         util.MODEL_PRICING["grok-4.7"]["output"])

    def test_flare_weekly_limit_is_four(self):
        from datetime import datetime
        from src import image_gen
        old_usage = image_gen._image_usage
        image_gen._image_usage = {}
        try:
            with patch.object(image_gen, "msk_now", return_value=datetime(2026, 11, 9, 12)), \
                    patch.object(image_gen, "_save_usage"):
                for _ in range(3):
                    self.assertTrue(image_gen.consume_image("tg", 777001))
                self.assertEqual(image_gen.image_remaining("tg", 777001), 1)
                self.assertTrue(image_gen.consume_image("tg", 777001))
                self.assertFalse(image_gen.consume_image("tg", 777001))
            with patch.object(image_gen, "msk_now", return_value=datetime(2026, 11, 16, 12)), \
                    patch.object(image_gen, "_save_usage"):
                self.assertEqual(image_gen.image_remaining("tg", 777001), 4)
        finally:
            image_gen._image_usage = old_usage

    def test_compact_prompt_for_short_chat(self):
        from src import ai
        self.assertTrue(ai._is_compact_chat("че делаешь", None, "default", None, None))
        self.assertFalse(ai._is_compact_chat("нарисуй мопса", None, "default", None, None))
        full = ai.build_system_prompt("tg", -100, 0)
        compact = ai.build_system_prompt("tg", -100, 0, compact=True)
        self.assertLess(len(compact), len(full) - 3000)
        self.assertIn(ai.STYLE_REFERENCE[:40], compact)
        self.assertNotIn("УТИЛИТЫ.", compact)

    def test_compact_prompt_detects_short_history_message(self):
        from src import ai
        messages = [{"role": "user",
                     "text": "[20:00] [tg] Фолз (@lolfall, id:1, msg_id:2): че"}]
        self.assertTrue(ai._is_compact_chat(None, messages, "default", None, None))
        self.assertTrue(ai._is_compact_chat(None, messages, "observer", None, None))

    def test_separator_splits_glued_capitalized_text(self):
        from src import util
        self.assertEqual(
            util.split_by_separator("ща перерисую!separateKulsh Paint 1.2"),
            ["ща перерисую", "Kulsh Paint 1.2"],
        )
        self.assertEqual(
            util.split_by_separator("one!separateTwo"),
            ["one", "Two"],
        )
        self.assertEqual(util.split_by_separator("this is separately fine"),
                         ["this is separately fine"])

    def test_wants_drawing_only_on_explicit_request(self):
        from src import util
        self.assertTrue(util.wants_drawing("перерисуй эту картинку"))
        self.assertTrue(util.wants_drawing("нарисуй мопса"))
        self.assertFalse(util.wants_drawing("давай по новой"))
        self.assertTrue(util.wants_drawing("давай по новой", has_draw_context=True))
        self.assertFalse(util.wants_drawing("ты рисуешь?", has_draw_context=True))

    def test_compact_prompt_disabled_after_drawing(self):
        from src import ai
        messages = [
            {"role": "user", "text": "[20:00] [tg] Фолз (@lolfall, id:1, msg_id:2): перерисуй"},
            {"role": "model", "text": "[нарисовал картинку] моаи"},
            {"role": "user", "text": "[20:01] [tg] Фолз (@lolfall, id:1, msg_id:3): давай по новой"},
        ]
        self.assertFalse(ai._is_compact_chat(None, messages, "default", None, None))

    async def test_paint_passes_reference_image(self):
        from src import ai
        colors = ["#ff0000", "#00ff00", "#0000ff", "#ffff00", "#ff00ff", "#00ffff"]
        circles = ",".join(
            f'{{"type":"circle","x":{i * 15},"y":{i * 12},"x2":{i * 15 + 30},'
            f'"y2":{i * 12 + 30},"fill":"{colors[i % len(colors)]}"}}'
            for i in range(30)
        )
        good = f'{{"width":800,"height":600,"background":"#ffffff","elements":[{circles}]}}'
        reference = b"\x89PNG\r\n\x1a\nfake"
        with patch.object(ai, "ask_ai_async", AsyncMock(return_value=good)) as call:
            result = await ai.ask_paint("перерисуй это", "tg", 1, 2, reference_image=reference)
        self.assertEqual(call.await_count, 1)
        self.assertIs(call.await_args.kwargs.get("image_bytes"), reference)
        self.assertIn("!draw", result)

    async def test_paint_does_not_waste_extra_request(self):
        from src import ai
        sparse = ('{"width":800,"height":600,"background":"#000000","elements":'
                  '[{"type":"rect","x":0,"y":0,"w":20,"h":20,"fill":"#ffffff"}]}')
        with patch.object(ai, "ask_ai_async", AsyncMock(return_value=sparse)) as call:
            result = await ai.ask_paint("мопс", "tg", 1, 2)
        # Одна генерация — один запрос, без дорогого второго прохода.
        self.assertEqual(call.await_count, 1)
        self.assertIn("!draw", result)

    def test_svg_does_not_connect_separate_subpaths(self):
        from PIL import Image
        from src import draw
        spec = {
            "width": 120, "height": 40, "background": "#ffffff",
            "elements": [{"type": "svg", "d": "M10 20 L40 20 M80 20 L110 20",
                          "outline": "#000000", "width": 4}],
        }
        img = Image.open(draw.render_spec(spec)).convert("RGB")
        self.assertEqual(img.getpixel((60, 20)), (255, 255, 255))
        self.assertNotEqual(img.getpixel((25, 20)), (255, 255, 255))
        self.assertNotEqual(img.getpixel((95, 20)), (255, 255, 255))

    async def test_process_drawing_accepts_native_svg(self):
        from src import draw
        result = await draw.process_drawing(
            '<svg width="80" height="80" viewBox="0 0 80 80">'
            '<rect width="80" height="80" fill="#000000"/>'
            '<circle cx="40" cy="40" r="20" fill="#ffffff"/></svg>'
        )
        self.assertIsNotNone(result.png)
        self.assertGreater(len(result.png.getvalue()), 100)

    async def test_svg_is_rendered(self):
        from src import draw
        spec = draw.svg_to_spec(
            '<svg width="200" height="120" viewBox="0 0 200 120" '
            'xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#102030"/>'
            '<circle cx="60" cy="60" r="30" fill="#ff0000"/>'
            '<text x="100" y="90" font-size="20" fill="#ffffff">kulsh</text></svg>'
        )
        self.assertIsNotNone(spec)
        self.assertGreaterEqual(len(spec["elements"]), 2)
        png = draw.render_spec(spec)
        self.assertGreater(len(png.getvalue()), 100)


class ImageBillingTests(unittest.IsolatedAsyncioTestCase):
    async def test_paid_image_charged_once(self):
        from src import image_gen, billing
        with patch.object(image_gen, "image_remaining", return_value=0), \
                patch.object(image_gen, "generate_image", AsyncMock(return_value=b"png")), \
                patch.object(billing, "charge_balance", return_value=True) as charge, \
                patch.object(billing, "add_credit") as refund:
            result = await image_gen.generate_for_user("tg", 555001, "auto", {"prompt": "x"})
            self.assertEqual(result, b"png")
            self.assertEqual(charge.call_args.args[2], 3)
            refund.assert_not_called()

    async def test_failed_paid_image_is_refunded(self):
        from src import image_gen, billing
        with patch.object(image_gen, "generate_image", AsyncMock(side_effect=RuntimeError("failed"))), \
                patch.object(billing, "charge_balance", return_value=True), \
                patch.object(billing, "add_credit") as refund:
            with self.assertRaises(RuntimeError):
                await image_gen.generate_for_user("tg", 555002, "sunburst", {"prompt": "x"})
            self.assertEqual(refund.call_args.args[2], 4)


class NewFeatureTests(unittest.IsolatedAsyncioTestCase):
    def test_effort_setting_and_labels(self):
        from src import util
        self.assertIn("xhigh", util.DRAW_EFFORTS)
        self.assertEqual(util.draw_effort_label("max", "ru"), "Макс")
        cfg = util.get_user_config("tg", -555, 1)
        self.assertEqual(cfg.get("draw_effort"), "medium")
        cfg["draw_effort"] = "max"
        self.assertEqual(cfg.get("draw_effort"), "max")

    def test_modes_are_gone(self):
        from src import util, ui
        cfg = util.get_user_config("tg", -600, 1)
        cfg["communication_mode"] = "assistant"
        self.assertEqual(util.get_user_config("tg", -600, 1).get("communication_mode"), "kent")
        text = ui.config_text("tg", -600, 1)
        self.assertNotIn("Режим", text)
        self.assertIn("Усилие", text)

    def test_svg_linear_gradient_is_rendered(self):
        from PIL import Image
        from src import draw
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50" viewBox="0 0 100 50">'
            '<defs><linearGradient id="g1" x1="0" y1="0" x2="1" y2="0">'
            '<stop offset="0" stop-color="#ff0000"/>'
            '<stop offset="1" stop-color="#0000ff"/>'
            '</linearGradient></defs>'
            '<rect x="0" y="0" width="100" height="50" fill="url(#g1)"/></svg>'
        )
        spec = draw.svg_to_spec(svg)
        self.assertIsNotNone(spec)
        img = Image.open(draw.render_spec(spec)).convert("RGB")
        left = img.getpixel((5, 25))
        right = img.getpixel((95, 25))
        self.assertGreater(left[0], left[2])
        self.assertGreater(right[2], right[0])

    async def test_workspace_file_actions(self):
        from src import workspace
        workspace.write_text("tg", -777, "notes/test.txt", "line1\nline2\nline3")
        self.assertIn("line2", workspace.read_text("tg", -777, "notes/test.txt", 2, 2))
        cleaned, actions = workspace.extract_actions(
            "готово\n!files\n!read notes/test.txt 1-2\n!send notes/test.txt"
        )
        kinds = [a.kind for a in actions]
        self.assertEqual(kinds, ["send", "read", "list"])
        self.assertNotIn("!files", cleaned)
        archive = workspace.make_archive("tg", -777, "notes", "notes.zip")
        files = workspace.unpack_archive("tg", -777, archive)
        self.assertTrue(any("test.txt" in f for f in files))

    def test_page_marker_and_url_detection(self):
        from src import ai
        urls, cleaned = ai.extract_page_marker("!read_page https://example.com/a https://example.com/b")
        self.assertEqual(urls, ["https://example.com/a", "https://example.com/b"])
        self.assertEqual(cleaned, "")
        self.assertTrue(ai.wants_page_read("прочитай что там по ссылке"))
        self.assertFalse(ai.wants_page_read("просто скинь ссылку"))
        self.assertEqual(ai.extract_urls("смотри https://x.dev/page?q=1)."),
                         ["https://x.dev/page?q=1"])

    def test_stream_preview_hides_markers(self):
        from src import telegram
        visible = telegram._stream_visible("ща нарисую!separateвот\n!draw\n```json\n{}")
        self.assertNotIn("!separate", visible)
        self.assertNotIn("!draw", visible)
        self.assertNotIn("```", visible)

    def test_effort_hints_are_universal(self):
        from src import ui
        text = ui.effort_text("tg", -903, 1).casefold()
        self.assertNotIn("svg", text)
        self.assertNotIn("градиент", text)
        self.assertNotIn("вектор", text)
        self.assertIn("детализац", text)

    def test_streaming_and_split_are_exclusive(self):
        from src import util
        cfg = util.get_user_config("tg", -905, 1)
        cfg["separate_enabled"] = True
        cfg["streaming_enabled"] = True
        self.assertFalse(util.get_user_config("tg", -905, 1)["streaming_enabled"])

    def test_prompt_contains_effort_hint(self):
        from src import ai, util
        cfg = util.get_user_config("tg", -907, 1)
        cfg["draw_effort"] = "max"
        self.assertIn("40-65", ai.build_system_prompt("tg", -907, 1))
        cfg["draw_effort"] = "low"
        self.assertIn("5-10", ai.build_system_prompt("tg", -907, 1))

    def test_workspace_writes_any_extension_and_expires_files(self):
        from src import workspace
        cleaned, actions = workspace.extract_actions(
            "!write app.py\n```python\nprint('hi')\n```"
        )
        self.assertEqual(actions[0].kind, "write")
        self.assertEqual(cleaned.strip(), "")
        workspace.save_upload("tg", -904, "photo.jpg", b"\x89PNGdata", "image/jpeg",
                              file_id="FILEID123", message_id=7)
        base = workspace.workspace_dir("tg", -904)
        workspace.cleanup_expired("tg", -904)
        index_path = os.path.join(base, ".index.json")
        with open(index_path, encoding="utf-8") as f:
            data = json.load(f)
        entry = data["files"]["photo.jpg"]
        self.assertEqual(entry["file_id"], "FILEID123")
        entry["used"] = time.time() - 9999
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.assertGreaterEqual(workspace.cleanup_expired("tg", -904), 1)
        self.assertFalse(os.path.isfile(os.path.join(base, "photo.jpg")))

    def test_send_without_path_is_allowed(self):
        from src import workspace
        _, actions = workspace.extract_actions("!pack\n!send")
        kinds = [a.kind for a in actions]
        self.assertIn("send", kinds)
        self.assertEqual(actions[-1].payload, "")

    async def test_workspace_recovers_file_from_chat(self):
        from src import workspace
        from src import util as util_mod
        workspace.save_upload("ds", -906, "note.txt", b"old", "text/plain",
                              url="https://cdn.example/note.txt")
        base = workspace.workspace_dir("ds", -906)
        os.remove(os.path.join(base, "note.txt"))
        with patch.object(util_mod, "download_image_bytes", AsyncMock(return_value=b"fresh")):
            self.assertTrue(await workspace.recover_file("ds", -906, "note.txt"))
        self.assertEqual(workspace.as_bytes("ds", -906, "note.txt"), b"fresh")


if __name__ == "__main__":
    unittest.main()
