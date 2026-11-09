from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import openai
from fastapi import FastAPI
from pydantic import BaseModel, Field

from billbridge.adapters import BillingClient, CrmClient, PaymentsClient, TicketClient
from billbridge.agent import SAFE_FALLBACK, run_turn
from billbridge.config import LEGACY_BASE_URL, llm_model
from billbridge.errors import BackendError
from billbridge.events import log_event
from billbridge.llm import make_llm
from billbridge.models import TurnResult
from billbridge.session import SessionStore
from billbridge.tools import ToolBox


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)


def build_toolbox(http: httpx.AsyncClient) -> ToolBox:
    return ToolBox(CrmClient(http), BillingClient(http), PaymentsClient(http), TicketClient(http))


def create_app(llm: Any = None, http: httpx.AsyncClient | None = None,
               model: str | None = None) -> FastAPI:
    '''Inject llm and http in tests; production builds them from config.'''

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = http or httpx.AsyncClient(base_url=LEGACY_BASE_URL, timeout=5.0)
        app.state.llm = llm or make_llm()
        app.state.tools = build_toolbox(client)
        app.state.sessions = SessionStore()
        app.state.model = model or llm_model()
        try:
            yield
        finally:
            if http is None:
                await client.aclose()

    app = FastAPI(title='billbridge', lifespan=lifespan)

    @app.get('/health')
    async def health() -> dict:
        return {'status': 'ok'}

    @app.post('/chat', response_model=TurnResult)
    async def chat(req: ChatRequest) -> TurnResult:
        session = app.state.sessions.get(req.session_id)
        try:
            return await run_turn(session, req.message, app.state.llm, app.state.tools,
                                  model=app.state.model)
        except openai.APIError as e:  # model outage: hand over instead of returning a 500
            log_event(session.session_id, 'turn_error', {'error': type(e).__name__})
            try:
                await app.state.tools.escalate(session, 'llm_unavailable',
                                               'The assistant model was unavailable.')
            except BackendError:
                pass
        except BackendError as e:  # e.g. the ticket system is down while escalating
            log_event(session.session_id, 'turn_error', {'error': type(e).__name__})
        return TurnResult(reply=SAFE_FALLBACK, escalated=session.escalated,
                          ticket_ref=session.ticket_ref, tools_called=list(session.tool_trace))

    return app


app = create_app()
