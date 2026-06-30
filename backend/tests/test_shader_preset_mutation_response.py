"""ShaderPresetMutationResponse 契约模型校验。"""
import unittest

from app.schemas import ShaderPresetDiagnosticItem, ShaderPresetMutationResponse


class TestShaderPresetMutationResponse(unittest.TestCase):
    def test_defaults(self) -> None:
        r = ShaderPresetMutationResponse(filename="a.wgsl", normalized=True, diagnostics=[])
        self.assertTrue(r.ok)
        self.assertEqual(r.filename, "a.wgsl")
        self.assertEqual(r.diagnostics, [])
        self.assertIsNotNone(r.note)

    def test_diagnostic_item_optional_fields(self) -> None:
        d = ShaderPresetDiagnosticItem(message="x", severity="warning", line=10, column=2)
        self.assertEqual(d.line, 10)
        self.assertEqual(d.column, 2)


if __name__ == "__main__":
    unittest.main()
