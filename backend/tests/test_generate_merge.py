import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routes.generate import _merge_assistant_output_into_message
from app.schemas import Chat, ChatMessage


class MergeAssistantOutputTests(unittest.TestCase):
    def test_merges_output_into_existing_assistant_variant(self) -> None:
        chat = Chat(
            characterId="char-a",
            messages=[
                ChatMessage(id="user-1", role="user", content="hi"),
                ChatMessage(
                    id="assistant-1",
                    role="assistant",
                    content="old",
                    characterId="char-a",
                    reasoningContent="old reason",
                    reasoningDurationSec=1.0,
                ),
            ],
        )

        merged = _merge_assistant_output_into_message(
            chat,
            message_id="assistant-1",
            content="new",
            character_id="char-a",
            reasoning_content="new reason",
            reasoning_duration_sec=2.0,
        )

        self.assertEqual(merged.id, "assistant-1")
        self.assertEqual(merged.content, "new")
        self.assertEqual(merged.reasoningContent, "new reason")
        self.assertEqual(merged.reasoningDurationSec, 2.0)
        self.assertEqual(merged.greetingVariantIndex, 1)
        self.assertEqual(merged.greetingVariants, ["old", "new"])
        self.assertEqual(merged.greetingVariantReasoningContents, ["old reason", "new reason"])
        self.assertEqual(merged.greetingVariantReasoningDurations, [1.0, 2.0])
        self.assertEqual(len(chat.messages), 2)

    def test_merges_reasoning_only_output_as_empty_content_variant(self) -> None:
        chat = Chat(
            characterId="char-a",
            messages=[
                ChatMessage(id="assistant-1", role="assistant", content="old", characterId="char-a"),
            ],
        )

        merged = _merge_assistant_output_into_message(
            chat,
            message_id="assistant-1",
            content="",
            character_id="char-a",
            reasoning_content="thinking only",
            reasoning_duration_sec=0.5,
        )

        self.assertEqual(merged.content, "")
        self.assertEqual(merged.reasoningContent, "thinking only")
        self.assertEqual(merged.greetingVariantIndex, 1)
        self.assertEqual(merged.greetingVariants, ["old", ""])
        self.assertEqual(merged.greetingVariantReasoningContents, ["", "thinking only"])
        self.assertEqual(merged.greetingVariantReasoningDurations, [None, 0.5])


if __name__ == "__main__":
    unittest.main()
