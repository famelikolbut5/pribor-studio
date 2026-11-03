import unittest

from test_app import fixture

from app.validation import check_card


class EditorialRangeTests(unittest.TestCase):
    def test_description_ranges_use_words_instead_of_ellipsis(self):
        for value in ("0 ... +50 °C", "0…+50 °C", "-50 ... +50 °C"):
            with self.subTest(value=value):
                product, card = fixture()
                card.seo_description += " Рабочая температура " + value + "."
                self.assertTrue(
                    any(
                        "словами от и до" in error
                        for error in check_card(card, product)
                    )
                )

    def test_commercial_range_uses_words(self):
        product, card = fixture()
        card.commercial.tasks += " Измерения в диапазоне 0 ... 100 гПа."
        self.assertTrue(
            any("словами от и до" in error for error in check_card(card, product))
        )

    def test_prose_words_preserve_source_values_without_changing_specs(self):
        product, card = fixture()
        card.seo_description += " Рабочая температура от 0 до +50 °C."
        self.assertEqual(check_card(card, product), [])
        self.assertEqual(card.key_specs[0].value, product.specs[card.key_specs[0].name])
