from fastapi import FastAPI, Request
from fastapi.responses import Response
from opds_bridge.api.router import router as opds_router
from opds_bridge.api.acquire import router as acquire_router

def create_app() -> FastAPI:
    app = FastAPI(title="Audiobookshelf OPDS Bridge")

    @app.middleware("http")
    async def handle_head(request: Request, call_next):
        if request.method == "HEAD":
            request.scope["method"] = "GET"
            response = await call_next(request)
            headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
            return Response(status_code=response.status_code, headers=headers)
        return await call_next(request)

    app.include_router(opds_router)
    app.include_router(acquire_router)
    return app

app = create_app()
