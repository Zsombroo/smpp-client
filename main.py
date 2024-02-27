import asyncio
import os
from contextlib import asynccontextmanager
from typing import Annotated 

import json_logging
from fastapi import Body
from fastapi import Depends
from fastapi import FastAPI
from fastapi import Request
from fastapi import status
from fastapi import Response
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


async def capture_body(request: Request):
    request.state.request_body = {}
    if request.method in ["POST", "PUT", "PATCH"]:
        request.state.request_body = await request.json()


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
async def validation_exception_handler(_, exc: RequestValidationError):
    error_json = jsonable_encoder(exc.errors())
    return JSONResponse(content=error_json, status_code=422)


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException):
    return JSONResponse(content=exc.detail, status_code=exc.status_code)


@app.get("/", include_in_schema=False, dependencies=[Depends(capture_body)])
async def root():
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


@app.post('/sms')
async def send_sms(
    msisdn: str = Annotated[str, Body(example="79161234567")],
    message: str = Annotated[str, Body(example="Hello, world!")],
) -> APIResponse:
    logger.info(f"Send SMS to {msisdn}, message: {message}")

    success: bool = await esme.send_message(msisdn, message)

    if success:
        status = ResponseStatus.success
        status_code = 200
    else:
        status = ResponseStatus.failed
        status_code = 500

    return APIResponse(
        status=status,
        status_code=status_code,
        message={"msisdn": msisdn, "message": message},
    )


@app.options("/{x:path}", include_in_schema=False)
async def myoptions() -> Response:
    return Response(status_code=status.HTTP_200_OK)


@app.post('/{x:path}', include_in_schema=False, dependencies=[Depends(capture_body)])
async def catch_all() -> APIError:
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