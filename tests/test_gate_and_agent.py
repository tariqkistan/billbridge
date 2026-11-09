import json
import sqlite3

import pytest

from billbridge.agent import SAFE_FALLBACK, amounts_in, run_turn
from billbridge.session import Session
from legacy_sim import app as sim
from tests.helpers import CUSTOMER, FakeLLM, LoopingLLM

WRONG = {**CUSTOMER, 'id_last4': '9999'}


def events(db: str) -> list[tuple[str, dict]]:
    conn = sqlite3.connect(db)
    try:
        return [(t, json.loads(d)) for t, d in conn.execute('SELECT type, detail FROM events')]
    finally:
        conn.close()


# ---- the gate ----

@pytest.mark.parametrize('tool', ['get_invoice_breakdown', 'get_payment_status'])
async def test_account_tools_refuse_unverified_session(tools, session, tool):
    assert await tools.execute(session, tool, '{}') == {'error': 'not_verified'}
    assert session.allowed_cents == set()


async def test_account_tools_take_no_account_id(tools, session):
    await tools.execute(session, 'verify_identity', json.dumps(CUSTOMER))
    result = await tools.execute(session, 'get_payment_status', '{"account_id": "A-0411"}')
    assert result == {'error': 'bad_arguments'}


async def test_verify_then_invoice_breakdown(tools, session):
    verified = await tools.execute(session, 'verify_identity', json.dumps(CUSTOMER))
    assert verified == {'verified': True, 'first_name': 'Thandi'}
    result = await tools.execute(session, 'get_invoice_breakdown', '{}')
    assert result['period'] == '2026-10'
    assert result['total_cents'] == 91050
    assert result['previous_total_cents'] == 59800
    assert result['change_cents'] == 31250
    assert result['changes'] == [{'category': 'roaming', 'change_cents': 31250}]
    assert {91050, 59800, 31250, 5000}.issubset(session.allowed_cents)


async def test_invoice_for_specific_period(tools, session):
    await tools.execute(session, 'verify_identity', json.dumps(CUSTOMER))
    result = await tools.execute(session, 'get_invoice_breakdown', '{"period": "2026-09"}')
    assert result['total_cents'] == 59800
    assert 'previous_total_cents' not in result
    missing = await tools.execute(session, 'get_invoice_breakdown', '{"period": "2025-01"}')
    assert missing == {'error': 'period_not_found'}


async def test_unknown_number_and_wrong_details_look_identical(tools):
    a, b = Session('a'), Session('b')
    unknown = await tools.execute(a, 'verify_identity', json.dumps({**CUSTOMER, 'msisdn': '0830000000'}))
    wrong = await tools.execute(b, 'verify_identity', json.dumps(WRONG))
    assert unknown == wrong == {'verified': False, 'locked': False, 'attempts_left': 2}


async def test_three_failures_lock_and_escalate_once(tools, session, events_db):
    for _ in range(2):
        await tools.execute(session, 'verify_identity', json.dumps(WRONG))
    locked = await tools.execute(session, 'verify_identity', json.dumps(WRONG))
    assert locked['locked'] is True and locked['ticket_ref'].startswith('TCK-')
    assert session.escalated
    # correct details after lockout still fail
    again = await tools.execute(session, 'verify_identity', json.dumps(CUSTOMER))
    assert again == {'verified': False, 'locked': True, 'ticket_ref': locked['ticket_ref']}
    assert not session.verified
    assert len(sim.TICKETS) == 1
    assert [d['reason'] for t, d in events(events_db) if t == 'escalation'] == [
        'verification_locked']


async def test_escalation_is_one_ticket_per_session(tools, session):
    first = await tools.execute(session, 'escalate_to_human', '{"reason": "a", "summary": "s"}')
    second = await tools.execute(session, 'escalate_to_human', '{"reason": "b", "summary": "s"}')
    assert first == second
    assert len(sim.TICKETS) == 1


async def test_backend_down_becomes_structured_error(tools, session, events_db):
    sim.app.state.fault_mode = 'crm_down'
    result = await tools.execute(session, 'verify_identity', json.dumps(CUSTOMER))
    assert result == {'error': 'backend_unavailable'}
    assert ('tool_call', {'tool': 'verify_identity', 'outcome': 'backend_error:TransientError'}) \
        in events(events_db)


async def test_unknown_tool_and_bad_json(tools, session):
    assert await tools.execute(session, 'delete_account', '{}') == {'error': 'unknown_tool'}
    assert await tools.execute(session, 'verify_identity', '{not json') == {'error': 'bad_arguments'}


async def test_event_log_contains_no_customer_data(tools, session, events_db):
    await tools.execute(session, 'verify_identity', json.dumps(CUSTOMER))
    await tools.execute(session, 'get_invoice_breakdown', '{}')
    raw = json.dumps(events(events_db))
    for secret in ('0821234567', '1083', '1985-03-12', 'Thandi', 'Nkosi'):
        assert secret not in raw


# ---- grounding ----

@pytest.mark.parametrize('text, cents', [
    ('Your bill is R910,50.', {91050}),
    ('R1 234,50 and R 50,00', {123450, 5000}),
    ('It went up by R312.50', {31250}),
    ('No amounts here, or roughly R900', set()),
])
def test_amounts_in(text, cents):
    assert amounts_in(text) == cents


# ---- the loop ----

async def test_full_turn_grounded_reply(tools, session):
    llm = FakeLLM([
        [('verify_identity', CUSTOMER)],
        [('get_invoice_breakdown', {})],
        'Thanks Thandi. Your October bill is R910,50, up R312,50 from R598,00 because of roaming.',
    ])
    result = await run_turn(session, 'why is my bill up? 0821234567 1083 1985-03-12', llm, tools)
    assert result.reply.startswith('Thanks Thandi')
    assert result.escalated is False
    assert result.tools_called == ['verify_identity', 'get_invoice_breakdown']
    assert llm.requests[0]['temperature'] == 0
    # tool results were fed back to the model
    assert any(m.get('role') == 'tool' for m in llm.requests[-1]['messages'])


async def test_ungrounded_amount_is_replaced_and_escalated(tools, session, events_db):
    llm = FakeLLM([
        [('verify_identity', CUSTOMER)],
        [('get_invoice_breakdown', {})],
        'Without roaming you would have paid R648,00.',  # invented arithmetic
    ])
    result = await run_turn(session, 'what would it be without roaming?', llm, tools)
    assert result.reply == SAFE_FALLBACK
    assert result.escalated and result.ticket_ref
    types = [t for t, _ in events(events_db)]
    assert 'grounding_fail' in types and 'escalation' in types


async def test_amount_before_verification_is_ungrounded(tools, session):
    llm = FakeLLM(['Your bill is R910,50.'])
    result = await run_turn(session, 'what is my bill', llm, tools)
    assert result.reply == SAFE_FALLBACK


async def test_loop_limit_escalates(tools, session):
    result = await run_turn(session, 'hi', LoopingLLM([]), tools)
    assert result.reply == SAFE_FALLBACK
    assert result.escalated


async def test_history_carries_across_turns(tools, session):
    llm = FakeLLM([
        'Please share your number, ID last 4 and date of birth.',
        [('verify_identity', CUSTOMER)],
        'Thanks, you are verified.',
    ])
    await run_turn(session, 'why is my bill up?', llm, tools)
    await run_turn(session, '0821234567, 1083, 1985-03-12', llm, tools)
    contents = [m.get('content') for m in llm.requests[-1]['messages']]
    assert 'why is my bill up?' in contents
    assert session.verified
