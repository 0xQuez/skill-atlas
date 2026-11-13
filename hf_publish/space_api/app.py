"""Gradio / ZeroGPU entry for the Skill Atlas API.

Hugging Face free accounts cannot create Docker Spaces. This file satisfies
the Gradio + ZeroGPU startup check, then attaches the real JSON and MCP
routes to Gradio's FastAPI app. SSR is disabled so those routes reach Python.
No Hugging Face token is required; data is baked into ./data.
"""
import os

import gradio as gr
import spaces

import entrypoint

entrypoint.apply_env(entrypoint.ensure_data())

import atlas_server  # noqa: E402  (DuckDB opens files at import)

print(
    f"atlas prod={atlas_server._prod} rate={atlas_server._rate} "
    f"host={atlas_server._host} allowed={atlas_server._allowed_hosts}",
    flush=True,
)



@spaces.GPU
def _zerogpu_platform_check():
    # Never called. ZeroGPU requires at least one @spaces.GPU function at
    # startup; the decorator only allocates a GPU if the function runs.
    return None


def _search(query: str, verdict: str, white_hat: str, limit: int) -> str:
    import json
    v = None if verdict in ("", "any") else verdict
    result = atlas_server.search(query, v, None, int(limit), white_hat or "include")
    slim = []
    for row in result.get("results", [])[: int(limit)]:
        slim.append({
            "skill_id": row.get("skill_id"),
            "name": row.get("name"),
            "verdict": row.get("verdict"),
            "repo": row.get("repo"),
            "github_url": row.get("github_url"),
            "white_hat": row.get("white_hat"),
        })
    return json.dumps({"count": result.get("count"), "results": slim}, indent=2)


with gr.Blocks(title="Skill Atlas API") as demo:
    gr.Markdown(
        """
# Skill Atlas API

Read-only search and verdicts for about 1.9 million public agent skills (`SKILL.md` files).
Built on [GitSkills](https://huggingface.co/datasets/mvaccargiu/gitskills) (Destefanis et al., arXiv 2608.10906), CC BY 4.0.

**HTTP:** `/healthz` · `/stats` · `/skills/search?q=` · `/skills/{id}/verdict` · `/skills/{id}/canonical`

**MCP (streamable HTTP):** `/mcp` — tools `search_skills`, `get_skill_verdict`, `find_canonical`
        """
    )
    with gr.Row():
        query = gr.Textbox(label="Search", value="terraform module")
        verdict = gr.Dropdown(["any", "use", "caution", "ignore"], value="use", label="Verdict")
        white_hat = gr.Dropdown(["include", "exclude", "only"], value="include", label="White-hat tools")
        limit = gr.Slider(1, 20, value=5, step=1, label="Limit")
    out = gr.Code(label="Results", language="json")
    query.submit(_search, [query, verdict, white_hat, limit], out)
    gr.Button("Search").click(_search, [query, verdict, white_hat, limit], out)


def _attach_atlas_routes(fastapi_app):
    """Put Skill Atlas routes first so they are not swallowed by Gradio."""
    from contextlib import asynccontextmanager
    from starlette.middleware.cors import CORSMiddleware

    ours = list(atlas_server.app.router.routes)
    fastapi_app.router.routes = ours + list(fastapi_app.router.routes)
    # Re-apply production middleware (Starlette middleware is not copied with routes).
    origins = atlas_server._origins or ["*"]
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if origins == ["*"] else origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        max_age=3600,
    )
    if atlas_server._prod:
        host_list = []
        for h in atlas_server._allowed_hosts:
            host_list += [h, f"{h}:*"] if not h.endswith(":*") else [h]
        fastapi_app.add_middleware(atlas_server.HostCheckMiddleware, allowed=host_list)
    rate = atlas_server._rate
    if rate <= 0 and (atlas_server._prod or os.environ.get("RATE_LIMIT_PER_MIN")):
        rate = int(os.environ.get("RATE_LIMIT_PER_MIN") or "60")
    if rate > 0:
        # add_middleware raises if the stack is already built; force a rebuild in that case.
        try:
            fastapi_app.add_middleware(atlas_server.RateLimitMiddleware, per_min=rate)
        except RuntimeError:
            from starlette.middleware import Middleware
            fastapi_app.user_middleware.insert(0, Middleware(atlas_server.RateLimitMiddleware, per_min=rate))
            fastapi_app.middleware_stack = fastapi_app.build_middleware_stack()
        print(f"rate limit middleware attached: {rate}/min", flush=True)

    # Streamable HTTP MCP needs session_manager.run() on the same event loop.
    # Copying routes does not take the MCP app's lifespan with them.
    sm = getattr(atlas_server.mcp, "session_manager", None)
    if sm is not None and not getattr(fastapi_app, "_atlas_mcp_lifespan", False):
        prev = getattr(fastapi_app.router, "lifespan_context", None)

        @asynccontextmanager
        async def lifespan(app):
            async with sm.run():
                print("MCP session manager started", flush=True)
                if prev is not None:
                    ctx = prev(app)
                    if hasattr(ctx, "__aenter__"):
                        async with ctx:
                            yield
                    else:
                        yield
                else:
                    yield

        fastapi_app.router.lifespan_context = lifespan
        fastapi_app._atlas_mcp_lifespan = True
    return fastapi_app


try:
    from gradio.routes import App
    _orig_create = App.create_app

    def _create_app(*args, **kwargs):
        fastapi_app = _orig_create(*args, **kwargs)
        return _attach_atlas_routes(fastapi_app)

    App.create_app = _create_app
except Exception as exc:  # pragma: no cover
    print("warning: could not patch Gradio App.create_app:", exc, flush=True)


def _force_rate_limit(app, per_min: int) -> None:
    """Wrap the already-built ASGI stack so the limiter stays in the request path.

    Gradio may rebuild or wrap the FastAPI app after create_app returns, which
    can drop middleware added there. Mutating middleware_stack on the live
    object is visible to the running server.
    """
    if app is None or per_min <= 0:
        return
    existing = app.middleware_stack or app.build_middleware_stack()
    # Avoid wrapping twice if we are called again.
    if isinstance(existing, atlas_server.RateLimitMiddleware) and existing.per_min == per_min:
        return
    app.middleware_stack = atlas_server.RateLimitMiddleware(existing, per_min=per_min)
    print(f"rate limit forced on live middleware stack: {per_min}/min", flush=True)


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", "7860")),
        prevent_thread_lock=True,
        ssr_mode=False,
    )
    # Belt and suspenders if the create_app patch did not run.
    if getattr(demo, "app", None) is not None:
        paths = {getattr(r, "path", None) for r in demo.app.router.routes}
        if "/healthz" not in paths and "/skills/search" not in paths:
            try:
                _attach_atlas_routes(demo.app)
            except Exception as exc:
                print("post-launch route attach failed:", exc, flush=True)
        rate = atlas_server._rate or int(os.environ.get("RATE_LIMIT_PER_MIN") or "60")
        try:
            _force_rate_limit(demo.app, rate)
        except Exception as exc:
            print("force rate limit failed:", exc, flush=True)
    demo.block_thread()
