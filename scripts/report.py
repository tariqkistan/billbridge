'''Operational metrics from the event log.

    python -m scripts.report                       # uses EVENTS_DB
    python -m scripts.report --db other.db --since-hours 24
'''
import argparse
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict


def percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))
    return ordered[index]


def build_report(conn: sqlite3.Connection, since: float = 0.0) -> dict:
    rows = conn.execute(
        'SELECT session_id, type, detail, latency_ms FROM events WHERE ts >= ?', (since,)
    ).fetchall()
    sessions: set[str] = set()
    escalated: set[str] = set()
    reasons: Counter[str] = Counter()
    tool_calls: Counter[str] = Counter()
    tool_outcomes: dict[str, Counter[str]] = defaultdict(Counter)
    latencies: dict[str, list[int]] = defaultdict(list)
    grounding_fails = turns = turn_errors = 0
    for session_id, type_, detail_raw, latency_ms in rows:
        detail = json.loads(detail_raw or '{}')
        sessions.add(session_id)
        if type_ == 'tool_call':
            tool = detail.get('tool', '?')
            tool_calls[tool] += 1
            tool_outcomes[tool][detail.get('outcome', '?')] += 1
            latencies[tool].append(latency_ms)
        elif type_ == 'escalation':
            escalated.add(session_id)
            reasons[detail.get('reason', '?')] += 1
        elif type_ == 'grounding_fail':
            grounding_fails += 1
        elif type_ == 'turn':
            turns += 1
        elif type_ == 'turn_error':
            turn_errors += 1
    total = len(sessions)
    return {
        'sessions': total,
        'turns': turns,
        'containment_rate': round((total - len(escalated)) / total, 3) if total else None,
        'escalations': len(escalated),
        'escalation_reasons': dict(reasons.most_common()),
        'grounding_failures': grounding_fails,
        'turn_errors': turn_errors,
        'tools': {
            tool: {
                'calls': count,
                'outcomes': dict(tool_outcomes[tool]),
                'error_rate': round(sum(n for o, n in tool_outcomes[tool].items()
                                        if o.startswith(('backend_error', 'bad_arguments')))
                                    / count, 3),
                'p50_ms': percentile(latencies[tool], 50),
                'p95_ms': percentile(latencies[tool], 95),
            }
            for tool, count in tool_calls.most_common()
        },
    }


def print_report(report: dict) -> None:
    rate = report['containment_rate']
    print(f'Sessions: {report["sessions"]}   Turns: {report["turns"]}')
    print(f'Containment: {"n/a" if rate is None else f"{rate:.0%}"}   '
          f'Escalations: {report["escalations"]}   '
          f'Grounding failures: {report["grounding_failures"]}   '
          f'Turn errors: {report["turn_errors"]}')
    if report['escalation_reasons']:
        print('Escalation reasons: ' + ', '.join(
            f'{k}={v}' for k, v in report['escalation_reasons'].items()))
    if report['tools']:
        print(f'\n{"tool":<24}{"calls":>6}{"err%":>7}{"p50ms":>7}{"p95ms":>7}  outcomes')
        for tool, t in report['tools'].items():
            outcomes = ', '.join(f'{k}={v}' for k, v in t['outcomes'].items())
            print(f'{tool:<24}{t["calls"]:>6}{t["error_rate"]:>7.0%}'
                  f'{t["p50_ms"]:>7}{t["p95_ms"]:>7}  {outcomes}')
    print('\nNote: containment is not resolution. A contained session may still be an '
          'unhappy customer.')


def main() -> int:
    from billbridge.config import EVENTS_DB

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=EVENTS_DB)
    parser.add_argument('--since-hours', type=float, default=0.0)
    parser.add_argument('--json', action='store_true', help='print raw JSON')
    args = parser.parse_args()
    since = time.time() - args.since_hours * 3600 if args.since_hours else 0.0
    conn = sqlite3.connect(args.db)
    try:
        report = build_report(conn, since)
    except sqlite3.OperationalError:
        print(f'No events table in {args.db}. Run some conversations first.')
        return 1
    finally:
        conn.close()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
    return 0


if __name__ == '__main__':
    sys.exit(main())
