import httpx
import openai
import pytest

from billbridge.api import create_app
from legacy_sim import app as sim
from tests.helpers import CUSTOMER, FakeLLM


async def post(app, payload):
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://api') as client:
            return [await client.post('/chat', json=p) for p in payload]


async def test_chat_endpoint_runs_a_turn(http):
    llm = FakeLLM([[('verify_identity', CUSTOMER)], 'You are verified, Thandi.'])
    app = create_app(llm=llm, http=http, model='test-model')
    [resp] = await post(app, [{'session_id': 's1', 'message': 'hi, 0821234567 1083 1985-03-12'}])
    assert resp.status_code == 200
    body = resp.json()
    assert body['reply'] == 'You are verified, Thandi.'
    assert body['tools_called'] == ['verify_identity']
    assert llm.requests[0]['model'] == 'test-model'


async def test_sessions_are_isolated(http):
    llm = FakeLLM([
        [('verify_identity', CUSTOMER)], 'Verified.',
        [('get_payment_status', {})], 'I cannot share that yet.',
    ])
    app = create_app(llm=llm, http=http, model='m')
    _, other = await post(app, [
        {'session_id': 'verified', 'message': 'verify me'},
        {'session_id': 'stranger', 'message': 'show payments'},
    ])
    assert other.json()['tools_called'] == ['get_payment_status']
    tool_msg = [m for m in llm.requests[-1]['messages'] if m.get('role') == 'tool']
    assert tool_msg[-1]['content'] == '{"error": "not_verified"}'


async def test_ticket_system_down_during_escalation_returns_safe_reply(http):
    sim.app.state.fault_mode = 'flaky'
    sim.app.state.rng.random = lambda: 0.0  # every call fails
    llm = FakeLLM([[('escalate_to_human', {'reason': 'r', 'summary': 's'})], 'Done.'])
    app = create_app(llm=llm, http=http, model='m')
    [resp] = await post(app, [{'session_id': 's', 'message': 'a person please'}])
    assert resp.status_code == 200
    assert resp.json()['escalated'] is False


@pytest.mark.parametrize('payload', [{'session_id': '', 'message': 'x'},
                                     {'session_id': 's', 'message': ''}, {}])
async def test_bad_requests_rejected(http, payload):
    app = create_app(llm=FakeLLM([]), http=http, model='m')
    [resp] = await post(app, [payload])
    assert resp.status_code == 422


class DownLLM(FakeLLM):
    async def _create(self, **kwargs):
        raise openai.APIConnectionError(request=httpx.Request('POST', 'http://llm'))


async def test_model_outage_escalates_instead_of_500(http):
    app = create_app(llm=DownLLM([]), http=http, model='m')
    [resp] = await post(app, [{'session_id': 's', 'message': 'hi'}])
    assert resp.status_code == 200
    body = resp.json()
    assert body['escalated'] is True and body['ticket_ref'].startswith('TCK-')
