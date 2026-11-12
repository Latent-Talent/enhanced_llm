import os
import tempfile
import threading
import time
import unittest

from enhanced_llm.runtime import ModelRef, NativeLLMRuntime


class TestRuntime(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = os.path.join(self.temp.name, "model.safetensors")
        with open(self.path, "wb") as stream:
            stream.write(b"original")
        self.loads = []
        self.runtime = NativeLLMRuntime(
            loader=lambda path, kind: self.loads.append((path, kind)) or object()
        )
        self.ref = ModelRef(path=self.path)

    def test_cache_reuse(self):
        a, reused_a = self.runtime.run(self.ref, lambda clip: clip)
        b, reused_b = self.runtime.run(self.ref, lambda clip: clip)
        self.assertIs(a, b)
        self.assertFalse(reused_a)
        self.assertTrue(reused_b)
        self.assertEqual(len(self.loads), 1)

    def test_file_replacement_invalidates_cache(self):
        original, _ = self.runtime.run(self.ref, lambda clip: clip)
        with open(self.path, "ab") as stream:
            stream.write(b"new")
        replaced, reused = self.runtime.run(self.ref, lambda clip: clip)
        self.assertIsNot(original, replaced)
        self.assertFalse(reused)
        self.assertEqual(self.runtime.status()["cached_model_count"], 1)

    def test_cache_limit(self):
        other_path = os.path.join(self.temp.name, "other.safetensors")
        with open(other_path, "wb") as stream:
            stream.write(b"data")
        self.runtime.configure(1)
        self.runtime.run(self.ref, lambda _: None)
        self.runtime.run(ModelRef(path=other_path), lambda _: None)
        self.assertEqual(self.runtime.status()["cached_model_count"], 1)

    def test_release(self):
        self.runtime.run(self.ref, lambda _: None)
        self.assertEqual(self.runtime.release(self.ref), 1)
        self.assertEqual(self.runtime.release(self.ref), 0)

    def test_borrowed_clip_is_not_owned(self):
        clip = object()
        ref = ModelRef(borrowed_clip=clip)
        result, reused = self.runtime.run(ref, lambda x: x)
        self.assertIs(result, clip)
        self.assertTrue(reused)
        self.assertEqual(self.runtime.release(ref), 0)
        self.assertEqual(self.runtime.status()["cached_model_count"], 0)

    def test_invalid_model_reference(self):
        with self.assertRaises(ValueError):
            ModelRef()
        with self.assertRaises(ValueError):
            ModelRef(path=self.path, borrowed_clip=object())

    def test_serial_generation(self):
        entered = []
        running = [0]
        barrier = threading.Barrier(3)

        def op(_):
            running[0] += 1
            self.assertEqual(running[0], 1)
            entered.append(1)
            time.sleep(0.015)
            running[0] -= 1

        def task():
            barrier.wait()
            self.runtime.run(self.ref, op)

        threads = [threading.Thread(target=task) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(len(entered), 2)

    def test_active_reset_after_error(self):
        with self.assertRaisesRegex(RuntimeError, "failed"):
            self.runtime.run(self.ref, lambda _: (_ for _ in ()).throw(RuntimeError("failed")))
        self.assertFalse(self.runtime.status()["active_request"])


if __name__ == "__main__":
    unittest.main()
