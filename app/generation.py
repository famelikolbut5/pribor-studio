import asyncio
import os
import time
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv
from pydantic import ValidationError

from .prompt import messages_for
from .schemas import Card, Product
from .validation import check_card, markdown, parse_card

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
BASE_URL = os.getenv("LLM_BASE_URL", "https://limitdeckai.ru/v1").rstrip("/")
DEFAULT_MODEL = os.getenv("LLM_MODEL", "gpt-6.1-sol")
REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "high")
MAX_COMPLETION_TOKENS = 8192
MAX_ATTEMPTS = 2
MAX_CONCURRENT_REQUESTS = 3
REQUEST_TIMEOUT_SECONDS = 300
_gate = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)


class GenerationError(Exception):
    def __init__(
        self, message: str, status: int = 502, details: list[str] | None = None
    ):
        super().__init__(message)
        self.message = message
        self.status = status
        self.details = details or []


def get_key() -> str:
    return os.getenv("LLM_API_KEY", "").strip()


async def catalog() -> list[dict]:
    if not get_key():
        return []
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.get(
                BASE_URL + "/models", headers={"Authorization": "Bearer " + get_key()}
            )
            response.raise_for_status()
        rows = response.json()["data"]
        if not isinstance(rows, list):
            raise ValueError("Invalid catalogue envelope")
        result = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise ValueError("Invalid catalogue entry")
            if "image" not in row["id"]:
                result.append(
                    {
                        "id": row["id"],
                        "availability": row.get("availability", "unknown"),
                    }
                )
        return result
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, TypeError):
        raise GenerationError(
            "Не удалось получить каталог моделей. Проверьте подключение и ключ.", 503
        ) from None


def completion_from(response: httpx.Response) -> tuple[str, dict]:

    try:
        body = response.json()
        choice = body["choices"][0]
        message = choice["message"]
        content = message.get("content")
        usage = body.get("usage") or {}
        if not isinstance(message, dict) or not isinstance(usage, dict):
            raise TypeError
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise GenerationError(
            "API вернул некорректный ответ. Предыдущий черновик сохранён."
        ) from None
    if message.get("refusal") or choice.get("finish_reason") == "content_filter":
        raise GenerationError(
            "Модель отказалась формировать карточку. Проверьте исходные данные."
        )
    if choice.get("finish_reason") == "length":
        raise GenerationError(
            "Ответ модели обрезан по лимиту. Неполный черновик не выдан."
        )
    if not isinstance(content, str):
        raise GenerationError(
            "API не вернул текст карточки. Предыдущий черновик сохранён."
        )
    return content, usage


def provider_error(status: int) -> GenerationError:
    messages = {
        400: "API отклонил параметры или выбранную модель.",
        401: "Ключ API отклонён. Проверьте настройку на сервере.",
        402: "Недостаточно средств на балансе API.",
        403: "Провайдер запретил доступ к выбранной модели.",
        404: "Выбранная модель или адрес API не найдены.",
        429: "Превышен лимит запросов провайдера. Подождите и повторите.",
    }
    return GenerationError(
        messages.get(status, "Провайдер не смог выполнить генерацию. Повторите позже."),
        status if status in (400, 401, 402, 403, 404, 429) else 502,
    )


async def generate(product: Product, model: str) -> dict:
    if not get_key():
        raise GenerationError(
            "API-ключ не настроен. Укажите LLM_API_KEY на сервере.", 503
        )
    if _gate.locked():
        raise GenerationError(
            "Сервис уже выполняет три генерации. Дождитесь завершения одной из них.",
            429,
        )
    started = time.monotonic()
    feedback = None
    previous = None
    usage = {}
    async with _gate:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=15)
        ) as client:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                payload = {
                    "model": model,
                    "messages": messages_for(product, feedback, previous),
                    "max_tokens": MAX_COMPLETION_TOKENS,
                    "reasoning_effort": REASONING_EFFORT,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "product_card",
                            "strict": True,
                            "schema": Card.model_json_schema(),
                        },
                    },
                    "stream": False,
                }
                try:
                    async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                        response = await client.post(
                            BASE_URL + "/chat/completions",
                            json=payload,
                            headers={
                                "Authorization": "Bearer " + get_key(),
                                "Idempotency-Key": str(uuid.uuid4()),
                            },
                        )
                except (httpx.TimeoutException, TimeoutError):
                    raise GenerationError(
                        "Модель не ответила вовремя. Проверьте журнал провайдера перед повтором.",
                        504,
                    ) from None
                except (httpx.HTTPError, httpx.InvalidURL):
                    raise GenerationError(
                        "Не удалось связаться с API. Проверьте адрес API и сеть.",
                        503,
                    ) from None
                if response.status_code != 200:
                    raise provider_error(response.status_code)
                previous, attempt_usage = completion_from(response)
                for name, value in attempt_usage.items():
                    if type(value) is int and value >= 0:
                        usage[name] = usage.get(name, 0) + value
                try:
                    card = parse_card(previous)
                    feedback = check_card(card, product)
                except ValidationError as error:
                    feedback = [
                        ".".join(map(str, item["loc"])) + " " + item["msg"]
                        for item in error.errors()[:10]
                    ]
                except ValueError:
                    feedback = [
                        "Верни корректный JSON без обрамления Markdown и пояснений"
                    ]
                if not feedback:
                    return {
                        "card": card.model_dump(),
                        "markdown": markdown(card),
                        "checks": {
                            "title_chars": len(card.seo_title),
                            "description_chars": len(card.seo_description),
                            "search_query_count": len(card.search_queries),
                            "specs_match": True,
                            "semantic_review_required": True,
                        },
                        "meta": {
                            "model": model,
                            "reasoning_effort": REASONING_EFFORT,
                            "seconds": round(time.monotonic() - started, 2),
                            "attempts": attempt,
                            "usage": usage,
                        },
                    }
    raise GenerationError(
        "Ответ модели не прошёл проверку. Исходные данные и предыдущий черновик сохранены.",
        details=feedback,
    )
