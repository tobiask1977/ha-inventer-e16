# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""Flow tests against a real Home Assistant core (pytest-homeassistant-custom-component)."""
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
