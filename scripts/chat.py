'''Chat with the agent in the terminal, against the in-process simulator.

    python -m scripts.chat                 # needs a model key
    python -m scripts.chat --fault flaky   # crm_down | flaky
'''
import argparse
import asyncio
import sys
import uuid

import httpx

from billbridge.agent import run_turn
from billbridge.api import build_toolbox
from billbridge.config import have_real_key, llm_model
from billbridge.llm import make_llm
from billbridge.session import Session
from legacy_sim import app as sim


async def chat(fault: str) -> None:
    sim.app.state.fault_mode = fault
    session = Session(session_id=f'cli-{uuid.uuid4().hex[:8]}')
    llm, model = make_llm(), llm_model()
    transport = httpx.ASGITransport(app=sim.app)
    async with httpx.AsyncClient(transport=transport, base_url='http://legacy') as http:
        tools = build_toolbox(http)
        print(f'Karoo Mobile billing assistant (session {session.session_id}). Ctrl-D to quit.')
        print('Test customer: 0821234567, ID last 4 1083, DOB 1985-03-12\n')
        while True:
            try:
                message = input('you> ').strip()
            except EOFError:
                break
            if not message:
                continue
            result = await run_turn(session, message, llm, tools, model=model)
            print(f'bot> {result.reply}')
            print(f'     [tools={",".join(result.tools_called) or "-"} '
                  f'escalated={result.escalated} ticket={result.ticket_ref}]\n')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fault', default='none', choices=['none', 'crm_down', 'flaky'])
    args = parser.parse_args()
    if not have_real_key():
        print('No model key configured (AZURE_OPENAI_KEY or OPENAI_API_KEY). See .env.example.')
        return 2
    asyncio.run(chat(args.fault))
    return 0


if __name__ == '__main__':
    sys.exit(main())
