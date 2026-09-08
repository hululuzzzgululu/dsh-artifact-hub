"""FastAPI application for the DSH Artifact Hub."""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.response import failure
from api.routers import shares
from artifact_hub.domain.errors import HubError
from artifact_hub.repositories.factory import create_artifact_repository
from artifact_hub.services.artifact_hub import ArtifactHub
from config.manager import ConfigManager


logger = logging.getLogger(__name__)


def create_app(hub: Optional[ArtifactHub] = None) -> FastAPI:
    settings = ConfigManager.from_env().config
    if hub is None:
        repository = create_artifact_repository(settings)
        hub_instance = ArtifactHub(
            repository=repository,
            artifact_root=settings.artifact_root,
            base_url=settings.base_url,
        )
    else:
        hub_instance = hub

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if app.state.owns_hub:
            app.state.hub.close()

    app = FastAPI(title="DSH Artifact Hub API", lifespan=lifespan)
    app.state.hub = hub_instance
    app.state.owns_hub = hub is None

    @app.exception_handler(HubError)
    async def hub_exception_handler(_request: Request, exc: HubError) -> JSONResponse:
        payload = failure(str(exc.status_code), exc.message, {"code": exc.code})
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(payload, by_alias=True),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        result_obj = None if isinstance(exc.detail, str) else exc.detail
        payload = failure(str(exc.status_code), message, result_obj)
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(payload, by_alias=True),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        payload = failure("422", "Request validation failed", exc.errors())
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(payload, by_alias=True),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception(
            "Unhandled API exception for %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        payload = failure("500", "Internal Server Error")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(payload, by_alias=True),
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(shares.router)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = ConfigManager.from_env().config
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
