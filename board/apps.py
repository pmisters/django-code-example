from django.apps import AppConfig


class BoardAppConfig(AppConfig):
    name = "board"

    def ready(self) -> None:
        # Register event handlers
        import board.handlers  # noqa
