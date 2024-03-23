import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import json_logging
from fastapi import Body
from fastapi import Depends
from fastapi import FastAPI
from fastapi import Request
from fastapi import Response
from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from hypercorn.asyncio import serve
from hypercorn.config import Config
from starlette.exceptions import HTTPException

from settings import SmppSettings
from smpp.api_response import APIError
from smpp.api_response import APIResponse
from smpp.api_response import ResponseStatus
from smpp.api_response import Success
from smpp.esme import ESME
from utils.logger import logger


settings = SmppSettings()
esme = ESME(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup")
    esme.connect()
    
    yield

    esme.disconnect()
    logger.info("Shutdown")


def capture_body(request: Request):
    request.state.request_body = {}
    if request.method in ["POST", "PUT", "PATCH"]:
        request.state.request_body = request.json()


app = FastAPI(
    title="SMPP ESME",
    description="External Short Message Entity",
    swagger_ui_parameters={'defaultModelsExpandDepth': -1},
    docs_url='/smpp/docs',
    openapi_url='/smpp/openapi.json',
    version="0.0.1",
    redoc_url=None,
    lifespan=lifespan
)


json_logging.init_fastapi(enable_json=True)
json_logging.init_request_instrument(app)


@app.exception_handler(RequestValidationError)
def validation_exception_handler(_, exc: RequestValidationError):
    error_json = jsonable_encoder(exc.errors())
    return JSONResponse(content=error_json, status_code=422)


@app.exception_handler(HTTPException)
def http_exception_handler(_, exc: HTTPException):
    return JSONResponse(content=exc.detail, status_code=exc.status_code)


@app.get("/", include_in_schema=False, dependencies=[Depends(capture_body)])
def root():
    """Micro-service card identifier"""

    version: str = "unknown"
    try:
        if os.path.exists("version.txt"):
            with open("version.txt", "r") as version_file:
                version = version_file.read().strip()
    except Exception:
        pass

    return {
        "name": "SMPP ESME",
        "type": "microservice",
        "description": "SMPP Gatway",
        "status": "success",
        "version": version,
        "server": settings.servername,
    }


@app.post('/sms', response_model=APIResponse)
def send_sms(
    msisdn: str = Body(...),
    message: str = Body(...),
) -> APIResponse:
    logger.info(f"Send SMS to {msisdn}, message: {message}")

    response: dict[str, Any] = esme.send_message(msisdn, message)

    if response.get("status") == "failed":
        response: dict[str, Any] = esme.send_message(msisdn, message)
        if response.get("status") == "failed":
            raise HTTPException(
                status_code=response.get("code"),
                detail=response.get("message"),
            )

    return APIResponse(
        status=ResponseStatus.success,
        success=Success(code=response.get("code"), message=response.get("message")),
        data={"msisdn": msisdn, "message": message},
    )


@app.options("/{x:path}", include_in_schema=False)
def myoptions() -> Response:
    return Response(status_code=status.HTTP_200_OK)


@app.post('/{x:path}', include_in_schema=False, dependencies=[Depends(capture_body)])
def catch_all() -> APIError:
    return APIError(
        type="catchall",
        status_code=501,
        message=f"Requested method or path is invalid",
    )


if __name__ == "__main__":
    config = Config()
    config.bind = [f'{settings.listening_host}:{settings.listening_port}']
    config.accesslog = logger
    config.errorlog = logger
    config.logconfig = "./json_log.ini"
    
    asyncio.run(serve(app, config))