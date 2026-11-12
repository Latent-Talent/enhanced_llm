"""Enhanced LLM native ComfyUI custom-node entry point.

The actual implementation lives in the internal package so the core can be
unit tested without loading ComfyUI or initializing the CUDA runtime.
"""

from .enhanced_llm.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
