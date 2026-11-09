import hashlib
import json
import time

from billbridge.adapters import BillingClient, CrmClient, PaymentsClient, TicketClient
from billbridge.config import MAX_VERIFY_ATTEMPTS
from billbridge.errors import BackendError
from billbridge.events import log_event
from billbridge.models import Invoice
from billbridge.session import Session


def _spec(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {'type': 'function', 'function': {
        'name': name, 'description': description,
        'parameters': {'type': 'object', 'properties': properties, 'required': required}}}


TOOL_SPECS = [
    _spec('verify_identity',
          'Verify the customer before any account information is shared.',
          {'msisdn': {'type': 'string', 'description': 'Mobile number, e.g. 0821234567'},
           'id_last4': {'type': 'string', 'description': 'Last 4 digits of the SA ID number'},
           'date_of_birth': {'type': 'string', 'description': 'ISO date, YYYY-MM-DD'}},
          ['msisdn', 'id_last4', 'date_of_birth']),
    _spec('get_invoice_breakdown',
          'Get the verified customer invoice lines and how they changed from the previous month.',
          {'period': {'type': 'string', 'description': 'Optional month, YYYY-MM. Defaults to latest.'}},
          []),
    _spec('get_payment_status',
          'Get the verified customer most recent payments and their status.', {}, []),
    _spec('escalate_to_human',
          'Hand the conversation to a human agent with a short summary.',
          {'reason': {'type': 'string'}, 'summary': {'type': 'string'}},
          ['reason', 'summary']),
]


def _changes_by_category(current: Invoice, previous: Invoice | None) -> list[dict]:
    def totals(invoice: Invoice | None) -> dict[str, int]:
        out: dict[str, int] = {}
        if invoice:
            for line in invoice.lines:
                out[line.category] = out.get(line.category, 0) + line.amount_cents
        return out

    cur, prev = totals(current), totals(previous)
    return [
        {'category': cat, 'change_cents': cur.get(cat, 0) - prev.get(cat, 0)}
        for cat in sorted(set(cur) | set(prev))
        if cur.get(cat, 0) != prev.get(cat, 0)
    ]


class ToolBox:
    def __init__(self, crm: CrmClient, billing: BillingClient,
                 payments: PaymentsClient, tickets: TicketClient) -> None:
        self.crm, self.billing, self.payments, self.tickets = crm, billing, payments, tickets

    async def execute(self, session: Session, name: str, raw_args: str) -> dict:
        try:
            args = json.loads(raw_args or '{}')
        except json.JSONDecodeError:
            return {'error': 'bad_arguments'}
        handler = getattr(self, f'_tool_{name}', None)
        if handler is None:
            return {'error': 'unknown_tool'}
        session.tool_trace.append(name)
        started = time.perf_counter()
        try:
            result = await handler(session, **args)
            outcome = 'refused' if result.get('error') == 'not_verified' else 'ok'
        except TypeError:  # the model sent argument names the handler does not accept
            result, outcome = {'error': 'bad_arguments'}, 'bad_arguments'
        except BackendError as e:
            result = {'error': 'backend_unavailable'}
            outcome = f'backend_error:{type(e).__name__}'
        latency_ms = int((time.perf_counter() - started) * 1000)
        log_event(session.session_id, 'tool_call', {'tool': name, 'outcome': outcome}, latency_ms)
        self._remember_amounts(session, result)
        return result

    def _remember_amounts(self, session: Session, obj: object) -> None:
        '''Record every cents value a tool returned, for the grounding check.'''
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key.endswith('cents') and isinstance(value, int):
                    session.allowed_cents.add(abs(value))
                else:
                    self._remember_amounts(session, value)
        elif isinstance(obj, list):
            for item in obj:
                self._remember_amounts(session, item)

    async def escalate(self, session: Session, reason: str, summary: str) -> str:
        if session.ticket_ref:  # one ticket per session
            return session.ticket_ref
        key = hashlib.sha256(f'{session.session_id}:{reason}'.encode()).hexdigest()[:32]
        account = session.customer.account_id if session.customer else None
        ref = await self.tickets.create(account, reason, summary, key)
        session.escalated, session.ticket_ref = True, ref
        log_event(session.session_id, 'escalation', {'reason': reason})
        return ref

    # ---- tool handlers ----

    async def _tool_verify_identity(self, session: Session, msisdn: str, id_last4: str,
                                    date_of_birth: str) -> dict:
        if session.locked:
            return {'verified': False, 'locked': True, 'ticket_ref': session.ticket_ref}
        customer = await self.crm.find_customer(msisdn)
        if (customer and customer.id_last4 == id_last4
                and customer.dob.isoformat() == date_of_birth):
            session.verified, session.customer = True, customer
            return {'verified': True, 'first_name': customer.full_name.split()[0]}
        session.failed_verifications += 1  # same answer for unknown number and wrong details
        if session.locked:
            ref = await self.escalate(
                session, 'verification_locked', 'Caller failed identity verification 3 times.')
            return {'verified': False, 'locked': True, 'ticket_ref': ref}
        return {'verified': False, 'locked': False,
                'attempts_left': MAX_VERIFY_ATTEMPTS - session.failed_verifications}

    async def _tool_get_invoice_breakdown(self, session: Session, period: str | None = None) -> dict:
        if not (session.verified and session.customer):
            return {'error': 'not_verified'}  # THE GATE: enforced in code
        invoices = await self.billing.list_invoices(session.customer.account_id)
        if not invoices:
            return {'error': 'no_invoices'}
        if period:
            matches = [i for i in invoices if i.period_start.strftime('%Y-%m') == period]
            if not matches:
                return {'error': 'period_not_found'}
            current = matches[0]
        else:
            current = invoices[0]
        position = invoices.index(current)
        previous = invoices[position + 1] if position + 1 < len(invoices) else None
        result: dict = {
            'period': current.period_start.strftime('%Y-%m'),
            'total_cents': current.total_cents,
            'lines': [{'description': line.description, 'category': line.category,
                       'amount_cents': line.amount_cents} for line in current.lines],
        }
        if previous:
            result['previous_period'] = previous.period_start.strftime('%Y-%m')
            result['previous_total_cents'] = previous.total_cents
            result['change_cents'] = current.total_cents - previous.total_cents
            result['changes'] = _changes_by_category(current, previous)
        return result

    async def _tool_get_payment_status(self, session: Session) -> dict:
        if not (session.verified and session.customer):
            return {'error': 'not_verified'}
        payments = await self.payments.list_payments(session.customer.account_id)
        return {'payments': [
            {'payment_id': p.payment_id, 'amount_cents': p.amount_cents,
             'status': p.status, 'paid_on': p.paid_on.isoformat()} for p in payments[:3]]}

    async def _tool_escalate_to_human(self, session: Session, reason: str, summary: str) -> dict:
        return {'ticket_ref': await self.escalate(session, reason, summary)}
