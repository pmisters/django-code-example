from django.db import models


class TimeableModel(models.Model):
    """Model Class with timestamp for create and update events"""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UpdatableMixin:
    """
    Mixin for adding :func:`update()` with a list of allowed fields
    Class **must** contain subclass :class:`UpdateMeta` with
    :attr:`allowed_fields`

    """

    def update(self, **kwargs):
        """Update current instance with editable fields checking."""
        is_changed = False
        for name, value in kwargs.items():
            if name not in self.UpdateMeta.allowed_fields:
                raise AssertionError(f"Field {name} is not updatable")
            if getattr(self, name) != value:
                setattr(self, name, value)
                is_changed = True
        if is_changed:
            self.save()
        return is_changed
