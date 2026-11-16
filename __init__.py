"""Enhanced LLM - native ComfyUI text generation with prompt sets."""
from comfy_api.latest import ComfyExtension, io
from typing_extensions import override

from .nodes import EnhancedGenerateText
from .queue_service import register_routes

WEB_DIRECTORY = "./web"
register_routes()


class EnhancedLLMExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [EnhancedGenerateText]


async def comfy_entrypoint() -> EnhancedLLMExtension:
    return EnhancedLLMExtension()
