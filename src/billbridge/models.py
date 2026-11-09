from datetime import date
from typing import Literal

from pydantic import BaseModel

Category = Literal['subscription', 'usage', 'roaming', 'device', 'fee', 'discount', 'other']


class Customer(BaseModel):
    customer_id: str
    account_id: str
    full_name: str
    msisdn: str
    id_last4: str
    dob: date


class ChargeLine(BaseModel):
    description: str
    amount_cents: int  # money is ALWAYS integer cents
    category: Category


class Invoice(BaseModel):
    invoice_id: str
    account_id: str
    period_start: date
    period_end: date
    lines: list[ChargeLine]

    @property
    def total_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines)


class Payment(BaseModel):
    payment_id: str
    account_id: str
    amount_cents: int
    status: Literal['settled', 'pending', 'failed']
    paid_on: date


class TurnResult(BaseModel):
    reply: str
    escalated: bool = False
    ticket_ref: str | None = None
    tools_called: list[str] = []
