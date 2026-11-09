'''Run the scenario suite against a real model and the in-process simulator.

    python -m scripts.run_scenarios                 # all scenarios
    python -m scripts.run_scenarios --only crm_down
    python -m scripts.run_scenarios --min-pass-rate 0.9 --out results/latest.json
'''
import argparse
import asyncio
import json
import random
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

from billbridge.agent import amounts_in, run_turn
from billbridge.api import build_toolbox
from billbridge.session import Session
from legacy_sim import app as sim

SCENARIOS_PATH = Path(__file__).resolve().parent.parent / 'scenarios' / 'scenarios.yaml'
EXPECT_KEYS = {'tools_called', 'tools_not_called', 'escalated', 'reply_contains',
               'reply_excludes'}


@dataclass
class ScenarioResult:
    id: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    escalated: bool = False
    seconds: float = 0.0


def load_scenarios(path: Path = SCENARIOS_PATH) -> list[dict]:
    data = yaml.safe_load(path.read_text())
    scenarios = data['scenarios']
    for s in scenarios:
        unknown = set(s.get('expect', {})) - EXPECT_KEYS
        if unknown:
            raise ValueError(f'{s["id"]}: unknown expect keys {sorted(unknown)}')
        if s.get('fault_mode', 'none') not in ('none', 'crm_down', 'flaky'):
            raise ValueError(f'{s["id"]}: bad fault_mode')
    return scenarios


def reset_simulator(fault_mode: str = 'none') -> None:
    sim.app.state.fault_mode = fault_mode
    sim.app.state.rng = random.Random(42)
    sim.TICKETS.clear()


def check(scenario: dict, session: Session, replies: list[str]) -> list[str]:
    expect = scenario.get('expect', {})
    failures = []
    trace = set(session.tool_trace)
    for tool in expect.get('tools_called', []):
        if tool not in trace:
            failures.append(f'expected tool {tool} to be called')
    for tool in expect.get('tools_not_called', []):
        if tool in trace:
            failures.append(f'tool {tool} must not be called')
    if 'escalated' in expect and session.escalated != expect['escalated']:
        failures.append(f'escalated={session.escalated}, expected {expect["escalated"]}')
    final = replies[-1].lower() if replies else ''
    for text in expect.get('reply_contains', []):
        if text.lower() not in final:
            failures.append(f'final reply missing {text!r}')
    for text in expect.get('reply_excludes', []):
        if any(text.lower() in r.lower() for r in replies):
            failures.append(f'a reply contained forbidden {text!r}')
    for r in replies:
        ungrounded = amounts_in(r) - session.allowed_cents
        if ungrounded:
            failures.append(f'ungrounded amounts in reply: {sorted(ungrounded)}')
    return failures


async def run_scenario(scenario: dict, llm: Any, model: str) -> ScenarioResult:
    reset_simulator(scenario.get('fault_mode', 'none'))
    session = Session(session_id=f'scenario-{scenario["id"]}-{int(time.time() * 1000)}')
    replies: list[str] = []
    started = time.perf_counter()
    transport = httpx.ASGITransport(app=sim.app)
    async with httpx.AsyncClient(transport=transport, base_url='http://legacy') as http:
        tools = build_toolbox(http)
        for message in scenario['turns']:
            result = await run_turn(session, message, llm, tools, model=model)
            replies.append(result.reply)
    reset_simulator()
    failures = check(scenario, session, replies)
    return ScenarioResult(id=scenario['id'], passed=not failures, failures=failures,
                          replies=replies, tools_called=list(session.tool_trace),
                          escalated=session.escalated,
                          seconds=round(time.perf_counter() - started, 2))


async def run_all(scenarios: list[dict], llm: Any, model: str) -> list[ScenarioResult]:
    # Sequential on purpose: fault_mode is global state on the simulator app.
    return [await run_scenario(s, llm, model) for s in scenarios]


def main() -> int:
    from billbridge.config import have_real_key, llm_model
    from billbridge.llm import make_llm

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', nargs='*', help='scenario ids to run')
    parser.add_argument('--min-pass-rate', type=float, default=1.0)
    parser.add_argument('--out', type=Path, help='write JSON results here')
    args = parser.parse_args()

    if not have_real_key():
        print('No model key configured (AZURE_OPENAI_KEY or OPENAI_API_KEY). See .env.example.')
        return 2
    scenarios = load_scenarios()
    if args.only:
        scenarios = [s for s in scenarios if s['id'] in args.only]

    results = asyncio.run(run_all(scenarios, make_llm(), llm_model()))
    passed = sum(r.passed for r in results)
    rate = passed / len(results) if results else 0.0
    for r in results:
        print(f'{"PASS" if r.passed else "FAIL"}  {r.id:<28} {r.seconds:>6.1f}s  '
              f'tools={",".join(r.tools_called) or "-"}  escalated={r.escalated}')
        for f in r.failures:
            print(f'      - {f}')
    print(f'\n{passed}/{len(results)} passed ({rate:.0%}), gate {args.min_pass_rate:.0%}')
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(
            {'model': llm_model(), 'pass_rate': rate, 'results': [asdict(r) for r in results]},
            indent=2))
    return 0 if rate >= args.min_pass_rate else 1


if __name__ == '__main__':
    sys.exit(main())
