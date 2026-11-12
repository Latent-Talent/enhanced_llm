import json
import unittest
from unittest.mock import patch

from enhanced_llm.enhancer import EnhancedLLMPromptEnhancer
from enhanced_llm.enhancer_core import (
    apply_generated, clean_generated, dumps_history, parse_history, select_index,
)
from enhanced_llm.runtime import ModelRef


class TestEnhancerCore(unittest.TestCase):
    def test_parse_and_roundtrip(self):
        prompts = ["first", "héllo", "third"]
        self.assertEqual(parse_history(dumps_history(prompts)), prompts)
        for bad in ('not json', '{"x": 1}', '[1]', '[null]'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_history(bad)

    def test_fixed_cycle_and_wrap(self):
        self.assertEqual(select_index("fixed", 2, 4, 17), 2)
        self.assertEqual(select_index("increment", 2, 4, 3), 1)
        self.assertEqual(select_index("decrement", 2, 4, 3), 3)

    def test_shuffle_is_deck_with_no_boundary_repeat(self):
        for seed in (0, 33, 999):
            indexes = [select_index("shuffle", 0, 5, i, seed) for i in range(20)]
            for pos in range(0, 20, 5):
                self.assertEqual(set(indexes[pos:pos + 5]), set(range(5)))
            for pos in (5, 10, 15):
                self.assertNotEqual(indexes[pos], indexes[pos - 1])

    def test_random_is_repeatable(self):
        self.assertEqual(
            [select_index("random", 0, 6, i, 22) for i in range(12)],
            [select_index("random", 0, 6, i, 22) for i in range(12)],
        )

    def test_overwrite_and_append(self):
        self.assertEqual(apply_generated(["a", "b"], 0, ["x"], True), (["x", "b"], 0))
        self.assertEqual(apply_generated(["a"], 0, ["x", "y"], True), (["a", "x", "y"], 2))

    def test_clean_response(self):
        self.assertEqual(clean_generated("Enhanced Prompt: red flowers"), "red flowers")
        self.assertEqual(clean_generated("plain text"), "plain text")
        with self.assertRaises(ValueError):
            clean_generated("")


class TestEnhancerNode(unittest.TestCase):
    def setUp(self):
        self.node = EnhancedLLMPromptEnhancer()
        self.ref = ModelRef(borrowed_clip=object())

    def test_stored_mode_never_uses_gpu(self):
        with patch("enhanced_llm.enhancer.generate_native") as generate:
            result = self.node.output_prompts(
                self.ref, "original", history_json='["one", "two"]', active_index=1
            )
            generate.assert_not_called()
        self.assertEqual(result["result"][:2], ("two", "original"))
        self.assertEqual(json.loads(result["ui"]["enhanced_llm_enhancer"][0])["mode"], "stored")

    def test_empty_history_passes_source(self):
        result = self.node.output_prompts(self.ref, "original")
        self.assertEqual(result["result"][0], "original")

    def test_manual_batch_appends_and_keeps_original(self):
        seeds = []
        def generate(clip, **kwargs):
            seeds.append(kwargs["seed"])
            return f"Enhanced Prompt: result {len(seeds)}", "", {"total_seconds": 0.1}
        with patch("enhanced_llm.enhancer.generate_native", side_effect=generate):
            result = self.node.output_prompts(
                self.ref, "original", manual_request="req-1", state_id="state",
                history_json='["old"]', batch_count=3, seed=7, overwrite_enhanced=True,
            )
        self.assertEqual(seeds, [7, 8, 9])
        self.assertEqual(result["result"][1], "original")
        self.assertEqual(parse_history(result["result"][2]), [
            "old", "result 1", "result 2", "result 3",
        ])
        payload = json.loads(result["ui"]["enhanced_llm_enhancer"][0])
        self.assertEqual(payload["request"], "req-1")
        self.assertEqual(payload["state_id"], "state")
        self.assertFalse(payload["overwrite"])

    def test_workflow_enhancement_once(self):
        with patch("enhanced_llm.enhancer.generate_native", return_value=(
            "New", "", {"total_seconds": 0.1}
        )) as generate:
            result = self.node.output_prompts(self.ref, "old", enhance_with_workflow=True)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(result["result"][0], "New")

    def test_manual_request_invalidates_cached_node(self):
        self.assertIsNone(self.node.IS_CHANGED(prompt_cycle="fixed"))
        self.assertNotEqual(
            self.node.IS_CHANGED(prompt_cycle="increment"),
            self.node.IS_CHANGED(prompt_cycle="increment"),
        )
        self.assertNotEqual(
            self.node.IS_CHANGED(manual_request="nonce"),
            self.node.IS_CHANGED(manual_request="nonce"),
        )


if __name__ == "__main__":
    unittest.main()
