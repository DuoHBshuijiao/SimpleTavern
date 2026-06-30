import unittest
from unittest.mock import patch

from app.routes import import_export as ie


def _html_with_mbxm() -> str:
    """Minimal window.mbxM.push payload with one characterStore key."""
    inner = (
        '{"J-characterStore":{'
        '"character":{'
        '"name":"N","chat_name":"N","first_message":"one",'
        '"first_messages":["one","two"],'
        '"personality":"P","scenario":"S",'
        '"description":"<p>D</p>","example_dialogs":"E",'
        '"avatar":"x.webp"'
        "}}}"
    )
    # JS source: backslash-escape quotes
    esc = inner.replace("\\", "\\\\").replace('"', '\\"')
    return f'<!DOCTYPE html><script>window.mbxM.push(JSON.parse("{esc}"))</script>'


class TestJanitorMbxm(unittest.TestCase):
    def test_extract_character_from_mbxm_html(self) -> None:
        html = _html_with_mbxm()
        ch = ie._extract_janitor_character_from_mbxm_html(html)
        self.assertIsNotNone(ch)
        assert ch is not None
        self.assertEqual(ch.get("name"), "N")
        self.assertEqual(ch.get("first_messages"), ["one", "two"])

    @patch.object(ie, "_download_avatar_from_url", return_value="testavatar.webp")
    def test_parse_character_from_html_uses_mbxm(self, _m: object) -> None:
        html = _html_with_mbxm()
        card, w = ie._parse_character_from_html(html, None)
        self.assertEqual(card.name, "N")
        self.assertEqual(card.firstMessage, "one")
        self.assertEqual(len(card.extraFirstMessageEntries), 1)
        self.assertEqual(card.extraFirstMessageEntries[0].text, "two")
        self.assertIn("D", card.description)
        self.assertEqual(card.avatar, "testavatar.webp")
        self.assertEqual(w, [])


_MOCK_ACC = """<!DOCTYPE html><head>
<meta property="og:title" content="Otitle">
</head><body>
<div class="_characterInfoAccordionItem_1" id="info-0">
<span class="_characterInfoAccordionTitleText_1">Personality (10 tokens)</span>
</div>
<div id="panel-info-0" class="_characterInfoAccordionPanel_1 "><div class="_characterInfoMarkdownContainer_1">
<p>Per content</p>
</div></div>
</body></html>"""


class TestJanitorAccordion(unittest.TestCase):
    def test_parse_accordion(self) -> None:
        card, w = ie._parse_character_from_html(_MOCK_ACC, None)
        self.assertEqual(card.name, "Otitle")
        self.assertIn("Per content", card.personality)
