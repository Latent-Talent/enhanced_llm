import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from enhanced_llm import enhancer_storage as storage


class TestEnhancerStorage(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        patcher = patch.object(storage, "user_root", return_value=self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_templates_are_protected(self):
        self.assertIn("Default / General", [r["label"] for r in storage.templates()])
        with self.assertRaises(ValueError):
            storage.remove_template("Default / General")

    def test_user_template_save_and_delete(self):
        saved = storage.save_template("My Template", "Describe better")
        self.assertEqual(saved["label"], "User / My Template")
        self.assertTrue(any(r["label"] == saved["label"] for r in storage.templates()))
        storage.remove_template(saved["label"])
        self.assertNotIn(saved["label"], [r["label"] for r in storage.templates()])

    def test_paths_cannot_escape_user_directory(self):
        for value in ("../oops", "../../root", "a/b", "", ".."):
            with self.subTest(value=value), self.assertRaises(ValueError):
                storage.save_template(value, "text")

    def test_prompt_sets_roundtrip(self):
        storage.save_prompt_set("My Set", ["one", "two"], 1)
        self.assertIn("My Set", storage.prompt_sets())
        loaded = storage.load_prompt_set("My Set")
        self.assertEqual(loaded["prompts"], ["one", "two"])
        self.assertEqual(loaded["active_index"], 1)
        storage.remove_prompt_set("My Set")
        self.assertNotIn("My Set", storage.prompt_sets())


if __name__ == "__main__":
    unittest.main()
