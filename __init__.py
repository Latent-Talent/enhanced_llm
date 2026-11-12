"""Enhanced LLM native ComfyUI custom-node entry point.

The actual implementation lives in the internal package so the core can be
unit tested without loading ComfyUI or initializing the CUDA runtime.
"""

from .enhanced_llm.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

# Frontend controls are part of this custom-node package.
WEB_DIRECTORY = "./web"

from .enhanced_llm.http import register_routes
register_routes()
