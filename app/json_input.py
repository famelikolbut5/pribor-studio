import json


class DuplicateKeyError(ValueError):
    pass


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise DuplicateKeyError(f"Поле «{name[:150]}» повторяется в JSON")
        result[name] = value
    return result


def load_unique_json(value: str | bytes | bytearray):
    return json.loads(value, object_pairs_hook=unique_object)
