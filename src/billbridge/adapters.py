import calendar
import csv
import io
import re
from datetime import date, datetime
from typing import Literal

import httpx

from billbridge.errors import DataQualityError
from billbridge.models import Category, ChargeLine, Customer, Invoice, Payment
from billbridge.resilient import request_with_retry

CATEGORY_MAP: dict[str, Category] = {
    'SUB': 'subscription', 'USG': 'usage', 'ROM': 'roaming',
    'DEV': 'device', 'FEE': 'fee', 'DSC': 'discount',
}
PAYMENT_STATUS: dict[str, Literal['settled', 'pending', 'failed']] = {
    'S': 'settled', 'P': 'pending', 'F': 'failed',
}


def parse_date(raw: str, fmt: str) -> date:
    try:
        return datetime.strptime(raw.strip(), fmt).date()
    except ValueError:
        raise DataQualityError(f'Unparseable date {raw!r}')


def parse_money_to_cents(raw: str) -> int:
    '''Handles R1 234,50 / -R50,00 / 312.50 / 1,234.50. Raises on ambiguity.'''
    negative = raw.strip().startswith(('-', '('))
    digits = re.sub('[^0-9,.]', '', raw)
    if not digits:
        raise DataQualityError(f'No amount in {raw!r}')
    has_comma, has_dot = ',' in digits, '.' in digits
    if has_comma and has_dot:
        decimal = ',' if digits.rfind(',') > digits.rfind('.') else '.'
    elif has_comma:
        decimal = ','
    elif has_dot:
        decimal = '.'
    else:
        decimal = None
    if decimal is None:
        cents = int(digits) * 100
    else:
        whole, _, frac = digits.rpartition(decimal)
        if len(frac) not in (1, 2):
            raise DataQualityError(f'Ambiguous amount {raw!r}')
        whole = re.sub('[,.]', '', whole) or '0'
        cents = int(whole) * 100 + int(frac.ljust(2, '0'))
    return -cents if negative else cents


class CrmClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def find_customer(self, msisdn: str) -> Customer | None:
        resp = await request_with_retry(self.http, 'GET', '/crm/lookup', params={'msisdn': msisdn})
        rows = resp.json()
        active = [r for r in rows if str(r.get('STATUS', 'ACTIVE')).upper() == 'ACTIVE']
        if len(active) > 1:
            raise DataQualityError('More than one ACTIVE CRM record for this number')
        if not active:
            return None
        r = active[0]
        try:
            return Customer(
                customer_id=r['CUST_ID'],
                account_id=r['ACCT_NO'],
                full_name=r['CustName'].strip().title(),
                msisdn=r['MSISDN'],
                id_last4=r['ID_NO'][-4:],
                dob=parse_date(r['DOB'], '%d/%m/%Y'),
            )
        except KeyError as e:
            raise DataQualityError(f'CRM record missing field {e}')


class BillingClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def list_invoices(self, account_id: str) -> list[Invoice]:
        resp = await request_with_retry(
            self.http, 'GET', '/billing/export', params={'account_id': account_id})
        grouped: dict[str, dict] = {}
        try:
            for row in csv.DictReader(io.StringIO(resp.text), delimiter=';'):
                code = row['CAT']
                category: Category = CATEGORY_MAP[code] if code in CATEGORY_MAP else 'other'
                group = grouped.setdefault(
                    row['INV_NO'], {'account_id': row['ACCT'], 'period': row['PERIOD'], 'lines': []})
                group['lines'].append(ChargeLine(
                    description=row['LINE_DESC'].strip(),
                    amount_cents=parse_money_to_cents(row['AMT']),
                    category=category))
        except KeyError as e:
            raise DataQualityError(f'Billing export missing column {e}')
        invoices = []
        for invoice_id, g in grouped.items():
            start = parse_date(g['period'] + '01', '%Y%m%d')
            last_day = calendar.monthrange(start.year, start.month)[1]
            invoices.append(Invoice(
                invoice_id=invoice_id, account_id=g['account_id'], period_start=start,
                period_end=date(start.year, start.month, last_day), lines=g['lines']))
        return sorted(invoices, key=lambda i: i.period_start, reverse=True)


class PaymentsClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def list_payments(self, account_id: str) -> list[Payment]:
        resp = await request_with_retry(
            self.http, 'GET', '/payments', params={'account_id': account_id})
        payments = []
        try:
            for r in resp.json():
                raw_status = r['STAT']
                status = PAYMENT_STATUS.get(raw_status)
                if status is None:
                    raise DataQualityError(f'Unknown payment status {raw_status!r}')
                payments.append(Payment(
                    payment_id=r['PAY_REF'], account_id=r['ACCT'],
                    amount_cents=parse_money_to_cents(r['AMT']), status=status,
                    paid_on=parse_date(r['PAID_ON'], '%Y-%m-%d')))
        except KeyError as e:
            raise DataQualityError(f'Payment record missing field {e}')
        return sorted(payments, key=lambda p: p.paid_on, reverse=True)


class TicketClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def create(self, account_id: str | None, reason: str, summary: str,
                     idempotency_key: str) -> str:
        resp = await request_with_retry(
            self.http, 'POST', '/tickets',
            json={'account_id': account_id, 'reason': reason, 'summary': summary},
            headers={'Idempotency-Key': idempotency_key})
        return resp.json()['ref']
