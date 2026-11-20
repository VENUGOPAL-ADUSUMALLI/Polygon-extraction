"""
Pluggable test-case storage.

Usage:
    from problems.storage import get_storage
    storage = get_storage()
    storage.delete_problem_files(problem_id)
    storage.upload_test_case(problem_id, 1, input_data, output_data)

The provider is chosen by settings.STORAGE_PROVIDER. To add a provider,
implement TestCaseStorage in a new module and register it in _PROVIDERS.
Provider modules are imported lazily, so only the selected provider's SDK
needs to be importable.
"""
import importlib

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import TestCaseStorage

# STORAGE_PROVIDER value -> "module:ClassName" (relative to this package)
_PROVIDERS = {
    "s3": "s3:S3Storage",
    "azure": "azure:AzureBlobStorage",
}


def get_storage():
    """Return a TestCaseStorage instance for the configured STORAGE_PROVIDER."""
    provider = (getattr(settings, "STORAGE_PROVIDER", "") or "").strip().lower()
    target = _PROVIDERS.get(provider)
    if target is None:
        raise ImproperlyConfigured(
            f"Unknown STORAGE_PROVIDER '{provider}'. Supported values: {', '.join(sorted(_PROVIDERS))}"
        )
    module_name, class_name = target.split(":")
    module = importlib.import_module(f"{__name__}.{module_name}")
    return getattr(module, class_name).from_settings(settings)


__all__ = ["TestCaseStorage", "get_storage"]
