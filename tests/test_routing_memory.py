import unittest
import tempfile
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

    def test_system_role_is_not_embedded_in_user_content(self):
        messages = ai._to_openai_messages([{"role": "user", "parts": [{"text": "hi"}]}], "rules", True)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_easy_uses_luna_first(self):
        with patch.object(ai, "_jev_complexity", AsyncMock(return_value="easy")):
            result = await ai._pick_auto_models(False, "привет", False, "tg", 1, "default")
        self.assertEqual(result[0], "gpt-6-luna")
        self.assertFalse(any(ai.is_paid_model(m) for m in result))

    async def test_hard_vision_and_paid_constraints(self):
        with patch.object(ai, "_jev_complexity", AsyncMock(return_value="hard")):
            result = await ai._pick_auto_models(True, "сложная задача", False, "tg", 1, "default")
        self.assertNotIn("deepseek-v4-pro", result)
        self.assertFalse(any(ai.is_paid_model(m) for m in result))

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
        self.assertEqual(image_model_label("paint", "ru"), "Kulsh Paint 1.1")

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

    async def test_autonomous_post_ignores_who_spoke_last(self):
        from src import loops
        memory = deque([{"type": "bot", "ts": 1, "text": "я тут сам с собой"}])
        with patch.object(loops, "get_chat_memory", return_value=memory), \
                patch.object(loops, "memory_to_messages", return_value=[{"role": "model", "text": "..."}]), \
                patch.object(loops, "ask_ai_async", AsyncMock(return_value="раз!separateдва")) as ask, \
                patch.object(loops.agent, "deliver_message", AsyncMock(return_value=True)), \
                patch.object(loops, "add_bot_memory"):
            await loops._autonomous_post("tg", 1, 0)
        self.assertEqual(ask.await_args.kwargs["context_type"], "random")
        self.assertIsNotNone(ask.await_args.kwargs["messages"])

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


if __name__ == "__main__":
    unittest.main()
