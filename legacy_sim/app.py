import csv
import io
import random

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse

app = FastAPI(title='Legacy Billing Simulator')
app.state.fault_mode = 'none'  # none | crm_down | flaky
app.state.rng = random.Random(42)
TICKETS: dict[str, dict] = {}

CRM = [
    {'CUST_ID': 'C-900', 'ACCT_NO': 'A-1001', 'CustName': '  THANDI NKOSI ', 'MSISDN': '0821234567',
     'ID_NO': '8503125001083', 'DOB': '12/03/1985', 'STATUS': 'ACTIVE'},
    {'CUST_ID': 'C-411', 'ACCT_NO': 'A-0411', 'CustName': 'T NKOSI', 'MSISDN': '0821234567',
     'ID_NO': '8503125001083', 'DOB': '12/03/1985', 'STATUS': 'INACTIVE'},
]

BILLING_ROWS = [
    ['INV_NO', 'ACCT', 'PERIOD', 'LINE_DESC', 'AMT', 'CAT'],
    ['INV-2610', 'A-1001', '202610', 'Anytime 500 plan', 'R499,00', 'SUB'],
    ['INV-2610', 'A-1001', '202610', 'Data top-up 5GB', 'R149,00', 'USG'],
    ['INV-2610', 'A-1001', '202610', 'Roaming Botswana', 'R312,50', 'ROM'],
    ['INV-2610', 'A-1001', '202610', 'Loyalty discount', '-R50,00', 'DSC'],
    ['INV-2609', 'A-1001', '202609', 'Anytime 500 plan', 'R499,00', 'SUB'],
    ['INV-2609', 'A-1001', '202609', 'Data top-up 5GB', 'R149,00', 'USG'],
    ['INV-2609', 'A-1001', '202609', 'Loyalty discount', '-R50,00', 'DSC'],
]

PAYMENTS = [
    {'PAY_REF': 'P-77', 'ACCT': 'A-1001', 'AMT': 'R598,00', 'STAT': 'S', 'PAID_ON': '2026-10-02'},
    {'PAY_REF': 'P-78', 'ACCT': 'A-1001', 'AMT': 'R910,50', 'STAT': 'P', 'PAID_ON': '2026-11-05'},
]


def maybe_fault(system: str) -> None:
    mode = app.state.fault_mode
    if mode == 'crm_down' and system == 'crm':
        raise HTTPException(status_code=503, detail='CRM unavailable')
    if mode == 'flaky' and app.state.rng.random() < 0.3:
        raise HTTPException(status_code=503, detail='Upstream hiccup')


@app.get('/crm/lookup')
def crm_lookup(msisdn: str):
    maybe_fault('crm')
    return [r for r in CRM if r['MSISDN'] == msisdn]


@app.get('/billing/export', response_class=PlainTextResponse)
def billing_export(account_id: str):
    maybe_fault('billing')
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=';')
    writer.writerow(BILLING_ROWS[0])
    for row in BILLING_ROWS[1:]:
        if row[1] == account_id:
            writer.writerow(row)
    return buf.getvalue()


@app.get('/payments')
def payments(account_id: str):
    maybe_fault('payments')
    return [p for p in PAYMENTS if p['ACCT'] == account_id]


@app.post('/tickets')
async def create_ticket(request: Request, idempotency_key: str = Header(...)):
    maybe_fault('tickets')
    if idempotency_key in TICKETS:
        return TICKETS[idempotency_key]  # same key, same ticket: no duplicate
    body = await request.json()
    ref = f'TCK-{len(TICKETS) + 1:04d}'
    TICKETS[idempotency_key] = {'ref': ref, **body}
    return TICKETS[idempotency_key]
