import json
import sqlite3

from billbridge.agent import run_turn
from billbridge.session import Session
from scripts.report import build_report, percentile
from tests.helpers import CUSTOMER, FakeLLM


def test_percentile():
    assert percentile([], 95) == 0
    assert percentile([5, 1, 3], 50) == 3
    assert percentile(list(range(1, 101)), 95) == 95


async def test_report_counts_containment_and_reasons(tools, events_db):
    contained = FakeLLM([[('verify_identity', CUSTOMER)], [('get_invoice_breakdown', {})],
                         'Your bill is R910,50.'])
    await run_turn(Session('contained'), 'bill?', contained, tools)
    invented = FakeLLM(['It is R1,00.'])
    await run_turn(Session('ungrounded'), 'bill?', invented, tools)

    conn = sqlite3.connect(events_db)
    report = build_report(conn)
    conn.close()
    assert report['sessions'] == 2
    assert report['containment_rate'] == 0.5
    assert report['escalation_reasons'] == {'ungrounded_amount': 1}
    assert report['grounding_failures'] == 1
    assert report['tools']['verify_identity']['calls'] == 1
    assert report['tools']['get_invoice_breakdown']['outcomes'] == {'ok': 1}
    json.dumps(report)
