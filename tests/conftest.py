"""Test fixtures."""

from __future__ import annotations

import pytest
import pytest_socket


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/ during tests."""
    yield


@pytest.fixture
def live_network(socket_enabled, disable_mock_zeroconf_resolver):
    """Let a test reach the real internet.

    The Home Assistant test harness deliberately walls tests off from the network: it
    mocks the DNS resolver and pins pytest-socket to 127.0.0.1. That default is right for
    ordinary tests, but the live tests exist precisely to check that the real Open-Meteo
    and BGR endpoints still behave as assumed, so both walls have to come down.

    Restoring the real resolver also wakes real zeroconf, which can then emit a
    "Event loop is closed" error while shutting its threads down at teardown. It is
    harmless noise from the harness, not from this integration — which speaks nothing but
    plain HTTPS. Swapping in phcc's `mock_zeroconf` to silence it breaks setup outright
    (its MagicMock is awaited during bootstrap), so the noise stays.
    """
    pytest_socket._remove_restrictions()
    pytest_socket.enable_socket()
    yield
