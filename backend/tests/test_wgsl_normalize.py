"""normalize_wgsl_source 与前端 normalizeWgslSource 语义对齐的最小校验。"""
import unittest

from app.storage import normalize_wgsl_source


class TestNormalizeWgslSource(unittest.TestCase):
    def test_nbsp_becomes_ascii_space(self) -> None:
        self.assertEqual(normalize_wgsl_source("let\u00a0x"), "let x")

    def test_strips_bom(self) -> None:
        self.assertEqual(normalize_wgsl_source("\ufeff// hi"), "// hi")

    def test_crlf_to_lf(self) -> None:
        self.assertEqual(normalize_wgsl_source("a\r\nb"), "a\nb")


if __name__ == "__main__":
    unittest.main()
