import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .generation import (
    DEFAULT_MODEL,
    REASONING_EFFORT,
    GenerationError,
    catalog,
    generate,
    get_key,
)
from .schemas import GenerateRequest
from .security import LocalRequestGuard

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Прибор — студия карточек", version="0.1.0", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=ROOT / "app/static"), name="static")
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"]
)
app.add_middleware(LocalRequestGuard)


@app.exception_handler(RequestValidationError)
async def invalid_input(request: Request, error: RequestValidationError):
    details = [
        {"field": ".".join(map(str, item["loc"][1:])), "message": item["msg"]}
        for item in error.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"error": "Проверьте входные данные", "details": details},
    )


@app.exception_handler(GenerationError)
async def generation_failure(request: Request, error: GenerationError):
    return JSONResponse(
        status_code=error.status,
        content={"error": error.message, "details": error.details},
    )


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(ROOT / "app/static/index.html")


@app.get("/designs", include_in_schema=False)
async def designs():
    return RedirectResponse("/", status_code=307)


@app.get("/api/status")
async def status():
    return {
        "configured": bool(get_key()),
        "default_model": DEFAULT_MODEL,
        "reasoning_effort": REASONING_EFFORT,
    }


@app.get("/api/models")
async def models():
    return {
        "models": await catalog(),
        "default_model": DEFAULT_MODEL,
        "reasoning_effort": REASONING_EFFORT,
    }


@app.get("/api/examples")
async def examples():
    result = []
    for path in sorted((ROOT / "examples").glob("*.input.json")):
        record = {
            "id": path.stem.replace(".input", ""),
            "product": json.loads(path.read_text(encoding="utf8")),
        }
        output = path.with_name(path.name.replace(".input.json", ".output.json"))
        if output.exists():
            record["saved_result"] = json.loads(output.read_text(encoding="utf8"))
        result.append(record)
    return result


@app.post("/api/generate")
async def generate_card(payload: GenerateRequest):
    return await generate(payload.product, payload.model)
