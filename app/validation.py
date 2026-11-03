import json
import re

from .json_input import load_unique_json
from .schemas import Card, Product

UNKNOWN = "данных нет"
REQUIRED_UNKNOWNS = ("степень защиты", "поверка")


def needs_short_clarification(card: Card, product: Product) -> bool:
    return (
        card.status == "needs_data"
        and not product.description.strip()
        and sum(bool(value) for value in product.specs.values()) <= 2
    )


def editorial_errors(card: Card, product: Product) -> list[str]:

    fields = [
        card.seo_title,
        card.seo_description,
        *card.search_queries,
        card.commercial.audience,
        card.commercial.tasks,
        *card.missing_data,
        *card.warnings,
    ]
    prose = "\n".join(fields)

    for value in sorted(filter(None, product.specs.values()), key=len, reverse=True):
        prose = prose.replace(value, "")
    prose = re.sub(r"(?<=\d)\s*[–—]\s*(?=[+−-]?\d)", "", prose)
    errors = []
    if ":" in prose or "—" in prose or "–" in prose:
        errors.append(
            "Авторский текст не должен содержать двоеточия или длинные тире. Технические значения сохрани дословно"
        )
    range_prose = " ".join(
        [card.seo_description, card.commercial.audience, card.commercial.tasks]
    )
    if re.search(r"\d\s*(?:\.{3}|…)\s*[+−-]?\d", range_prose):
        errors.append(
            "В описании и блоке менеджера запиши числовые диапазоны словами от и до, сохранив границы, знаки, единицы и условия. В key_specs оставь исходную запись"
        )
    if not needs_short_clarification(card, product):
        paragraphs = [
            part.strip()
            for part in re.split(r"\n\s*\n", card.seo_description)
            if part.strip()
        ]
        if len(paragraphs) != 3:
            errors.append(
                "Описание должно состоять из трёх содержательных абзацев, разделённых двумя переводами строки"
            )
    return errors


def parse_card(text: str) -> Card:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value)
    return Card.model_validate(load_unique_json(value))


def numbers(text: str) -> set[str]:
    result = set()
    for match in re.finditer(r"[-−]?\d+(?:[.,]\d+)?", text):
        value = match.group()
        signed = value[0] in "-−"
        previous = text[match.start() - 1] if match.start() else ""
        negative = signed and not previous.isalnum()
        digits = value[1:] if signed else value
        normalized = digits.replace(",", ".").lstrip("0") or "0"
        result.add("-" + normalized if negative and normalized != "0" else normalized)
    return result


