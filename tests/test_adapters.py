import httpx
import pytest

from billbridge.adapters import (
    BillingClient,
    CrmClient,
    PaymentsClient,
    TicketClient,
    parse_money_to_cents,
)
from billbridge.errors import DataQualityError, PermanentError, TransientError
from billbridge.resilient import request_with_retry
from legacy_sim import app as sim


@pytest.mark.parametrize('raw, cents', [
    ('R312,50', 31250),
    ('-R50,00', -5000),
    ('R1 234,50', 123450),
    ('312.50', 31250),
    ('1,234.50', 123450),
    ('1.234,50', 123450),
    ('R499', 49900),
    ('R0,5', 50),
    ('(R20,00)', -2000),
])
def test_parse_money(raw, cents):
    assert parse_money_to_cents(raw) == cents


@pytest.mark.parametrize('raw', ['1,234', 'R', '', '12.3456'])
def test_parse_money_refuses_to_guess(raw):
    with pytest.raises(DataQualityError):
        parse_money_to_cents(raw)


async def test_crm_picks_active_record_and_cleans_it(http):
    customer = await CrmClient(http).find_customer('0821234567')
    assert customer is not None
    assert customer.account_id == 'A-1001'  # not the INACTIVE A-0411 duplicate
    assert customer.full_name == 'Thandi Nkosi'
    assert customer.id_last4 == '1083'
    assert customer.dob.isoformat() == '1985-03-12'


async def test_crm_unknown_number_is_none(http):
    assert await CrmClient(http).find_customer('0000000000') is None


async def test_crm_two_active_records_is_data_quality_error(http):
    sim.CRM[1]['STATUS'] = 'ACTIVE'
    with pytest.raises(DataQualityError):
        await CrmClient(http).find_customer('0821234567')


async def test_billing_csv_normalised_to_invoices(http):
    invoices = await BillingClient(http).list_invoices('A-1001')
    assert [i.invoice_id for i in invoices] == ['INV-2610', 'INV-2609']  # newest first
    october, september = invoices
    assert october.total_cents == 91050
    assert september.total_cents == 59800
    assert october.period_start.isoformat() == '2026-10-01'
    assert october.period_end.isoformat() == '2026-10-31'
    assert {line.category for line in october.lines} == {
        'subscription', 'usage', 'roaming', 'discount'}


async def test_payments_normalised(http):
    payments = await PaymentsClient(http).list_payments('A-1001')
    assert [(p.payment_id, p.status, p.amount_cents) for p in payments] == [
        ('P-78', 'pending', 91050), ('P-77', 'settled', 59800)]


async def test_unknown_payment_status_is_data_quality_error(http):
    sim.PAYMENTS[0]['STAT'] = 'X'
    with pytest.raises(DataQualityError):
        await PaymentsClient(http).list_payments('A-1001')


async def test_ticket_idempotency_key_prevents_duplicates(http):
    client = TicketClient(http)
    first = await client.create('A-1001', 'r', 's', 'key-1')
    again = await client.create('A-1001', 'r', 's', 'key-1')
    other = await client.create('A-1001', 'r', 's', 'key-2')
    assert first == again != other
    assert len(sim.TICKETS) == 2


async def test_crm_down_raises_transient_after_retries(http):
    sim.app.state.fault_mode = 'crm_down'
    with pytest.raises(TransientError):
        await CrmClient(http).find_customer('0821234567')


async def test_flaky_backend_is_mostly_absorbed_by_retries(http):
    # 30% failure per call and 3 attempts leaves ~2.7% of requests failing, so
    # assert the rate, not perfection. The seeded rng keeps this deterministic.
    sim.app.state.fault_mode = 'flaky'
    ok = 0
    for _ in range(40):
        try:
            invoices = await BillingClient(http).list_invoices('A-1001')
        except TransientError:
            continue
        assert invoices[0].total_cents == 91050
        ok += 1
    assert ok >= 36


def _mock_client(statuses: list[int], headers: dict | None = None):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(statuses[min(len(calls) - 1, len(statuses) - 1)],
                              headers=headers or {}, json={})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://x'), calls


async def test_retry_recovers_after_transient_errors():
    client, calls = _mock_client([503, 429, 200])
    resp = await request_with_retry(client, 'GET', '/thing')
    assert resp.status_code == 200
    assert len(calls) == 3


async def test_4xx_is_permanent_and_not_retried():
    client, calls = _mock_client([404])
    with pytest.raises(PermanentError):
        await request_with_retry(client, 'GET', '/thing')
    assert len(calls) == 1


async def test_retry_after_header_is_honoured(monkeypatch):
    delays = []

    async def record(delay: float) -> None:
        delays.append(delay)
    monkeypatch.setattr('billbridge.resilient.asyncio.sleep', record)
    client, _ = _mock_client([429, 200], headers={'Retry-After': '1.5'})
    await request_with_retry(client, 'GET', '/thing')
    assert delays == [1.5]


async def test_timeouts_are_transient():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout('slow', request=request)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://x')
    with pytest.raises(TransientError):
        await request_with_retry(client, 'GET', '/thing')
