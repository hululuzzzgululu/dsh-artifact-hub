"""Artifact share routes."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response, status

from api.deps import get_hub
from api.response import ApiResponse, success
from api.schemas import (
    LocalShareRequest,
    NasCommitRequest,
    NasPrepareRequest,
    PreparedUploadResponse,
    PublicShareResponse,
    RevokeShareRequest,
    ShareList,
    ShareResponse,
)
from artifact_hub.domain.errors import AccessRestrictedError
from artifact_hub.services.artifact_hub import ArtifactHub


router = APIRouter(tags=["shares"])


def _public_share_values(info) -> dict:
    return {
        "version": info.version,
        "name": info.name,
        "mime_type": info.mime_type,
        "size": info.size,
        "visibility": info.visibility,
        "permission": info.permission,
        "created_by_id": info.created_by_id,
        "created_by_name": info.created_by_name,
        "expires_at": info.expires_at,
        "created_at": info.created_at,
    }


def _content_disposition(disposition: str, name: str) -> str:
    fallback = "".join(
        character
        for character in name
        if ord(character) < 128 and ord(character) >= 32 and character not in {'"', "\\"}
    ).strip()
    if not fallback or fallback.startswith("."):
        fallback = "artifact" + fallback
    return "{}; filename=\"{}\"; filename*=UTF-8''{}".format(
        disposition,
        fallback,
        quote(name, safe=""),
    )


def _public_content_headers(name: str, mime_type: str, disposition: str) -> dict:
    headers = {
        "Cache-Control": "private, no-store",
        "Content-Disposition": _content_disposition(disposition, name),
        "Cross-Origin-Resource-Policy": "same-origin",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
    }
    if mime_type.split(";", 1)[0].lower() == "text/html":
        headers["Content-Security-Policy"] = (
            "sandbox allow-scripts; default-src 'none'; "
            "script-src 'unsafe-inline' 'unsafe-eval' blob:; "
            "style-src 'unsafe-inline'; img-src data: blob:; "
            "font-src data:; media-src data: blob:; connect-src 'none'"
        )
    return headers


@router.get("/healthz", response_model=ApiResponse[dict])
async def health() -> ApiResponse[dict]:
    return success({"status": "ok"})


@router.post(
    "/api/shares",
    response_model=ApiResponse[ShareResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_local_share(
    request: LocalShareRequest,
    hub: ArtifactHub = Depends(get_hub),
) -> ApiResponse[ShareResponse]:
    result = hub.create_local_share(**request.model_dump())
    return success(result.to_dict())


@router.post(
    "/api/shares/prepare",
    response_model=ApiResponse[PreparedUploadResponse],
    status_code=status.HTTP_201_CREATED,
)
async def prepare_nas_share(
    request: NasPrepareRequest,
    hub: ArtifactHub = Depends(get_hub),
) -> ApiResponse[PreparedUploadResponse]:
    result = hub.prepare_nas_share(**request.model_dump())
    return success(result.to_dict())


@router.post(
    "/api/shares/commit",
    response_model=ApiResponse[ShareResponse],
    status_code=status.HTTP_201_CREATED,
)
async def commit_nas_share(
    request: NasCommitRequest,
    hub: ArtifactHub = Depends(get_hub),
) -> ApiResponse[ShareResponse]:
    result = hub.commit_nas_share(**request.model_dump())
    return success(result.to_dict())


@router.get("/api/shares", response_model=ApiResponse[ShareList])
async def list_created_shares(
    created_by_id: str = Query(min_length=1, max_length=128),
    hub: ArtifactHub = Depends(get_hub),
) -> ApiResponse[ShareList]:
    return success(
        {"items": [item.to_dict() for item in hub.list_created_shares(created_by_id)]}
    )


@router.post("/api/shares/revoke", response_model=ApiResponse[dict])
async def revoke_share(
    request: RevokeShareRequest,
    hub: ArtifactHub = Depends(get_hub),
) -> ApiResponse[dict]:
    hub.revoke_share(token=request.token, revoked_by_id=request.revoked_by_id)
    return success({"status": "revoked"})


@router.get("/s/{token}", response_model=ApiResponse[ShareResponse])
async def resolve_share(
    token: str,
    hub: ArtifactHub = Depends(get_hub),
) -> ApiResponse[ShareResponse]:
    result = hub.resolve_share(token)
    return success(result.to_dict())


@router.get("/s/{token}/content")
async def read_share_content(
    token: str,
    hub: ArtifactHub = Depends(get_hub),
) -> Response:
    content = hub.read_share_content(token)
    return Response(
        content=content.body,
        media_type=content.mime_type,
        headers={
            "Content-Disposition": _content_disposition("attachment", content.name),
        },
    )


@router.get(
    "/api/public/shares/{token}",
    response_model=ApiResponse[PublicShareResponse],
)
async def resolve_public_share(
    token: str,
    response: Response,
    hub: ArtifactHub = Depends(get_hub),
) -> ApiResponse[PublicShareResponse]:
    info = hub.resolve_share(token)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return success(_public_share_values(info))


@router.get("/api/public/shares/{token}/content")
async def preview_public_share_content(
    token: str,
    hub: ArtifactHub = Depends(get_hub),
) -> Response:
    content = hub.read_share_content(token)
    return Response(
        content=content.body,
        media_type=content.mime_type,
        headers=_public_content_headers(content.name, content.mime_type, "inline"),
    )


@router.get("/api/public/shares/{token}/download")
async def download_public_share_content(
    token: str,
    hub: ArtifactHub = Depends(get_hub),
) -> Response:
    content = hub.read_share_content(token)
    if content.permission != "VIEW_DOWNLOAD":
        raise AccessRestrictedError("share does not allow downloads")
    return Response(
        content=content.body,
        media_type=content.mime_type,
        headers=_public_content_headers(content.name, content.mime_type, "attachment"),
    )
