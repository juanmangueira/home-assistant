"""Test cases for the Shelly component."""
from __future__ import annotations

from unittest.mock import AsyncMock

from aioshelly.exceptions import DeviceConnectionError, InvalidAuthError
import pytest

from homeassistant.components.shelly.const import DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE
from homeassistant.helpers import device_registry
from homeassistant.setup import async_setup_component

from . import MOCK_MAC, init_integration

from tests.common import MockConfigEntry


async def test_custom_coap_port(hass, mock_block_device, caplog):
    """Test custom coap port."""
    assert await async_setup_component(
        hass,
        DOMAIN,
        {DOMAIN: {"coap_port": 7632}},
    )
    await hass.async_block_till_done()

    await init_integration(hass, 1)
    assert "Starting CoAP context with UDP port 7632" in caplog.text


@pytest.mark.parametrize("gen", [1, 2])
async def test_shared_device_mac(
    hass, gen, mock_block_device, mock_rpc_device, device_reg, caplog
):
    """Test first time shared device with another domain."""
    config_entry = MockConfigEntry(domain="test", data={}, unique_id="some_id")
    config_entry.add_to_hass(hass)
    device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={
            (
                device_registry.CONNECTION_NETWORK_MAC,
                device_registry.format_mac(MOCK_MAC),
            )
        },
    )
    await init_integration(hass, gen, sleep_period=1000)
    assert "will resume when device is online" in caplog.text


async def test_setup_entry_not_shelly(hass, caplog):
    """Test not Shelly entry."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id=DOMAIN)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id) is False
    await hass.async_block_till_done()

    assert "probably comes from a custom integration" in caplog.text


@pytest.mark.parametrize("gen", [1, 2])
async def test_device_connection_error(
    hass, gen, mock_block_device, mock_rpc_device, monkeypatch
):
    """Test device connection error."""
    monkeypatch.setattr(
        mock_block_device, "initialize", AsyncMock(side_effect=DeviceConnectionError)
    )
    monkeypatch.setattr(
        mock_rpc_device, "initialize", AsyncMock(side_effect=DeviceConnectionError)
    )

    entry = await init_integration(hass, gen)
    assert entry.state == ConfigEntryState.SETUP_RETRY


@pytest.mark.parametrize("gen", [1, 2])
async def test_device_auth_error(
    hass, gen, mock_block_device, mock_rpc_device, monkeypatch
):
    """Test device authentication error."""
    monkeypatch.setattr(
        mock_block_device, "initialize", AsyncMock(side_effect=InvalidAuthError)
    )
    monkeypatch.setattr(
        mock_rpc_device, "initialize", AsyncMock(side_effect=InvalidAuthError)
    )

    entry = await init_integration(hass, gen)
    assert entry.state == ConfigEntryState.SETUP_ERROR

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1

    flow = flows[0]
    assert flow.get("step_id") == "reauth_confirm"
    assert flow.get("handler") == DOMAIN

    assert "context" in flow
    assert flow["context"].get("source") == SOURCE_REAUTH
    assert flow["context"].get("entry_id") == entry.entry_id


@pytest.mark.parametrize("entry_sleep, device_sleep", [(None, 0), (1000, 1000)])
async def test_sleeping_block_device_online(
    hass, entry_sleep, device_sleep, mock_block_device, device_reg, caplog
):
    """Test sleeping block device online."""
    config_entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id="shelly")
    config_entry.add_to_hass(hass)
    device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={
            (
                device_registry.CONNECTION_NETWORK_MAC,
                device_registry.format_mac(MOCK_MAC),
            )
        },
    )

    entry = await init_integration(hass, 1, sleep_period=entry_sleep)
    assert "will resume when device is online" in caplog.text

    mock_block_device.mock_update()
    assert "online, resuming setup" in caplog.text
    assert entry.data["sleep_period"] == device_sleep


@pytest.mark.parametrize("entry_sleep, device_sleep", [(None, 0), (1000, 1000)])
async def test_sleeping_rpc_device_online(
    hass, entry_sleep, device_sleep, mock_rpc_device, caplog
):
    """Test sleeping RPC device online."""
    entry = await init_integration(hass, 2, sleep_period=entry_sleep)
    assert "will resume when device is online" in caplog.text

    mock_rpc_device.mock_update()
    assert "online, resuming setup" in caplog.text
    assert entry.data["sleep_period"] == device_sleep


@pytest.mark.parametrize(
    "gen, entity_id",
    [
        (1, "switch.test_name_channel_1"),
        (2, "switch.test_switch_0"),
    ],
)
async def test_entry_unload(hass, gen, entity_id, mock_block_device, mock_rpc_device):
    """Test entry unload."""
    entry = await init_integration(hass, gen)

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(entity_id).state is STATE_ON

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(entity_id).state is STATE_UNAVAILABLE


@pytest.mark.parametrize(
    "gen, entity_id",
    [
        (1, "switch.test_name_channel_1"),
        (2, "switch.test_switch_0"),
    ],
)
async def test_entry_unload_device_not_ready(
    hass, gen, entity_id, mock_block_device, mock_rpc_device
):
    """Test entry unload when device is not ready."""
    entry = await init_integration(hass, gen, sleep_period=1000)

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(entity_id) is None

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
