from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from configuration.models import Settings


def get_settings() -> "Settings":
    from configuration.models import Settings
    return Settings.objects.get(id=1)
