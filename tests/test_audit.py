import asyncio
import json
import unittest
from unittest.mock import patch

import httpx
from pydantic import ValidationError
from test_app import fixture

from app.generation import GenerationError, generate
from app.main import app
from app.schemas import Product
from app.validation import check_card, numbers, parse_card


class DataIntegrityTests(unittest.TestCase):
    def test_spec_names_cannot_conflict_only_by_case(self):
        with self.assertRaises(ValidationError):
            Product(name="A", specs={"Питание": "24 В", "питание": "220 В"})

    def test_changed_negative_value_is_not_an_existing_positive_value(self):
        product, card = fixture()
        card.seo_description += " Диапазон до -100 гПа."
        self.assertTrue(any("числа" in error for error in check_card(card, product)))

    def test_ranges_model_names_and_negative_measurements(self):
        self.assertEqual(
            numbers("0-100, 0–100, -50, −50, +300, DM-02"),
            {"0", "100", "-50", "300", "2"},
        )

    def test_model_json_cannot_repeat_fields(self):
        _, card = fixture()
        raw = card.model_dump_json()
        repeated = raw[:-1] + ',"seo_title":"Подмена"}'
        with self.assertRaises(ValueError):
            parse_card(repeated)


class IntakeAuditTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_duplicate_json_keys_never_reach_the_model(self):
        sources = [
            '{"model":"demo","product":{"name":"A","name":"B"}}',
            '{"model":"demo","product":{"name":"A","specs":{"x":"1","x":"2"}}}',
            r'{"model":"demo","product":{"name":"A","specs":{"x":"1","\u0078":"2"}}}',
        ]
        for source in sources:
            with self.subTest(source=source), patch("app.main.generate") as upstream:
                response = await self.client.post(
                    "/api/generate",
                    content=source.encode(),
                    headers={"Content-Type": "application/json"},
                )
                self.assertEqual(response.status_code, 422)
                upstream.assert_not_called()

    async def test_invalid_encoding_is_a_validation_error(self):
        response = await self.client.post(
            "/api/generate",
            content=b"\xff",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 422)

    async def test_excessive_json_nesting_does_not_crash(self):
        response = await self.client.post(
            "/api/generate",
            content="[" * 2000 + "0" + "]" * 2000,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 422)

    async def test_prototype_like_spec_names_are_plain_data(self):
        with patch("app.main.generate", return_value={"ok": True}) as upstream:
            response = await self.client.post(
                "/api/generate",
                content='{"model":"demo","product":{"name":"A","specs":{"__proto__":"text"}}}',
                headers={"Content-Type": "application/json"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(upstream.call_args.args[0].specs["__proto__"], "text")


class ProviderAuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_base_url_is_explained_without_retry(self):
        product, _ = fixture()
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(httpx.InvalidURL("bad URL"))
            )
        )
        with (
            patch("app.generation.get_key", return_value="test-key"),
            patch("app.generation.httpx.AsyncClient", return_value=client),
        ):
            with self.assertRaises(GenerationError) as error:
                await generate(product, "demo")
        self.assertEqual(error.exception.status, 503)

    async def test_total_deadline_is_enforced(self):
        product, _ = fixture()
        calls = []

        async def handler(request):
            calls.append(request)
            await asyncio.sleep(1)
            return httpx.Response(200, json={})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with (
            patch("app.generation.get_key", return_value="test-key"),
            patch("app.generation.REQUEST_TIMEOUT_SECONDS", 0.01),
            patch("app.generation.httpx.AsyncClient", return_value=client),
        ):
            with self.assertRaises(GenerationError) as error:
                await generate(product, "demo")
        self.assertEqual(error.exception.status, 504)
        self.assertEqual(len(calls), 1)

    async def test_invalid_usage_counters_do_not_break_a_valid_card(self):
        product, card = fixture()
        body = {
            "choices": [{"message": {"content": card.model_dump_json()}}],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": float("inf"),
                "other": 5.5,
                "negative": -1,
                "flag": True,
            },
        }
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    content=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"},
                )
            )
        )
        with (
            patch("app.generation.get_key", return_value="test-key"),
            patch("app.generation.httpx.AsyncClient", return_value=client),
        ):
            result = await generate(product, "demo")
        self.assertEqual(result["meta"]["usage"], {"prompt_tokens": 5})

    async def test_source_url_is_never_fetched(self):
        product, card = fixture()
        product.source_url = "http://169.254.169.254/latest/meta-data/"
        urls = []

        def handler(request):
            urls.append(str(request.url))
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": card.model_dump_json()}}]},
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with (
            patch("app.generation.get_key", return_value="test-key"),
            patch("app.generation.httpx.AsyncClient", return_value=client),
        ):
            await generate(product, "demo")
        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].endswith("/chat/completions"))
        self.assertNotIn("169.254.169.254", urls[0])
