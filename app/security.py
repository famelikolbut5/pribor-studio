import json

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .json_input import DuplicateKeyError, load_unique_json

MAX_BODY_BYTES = 100_000
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'self'"
)


class LocalRequestGuard:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)

        async def secure_send(message: Message):
            if message["type"] == "http.response.start":
                output = MutableHeaders(scope=message)
                output["X-Content-Type-Options"] = "nosniff"
                output["Referrer-Policy"] = "no-referrer"
                output["X-Frame-Options"] = "SAMEORIGIN"

                if not scope["path"].startswith("/api/docs"):
                    output["Content-Security-Policy"] = CSP
                if scope["path"].startswith("/api/"):
                    output["Cache-Control"] = "no-store"
            await send(message)

        async def reject(status: int, text: str):
            await JSONResponse({"error": text}, status_code=status)(
                scope, receive, secure_send
            )

        if scope["method"] == "POST":
            origin = headers.get("origin")
            expected_origin = scope["scheme"] + "://" + headers.get("host", "")
            if origin is not None and origin != expected_origin:
                await reject(
                    403, "Запрос с другого сайта запрещён. Откройте локальный редактор."
                )
                return
            content_length = headers.get("content-length")
            if content_length is not None:
                if not content_length.isascii() or not content_length.isdecimal():
                    await reject(400, "Некорректная длина запроса.")
                    return
                normalized_length = content_length.lstrip("0") or "0"
                if (
                    len(normalized_length) > 6
                    or int(normalized_length) > MAX_BODY_BYTES
                ):
                    await reject(413, "Слишком большой запрос. Допускается до 100 КБ.")
                    return

            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > MAX_BODY_BYTES:
                    await reject(413, "Слишком большой запрос. Допускается до 100 КБ.")
                    return
                if not message.get("more_body", False):
                    break
            content_type = headers.get("content-type", "").split(";")[0].strip().lower()
            if (
                not content_type
                or content_type == "application/json"
                or content_type.endswith("+json")
            ):
                try:
                    load_unique_json(body)
                except DuplicateKeyError as error:
                    await reject(422, str(error))
                    return
                except (json.JSONDecodeError, UnicodeDecodeError):
                    await reject(
                        422, "Некорректный JSON. Проверьте кавычки, запятые и скобки."
                    )
                    return
                except RecursionError:
                    await reject(422, "Слишком глубокая вложенность JSON.")
                    return
            delivered = False

            async def replay_body():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            await self.app(scope, replay_body, secure_send)
            return
        await self.app(scope, receive, secure_send)