def check_card(card: Card, product: Product) -> list[str]:
    errors = []
    if not card.seo_title.strip() or not 1 <= len(card.seo_title) <= 70:
        errors.append(f"SEO-заголовок: {len(card.seo_title)} символов, нужно 1–70")
    if (
        not needs_short_clarification(card, product)
        and not 800 <= len(card.seo_description) <= 1200
    ):
        errors.append(f"Описание: {len(card.seo_description)} символов, нужно 800–1200")
    if not 3 <= len(card.search_queries) <= 5 or len(
        {query.strip().casefold() for query in card.search_queries}
    ) != len(card.search_queries):
        errors.append("Нужно 3–5 разных поисковых запросов")
    if not card.commercial.audience.strip() or not card.commercial.tasks.strip():
        errors.append("Заполните оба поля блока для менеджера")
    if any(not query.strip() for query in card.search_queries):
        errors.append("Поисковые запросы не должны быть пустыми")
    specs = {row.name: row.value for row in card.key_specs}
    folded_specs = {row.name.casefold(): row.value for row in card.key_specs}
    if len(folded_specs) != len(card.key_specs):
        errors.append("Повторяющиеся характеристики")
    for name, value in product.specs.items():
        actual = specs.get(name)
        valid = (
            actual == value
            if value
            else actual == UNKNOWN or bool(actual and actual in product.description)
        )
        if not valid:
            errors.append(
                f"Характеристика «{name}» должна дословно совпадать с исходной"
            )
    source_names = {name.casefold() for name in product.specs}
    for name in REQUIRED_UNKNOWNS:
        actual = folded_specs.get(name)
        if (
            name not in source_names
            and actual != UNKNOWN
            and not (actual and actual in product.description)
        ):
            errors.append(
                f"Для «{name}» укажи точную цитату из description или «{UNKNOWN}»"
            )
    for name, value in specs.items():
        if not name.strip() or not value.strip():
            errors.append("Название и значение характеристики не должны быть пустыми")
        if name not in product.specs and name.casefold() in source_names:
            errors.append(
                f"Дублируется исходная характеристика «{name}» с другим регистром"
            )
        if (
            name not in product.specs
            and value != UNKNOWN
            and value not in product.description
        ):
            errors.append(
                f"Значение «{name}» должно дословно присутствовать в description либо быть пометкой «данных нет»"
            )
    source = json.dumps(product.model_dump(exclude={"source_url"}), ensure_ascii=False)
    prose = " ".join(
        [
            card.seo_title,
            card.seo_description,
            *card.search_queries,
            card.commercial.audience,
            card.commercial.tasks,
        ]
    )
    novel = numbers(prose) - numbers(source)
    if novel:
        errors.append(
            "В тексте обнаружены числа вне исходных данных: " + ", ".join(sorted(novel))
        )
    unit_pattern = (
        r"\d\s*(МПа|кПа|гПа|Па|мбар|бар|м/с|мА|мВ|В|Гц|мм|см|ч|°[CС])(?=$|[^\w])"
    )
    source_units = {unit.replace("С", "C") for unit in re.findall(unit_pattern, source)}
    prose_units = {unit.replace("С", "C") for unit in re.findall(unit_pattern, prose)}
    if prose_units - source_units:
        errors.append(
            "В тексте появились единицы вне исходных данных: "
            + ", ".join(sorted(prose_units - source_units))
        )
    source_values = [
        *product.specs.values(),
        *(spec.value for spec in card.key_specs if spec.value in product.description),
    ]
    for value in source_values:
        if value and "в среднем" in value.lower():
            first_number = re.search(r"\d+(?:[.,]\d+)?", value)
            if first_number and re.search(
                r"(?:до|не более|не менее)\s+"
                + re.escape(first_number.group())
                + r"\s*(?:ч|час)",
                prose,
                re.IGNORECASE,
            ):
                errors.append(
                    "Средний ресурс нельзя заменять верхним или нижним пределом"
                )
    if not product.specs and not product.description and card.status != "needs_data":
        errors.append(
            "При отсутствии характеристик и назначения требуется status=needs_data"
        )
    if (
        any(
            not value and specs.get(name) == UNKNOWN
            for name, value in product.specs.items()
        )
        and not card.missing_data
    ):
        errors.append("Не указаны пустые характеристики в missing_data")
    return errors + editorial_errors(card, product)


def markdown(card: Card) -> str:
    lines = [
        f"# {card.seo_title}",
        "",
        card.seo_description,
        "",
        "## Характеристики",
        "",
    ]
    for row in card.key_specs:
        lines += [f"**{row.name}**", "", row.value, ""]
    lines += ["", "## Поисковые запросы", ""] + [
        f"- {query}" for query in card.search_queries
    ]
    lines += [
        "",
        "## Для менеджера",
        "",
        "### Кому подходит",
        "",
        card.commercial.audience,
        "",
        "### Какие задачи решает",
        "",
        card.commercial.tasks,
    ]
    if card.missing_data:
        lines += ["", "## Уточнить", ""] + [f"- {item}" for item in card.missing_data]
    if card.warnings:
        lines += ["", "## Предупреждения", ""] + [f"- {item}" for item in card.warnings]
    return "\n".join(lines)
