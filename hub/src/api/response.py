"""Shared JSON response envelope for the FastAPI endpoints."""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Stable response envelope used by JSON API endpoints."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    result_code: str = Field(default="0", serialization_alias="resultCode")
    result_msg: str = Field(default="", serialization_alias="resultMsg")
    result_obj: Optional[T] = Field(default=None, serialization_alias="resultObj")


def success(result_obj: T) -> ApiResponse[T]:
    return ApiResponse(result_obj=result_obj)


def failure(result_code: str, result_msg: str, result_obj: Any = None) -> ApiResponse[Any]:
    return ApiResponse(
        result_code=result_code,
        result_msg=result_msg,
        result_obj=result_obj,
    )


__all__ = ["ApiResponse", "failure", "success"]


def send_bytes(handler, status, body, headers):
    handler.send_response(int(status))
    for name, value in headers.items():
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(body)


def send_json(handler, status, value):
    body = json.dumps(value, ensure_ascii=False).encode("utf-8")
    send_bytes(
        handler,
        status,
        body,
        {"Content-Type": "application/json; charset=utf-8", "Content-Length": str(len(body))},
    )


def send_error(handler, status, code, message):
    send_json(handler, status, {"error": {"code": code, "message": message}})
