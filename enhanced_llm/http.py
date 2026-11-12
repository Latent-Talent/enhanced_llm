"""ComfyUI HTTP routes for user-owned enhancer templates and prompt sets.

Native inference is never initiated by these routes: all GPU generation runs
through ComfyUI's normal queue so connected model/media dependencies resolve.
"""

from __future__ import annotations

from . import enhancer_storage as storage


def register_routes() -> bool:
    try:
        from aiohttp import web
        from server import PromptServer
    except ModuleNotFoundError:
        # Isolated Python unit tests run without starting ComfyUI.
        return False

    routes = PromptServer.instance.routes

    async def json_body(request):
        if request.content_length is not None and request.content_length > 2_000_000:
            raise web.HTTPRequestEntityTooLarge(max_size=2_000_000, actual_size=request.content_length)
        try:
            payload = await request.json()
        except (ValueError, TypeError) as exc:
            raise web.HTTPBadRequest(text=f"Invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise web.HTTPBadRequest(text="Request body must be a JSON object")
        return payload

    async def guard(coro):
        try:
            return web.json_response(await coro())
        except (ValueError, TypeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except FileNotFoundError:
            return web.json_response({"error": "Item not found"}, status=404)
        except FileExistsError:
            return web.json_response({"error": "Item already exists"}, status=409)

    @routes.get("/enhanced_llm/enhancer/templates")
    async def get_templates(request):
        return await guard(lambda: _as_async({"templates": storage.templates()}))

    @routes.post("/enhanced_llm/enhancer/templates/save")
    async def post_save_template(request):
        payload = await json_body(request)
        return await guard(lambda: _as_async(
            storage.save_template(payload.get("name"), payload.get("instructions"))
        ))

    @routes.post("/enhanced_llm/enhancer/templates/delete")
    async def post_delete_template(request):
        payload = await json_body(request)
        def remove():
            storage.remove_template(payload.get("label"))
            return {"ok": True}
        return await guard(lambda: _as_async(remove()))

    @routes.get("/enhanced_llm/enhancer/sets")
    async def get_sets(request):
        return await guard(lambda: _as_async({"prompt_sets": storage.prompt_sets()}))

    @routes.post("/enhanced_llm/enhancer/sets/save")
    async def post_save_set(request):
        payload = await json_body(request)
        return await guard(lambda: _as_async(storage.save_prompt_set(
            payload.get("name"), payload.get("prompts"), payload.get("active_index", 0)
        )))

    @routes.post("/enhanced_llm/enhancer/sets/load")
    async def post_load_set(request):
        payload = await json_body(request)
        return await guard(lambda: _as_async(storage.load_prompt_set(payload.get("name"))))

    @routes.post("/enhanced_llm/enhancer/sets/delete")
    async def post_delete_set(request):
        payload = await json_body(request)
        def remove():
            storage.remove_prompt_set(payload.get("name"))
            return {"ok": True}
        return await guard(lambda: _as_async(remove()))

    return True


async def _as_async(value):
    return value
