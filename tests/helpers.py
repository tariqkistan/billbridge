'''A scripted stand-in for the OpenAI client, so the loop is tested without a key.'''
import json
from types import SimpleNamespace
from typing import Any

ToolCall = tuple[str, dict]
Step = str | list[ToolCall]

CUSTOMER = {'msisdn': '0821234567', 'id_last4': '1083', 'date_of_birth': '1985-03-12'}


def _message(step: Step, index: int) -> SimpleNamespace:
    if isinstance(step, str):
        return SimpleNamespace(content=step, tool_calls=None)
    calls = [
        SimpleNamespace(id=f'call_{index}_{n}', type='function',
                        function=SimpleNamespace(name=name, arguments=json.dumps(args)))
        for n, (name, args) in enumerate(step)
    ]
    return SimpleNamespace(content=None, tool_calls=calls)


class FakeLLM:
    '''Returns the scripted steps in order; records every request it receives.'''

    def __init__(self, steps: list[Step]) -> None:
        self.steps = list(steps)
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.requests.append(kwargs)
        if not self.steps:
            raise AssertionError('FakeLLM ran out of scripted steps')
        step = self.steps.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=_message(step, len(self.requests)))])


class LoopingLLM(FakeLLM):
    '''Never stops asking for tools.'''

    async def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.requests.append(kwargs)
        step: Step = [('get_payment_status', {})]
        return SimpleNamespace(choices=[SimpleNamespace(message=_message(step, len(self.requests)))])
