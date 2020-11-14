from decimal import Decimal

from django.db import models

from common.db import TimeableModel


class ReservationDay(TimeableModel):
    reservation_room = models.ForeignKey("board.ReservationRoom", on_delete=models.CASCADE, related_name="day_prices")
    day = models.DateField()
    roomtype_id = models.PositiveIntegerField(blank=True, null=True)
    room = models.ForeignKey("houses.Room", on_delete=models.SET_NULL, blank=True, null=True)

    price_original = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_changed = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_accepted = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    currency = models.CharField(max_length=3, blank=True, null=True)

    class Meta:
        app_label = "board"
        ordering = ["day"]

    def __str__(self) -> str:
        return f"DAY={self.day.strftime('%Y-%m-%d')}"

    def save(self, **kwargs) -> None:
        for name in ("price_original", "price_changed", "price_accepted", "tax"):
            if getattr(self, name) is None:
                setattr(self, name, Decimal(0))
        if "update_fields" in kwargs and kwargs["update_fields"]:
            kwargs["update_fields"].append("updated_at")
        super().save(**kwargs)
