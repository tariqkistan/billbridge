import pytest

from billbridge.config import have_real_key, llm_model
from scripts.run_scenarios import check, load_scenarios, run_scenario

SCENARIOS = load_scenarios()


def test_scenarios_file_is_valid():
    ids = [s['id'] for s in SCENARIOS]
    assert len(ids) == len(set(ids))
    assert all(s['turns'] for s in SCENARIOS)


def test_checker_catches_failures():
    from billbridge.session import Session
    session = Session('x', tool_trace=['get_payment_status'], allowed_cents={91050})
    scenario = {'id': 'x', 'expect': {'tools_called': ['verify_identity'], 'escalated': True,
                                      'reply_contains': ['R312,50'],
                                      'reply_excludes': ['R910,50'],
                                      'tools_not_called': ['get_payment_status']}}
    failures = check(scenario, session, ['Your bill is R910,50 and R1,00'])
    assert len(failures) == 6


@pytest.mark.eval
@pytest.mark.skipif(not have_real_key(), reason='needs AZURE_OPENAI_KEY or OPENAI_API_KEY')
@pytest.mark.parametrize('scenario', SCENARIOS, ids=[s['id'] for s in SCENARIOS])
async def test_scenario_against_real_model(scenario):
    from billbridge.llm import make_llm
    result = await run_scenario(scenario, make_llm(), llm_model())
    assert result.passed, '\n'.join(result.failures + result.replies)
