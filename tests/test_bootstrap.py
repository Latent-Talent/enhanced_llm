"""Check ComfyUI's package entrypoint without needing a ComfyUI installation."""

import importlib.util
from pathlib import Path
import sys
import unittest


class TestPackageBootstrap(unittest.TestCase):
    def test_custom_node_package_entrypoint(self):
        path = Path(__file__).resolve().parents[1]
        name = "enhanced_llm_custom_node_bootstrap_test"
        spec = importlib.util.spec_from_file_location(
            name, path / "__init__.py", submodule_search_locations=[str(path)]
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        self.addCleanup(sys.modules.pop, name, None)
        spec.loader.exec_module(module)
        self.assertIn("EnhancedLLMGenerate", module.NODE_CLASS_MAPPINGS)
        self.assertEqual(len(module.NODE_CLASS_MAPPINGS), 5)


if __name__ == "__main__":
    unittest.main()
