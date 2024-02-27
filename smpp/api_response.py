from enum import Enum
from typing import Any

from pydantic import BaseModel


class ResponseStatus(str, Enum):
    success = "success"
    failed = "failed"


class APIError(BaseModel):
    type: str
    status_code: int
    message: str | dict[str, Any]

    def __init__(
        self,
        type: str,
        status_code: int | None,
        message: str | dict[str, Any] | None,
    ):
        if status_code is None:
            status_code = 666
        if not message:
            message = "Unknown error"
        return super().__init__(type=type, code=status_code, message=message)


class APIResponse(BaseModel):
    status: ResponseStatus
    status_code: int
    message: dict
