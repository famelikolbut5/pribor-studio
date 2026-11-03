import unittest

from test_app import fixture

from app.schemas import KeySpec, Product
from app.validation import check_card


def passport_card():
    _, card = fixture()
    product = Product(
        name="Манометр",
        description="Диапазон 0 ... 100 гПа. Степень защиты IP40. Питание 24 В. Ресурс 50 ч (в среднем).",
    )
    card.seo_title = product.name
    card.search_queries = [
        "манометр характеристики",
        "манометр диапазон",
        "манометр давление",
    ]
    card.key_specs = [
        KeySpec(name="диапазон измерений", value="0 ... 100 гПа"),
        KeySpec(name="степень защиты", value="IP40"),
        KeySpec(name="питание", value="24 В"),
        KeySpec(name="поверка", value="данных нет"),
    ]
    return product, card


class PassportTests(unittest.TestCase):
    def test_exact_values_can_be_extracted_from_description(self):
        product, card = passport_card()
        self.assertEqual(check_card(card, product), [])

    def test_empty_structured_field_can_use_a_passport_value(self):
        product, card = passport_card()
        product.specs = {"питание": None}
        self.assertEqual(check_card(card, product), [])

    def test_extracted_value_must_be_a_literal_source_fragment(self):
        product, card = passport_card()
        card.key_specs[0].value = "0–100 гПа"
        self.assertTrue(any("дословно" in error for error in check_card(card, product)))

    def test_an_existing_spec_cannot_be_replaced_by_a_passport_value(self):
        product, card = passport_card()
        product.specs = {"питание": "12 В"}
        self.assertTrue(any("исходной" in error for error in check_card(card, product)))

    def test_extracted_average_cannot_become_a_limit_in_prose(self):
        product, card = passport_card()
        card.key_specs.append(KeySpec(name="ресурс", value="50 ч (в среднем)"))
        card.seo_description += " Ресурс до 50 ч."
        self.assertTrue(
            any("Средний ресурс" in error for error in check_card(card, product))
        )
