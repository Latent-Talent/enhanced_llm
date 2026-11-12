import json
import unittest
from unittest.mock import patch

from enhanced_llm import NODE_CLASS_MAPPINGS
from enhanced_llm.nodes import EnhancedLLMGenerate, EnhancedLLMRelease, EnhancedLLMStatus
from enhanced_llm.runtime import ModelRef


class TestNodes(unittest.TestCase):
    def test_node_registration(self):
        self.assertEqual(len(NODE_CLASS_MAPPINGS), 5)
        self.assertIn("EnhancedLLMGenerate", NODE_CLASS_MAPPINGS)

    def test_generation_return_contract(self):
        borrowed = ModelRef(borrowed_clip=object())
        def fake_generate(clip, **kwargs):
            return "answer", "thought", {"mtp_requested": kwargs["mtp"]}
        with patch("enhanced_llm.nodes.generate_native", fake_generate):
            result = EnhancedLLMGenerate().generate(borrowed, "question")
        self.assertEqual(result[:2], ("answer", "thought"))
        self.assertEqual(json.loads(result[2])["mtp_requested"], "auto")

    def test_release_is_explicit(self):
        with self.assertRaises(ValueError):
            EnhancedLLMRelease().release(mode="selected")

    def test_status_is_json(self):
        status = json.loads(EnhancedLLMStatus().status()[0])
        self.assertEqual(status["engine"], "comfy_native")


if __name__ == "__main__":
    unittest.main()
