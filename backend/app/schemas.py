from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Quantity = Annotated[int, Field(strict=True, ge=0, le=9999)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(StrictModel):
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=254)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class TemplateItem(StrictModel):
    name: Name
    unit: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
    required_qty: Quantity
    requires_expiry: bool


class TemplateInput(StrictModel):
    name: Name
    items: list[TemplateItem] = Field(min_length=1, max_length=50)


class KitInput(StrictModel):
    name: Name
    location: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    template_id: int = Field(strict=True, ge=1)
    interval_days: int = Field(strict=True, ge=1, le=365)


class Revision(StrictModel):
    expected_revision: int = Field(strict=True, ge=1)


class Cancel(Revision):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class Group(StrictModel):
    qty: int = Field(strict=True, ge=1, le=9999)
    expiry_state: Literal["KNOWN", "UNKNOWN"]
    input_value: str = Field(default="", max_length=20)
    unknown_reason: Literal["UNREADABLE", "NO_MARK", "AMBIGUOUS"] | None = None
    confirmed: bool = False
    month_end_confirmed: bool = False
    source: Literal["MANUAL", "OCR"] = "MANUAL"


class ItemInput(Revision):
    actual_qty: Quantity
    confirmed: bool
    groups: list[Group] = Field(default_factory=list, max_length=20)

    @field_validator("confirmed")
    @classmethod
    def check_confirmation(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Подтвердите количество")
        return value
