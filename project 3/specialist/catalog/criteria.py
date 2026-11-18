"""Structured filters accepted by the public catalog tools."""

from decimal import Decimal

from pydantic import Field, model_validator

from specialist.contracts.validation import StrictSchema


class SearchCriteria(StrictSchema):
    """Customer filters for public Tunisianet product search."""

    name: str | None = Field(default=None, max_length=120)
    price_min_tnd: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    price_max_tnd: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    color: str | None = Field(default=None, max_length=80)
    weight_min_kg: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=3)
    weight_max_kg: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=3)
    characteristics: dict[str, str] = Field(default_factory=dict, max_length=10)

    @model_validator(mode="after")
    def validate_ranges_and_characteristics(self):
        if self.price_min_tnd is not None and self.price_max_tnd is not None and self.price_min_tnd > self.price_max_tnd:
            raise ValueError("Minimum price cannot exceed maximum price")
        if self.weight_min_kg is not None and self.weight_max_kg is not None and self.weight_min_kg > self.weight_max_kg:
            raise ValueError("Minimum weight cannot exceed maximum weight")
        if any(not key.strip() or not value.strip() or len(key) > 80 or len(value) > 120
               for key, value in self.characteristics.items()):
            raise ValueError("Characteristics require bounded non-empty names and values")
        return self
