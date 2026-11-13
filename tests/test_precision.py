import types
import unittest
from unittest.mock import patch

from enhanced_llm.precision import (
    MATRIX_PRECISION_MODES, is_native_four_bit_format, native_matrix_precision,
)


class FakeNativeMixedPrecisionOp:
    def __init__(self, fmt, dtype="torch.bfloat16", full=False, config=False):
        self.quant_format = fmt
        self.factory_kwargs = {"dtype": dtype}
        self._full_precision_mm = full
        self._full_precision_mm_config = config


class FakeStage:
    def __init__(self, layers):
        self.layers = layers

    def modules(self):
        return iter(self.layers)


class FakeClip:
    def __init__(self, layers):
        self.cond_stage_model = FakeStage(layers)


class TestW4A16Precision(unittest.TestCase):
    def test_format_detection_is_metadata_based(self):
        for fmt in ("nvfp4", "convrot_w4a4", "asym_w4a8_int8", "awq_w4a16", "custom_int4"):
            self.assertTrue(is_native_four_bit_format(fmt), fmt)
        for fmt in ("w6a8_int8", "int8_tensorwise", "float8_e4m3fn", None, "fp16"):
            self.assertFalse(is_native_four_bit_format(fmt), fmt)

    def test_native_mode_no_changes(self):
        clip = FakeClip([FakeNativeMixedPrecisionOp("nvfp4")])
        with native_matrix_precision(clip) as info:
            self.assertEqual(info["mode"], "native")
            self.assertFalse(clip.cond_stage_model.layers[0]._full_precision_mm)

    def test_selective_w4a16_and_restoration(self):
        bit4 = FakeNativeMixedPrecisionOp("asym_w4a8_int8")
        fp8 = FakeNativeMixedPrecisionOp("float8_e4m3fn")
        clip = FakeClip([bit4, fp8])
        # Isolate the native extension without importing torch/GPU in CI.
        fake_ops = types.SimpleNamespace(MixedPrecisionOp=FakeNativeMixedPrecisionOp)
        with patch("enhanced_llm.precision.import_module", return_value=fake_ops):
            with native_matrix_precision(clip, "w4a16") as info:
                self.assertTrue(bit4._full_precision_mm)
                self.assertTrue(bit4._full_precision_mm_config)
                self.assertFalse(fp8._full_precision_mm)
                self.assertEqual(info["w4a16_layers"], 1)
                self.assertEqual(info["activation_dtype"], "bfloat16")
            self.assertFalse(bit4._full_precision_mm)
            self.assertFalse(bit4._full_precision_mm_config)

    def test_restores_original_flags_on_error(self):
        bit4 = FakeNativeMixedPrecisionOp("nvfp4", full=True, config=False)
        with patch("enhanced_llm.precision.import_module",
                   return_value=types.SimpleNamespace(MixedPrecisionOp=FakeNativeMixedPrecisionOp)):
            with self.assertRaisesRegex(RuntimeError, "generation failed"):
                with native_matrix_precision(FakeClip([bit4]), "w4a16"):
                    raise RuntimeError("generation failed")
        self.assertTrue(bit4._full_precision_mm)
        self.assertFalse(bit4._full_precision_mm_config)

    def test_incompatible_model_rejected(self):
        with patch("enhanced_llm.precision.import_module",
                   return_value=types.SimpleNamespace(MixedPrecisionOp=FakeNativeMixedPrecisionOp)):
            with self.assertRaisesRegex(ValueError, "4-bit"):
                with native_matrix_precision(FakeClip([FakeNativeMixedPrecisionOp("float8_e4m3fn")]), "w4a16"):
                    pass

    def test_wrong_activation_dtype_rejected(self):
        layer = FakeNativeMixedPrecisionOp("nvfp4", dtype="torch.float32")
        with patch("enhanced_llm.precision.import_module",
                   return_value=types.SimpleNamespace(MixedPrecisionOp=FakeNativeMixedPrecisionOp)):
            with self.assertRaisesRegex(ValueError, "FP16/BF16"):
                with native_matrix_precision(FakeClip([layer]), "w4a16"):
                    pass

    def test_invalid_mode_rejected(self):
        self.assertEqual(MATRIX_PRECISION_MODES, ("native", "w4a16"))
        with self.assertRaisesRegex(ValueError, "Invalid matrix precision"):
            with native_matrix_precision(FakeClip([]), "unknown"):
                pass


if __name__ == "__main__":
    unittest.main()
