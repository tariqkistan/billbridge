import random
from collections.abc import AsyncIterator

import httpx
import pytest

import billbridge.events
from billbridge.api import build_toolbox
from billbridge.session import Session
from billbridge.tools import ToolBox
from legacy_sim import app as sim


@pytest.fixture(autouse=True)
def events_db(tmp_path, monkeypatch) -> str:
    path = str(tmp_path / 'events.db')
    monkeypatch.setattr(billbridge.events, 'EVENTS_DB', path)
    return path


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch) -> None:
    '''Keep retries real but instant.'''
    async def instant(_: float) -> None:
        return None
    monkeypatch.setattr('billbridge.resilient.asyncio.sleep', instant)


@pytest.fixture(autouse=True)
def reset_sim() -> None:
    sim.app.state.fault_mode = 'none'
    sim.app.state.rng = random.Random(42)
    sim.TICKETS.clear()
    crm_backup = [dict(r) for r in sim.CRM]
    payments_backup = [dict(p) for p in sim.PAYMENTS]
    yield
    sim.app.state.fault_mode = 'none'
    sim.CRM[:] = crm_backup
    sim.PAYMENTS[:] = payments_backup


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=sim.app)
    async with httpx.AsyncClient(transport=transport, base_url='http://legacy') as client:
        yield client


@pytest.fixture
def tools(http: httpx.AsyncClient) -> ToolBox:
    return build_toolbox(http)


@pytest.fixture
def session() -> Session:
    return Session(session_id='test-session')
