import unittest

from enhanced_llm.native import (
    generate_native, mtp_head_present, quantization_diagnostics,
    requested_mtp, split_reasoning,
)


class FakeClip:
    def __init__(self):
        self.params = None
        self.decode_calls = []

    def tokenize(self, prompt, **kwargs):
        self.params = kwargs
        return [[(1, None), (2, None)]]

    def generate(self, tokens, **kwargs):
        self.params = {**self.params, **kwargs}
        return [11, 12, 13]

    def decode(self, ids):
        self.decode_calls.append(ids)
        return "A generated answer"


class TestNative(unittest.TestCase):
    def test_native_mode_mapping(self):
        self.assertIs(requested_mtp("auto"), True)
        self.assertIs(requested_mtp("off"), False)
        self.assertEqual(requested_mtp("tree3s1"), "tree3s1")
        with self.assertRaises(ValueError):
            requested_mtp("unknown")

    def test_generate_delegates_native(self):
        clip = FakeClip()
        text, thinking, stats = generate_native(clip, prompt="hello", mtp="auto", seed=19)
        self.assertEqual(text, "A generated answer")
        self.assertEqual(thinking, "")
        self.assertIs(clip.params["mtp"], True)
        self.assertEqual(clip.params["seed"], 19)
        self.assertEqual(stats["output_tokens"], 3)
        self.assertEqual(stats["matrix_precision"]["mode"], "native")
        self.assertEqual(stats["quantization"]["format_selection"], "native_auto")

    def test_reasoning_split(self):
        clip = FakeClip()
        result = split_reasoning("<think>analysis</think>final", "test", [], clip)
        self.assertEqual(result, ("final", "analysis"))

    def test_metadata_not_invented(self):
        self.assertEqual(mtp_head_present(FakeClip()), None)
        self.assertFalse(quantization_diagnostics(FakeClip())["metadata_present"])

    def test_zero_length_rejected(self):
        with self.assertRaises(ValueError):
            generate_native(FakeClip(), prompt="bad", max_tokens=0)


if __name__ == "__main__":
    unittest.main()
