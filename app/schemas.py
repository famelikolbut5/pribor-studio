from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=250)
    manufacturer: str = Field(default="", max_length=150)
    specs: dict[str, str | None] = Field(default_factory=dict)
    description: str = Field(default="", max_length=20000)
    source_url: str = Field(default="", max_length=2000)

    @field_validator("specs", mode="before")
    @classmethod
    def bounded_specs(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Характеристики должны быть JSON-объектом")
        if len(value) > 60:
            raise ValueError("Допускается не более 60 характеристик")
        result = {}
        for name, text in value.items():
            if not isinstance(name, str) or not name.strip() or len(name) > 150:
                raise ValueError(
                    "Название характеристики должно содержать 1–150 символов"
                )
            if text is not None and not isinstance(text, str):
                raise ValueError("Значение характеристики должно быть строкой или null")
            if text is not None and len(text) > 2000:
                raise ValueError("Значение характеристики длиннее 2000 символов")
            if any(
                existing.casefold() == name.strip().casefold() for existing in result
            ):
                raise ValueError("Повторяется характеристика «" + name.strip() + "»")
            result[name.strip()] = text.strip() if text else None
        return result


class KeySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    value: str


class Commercial(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audience: str
    tasks: str


class Card(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["draft", "needs_data"]
    seo_title: str
    seo_description: str
    key_specs: list[KeySpec]
    search_queries: list[str]
    commercial: Commercial
    missing_data: list[str]
    warnings: list[str]


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product: Product
    model: str = Field(min_length=1, max_length=120)
