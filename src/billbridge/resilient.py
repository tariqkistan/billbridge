import asyncio
import random

import httpx

from billbridge.errors import PermanentError, TransientError


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    attempts: int = 3,
    base_delay: float = 0.2,
    **kwargs,
) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        retry_after: float | None = None
        try:
            resp = await client.request(method, url, **kwargs)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = TransientError(f'{type(e).__name__} calling {url}')
        else:
            if resp.status_code == 429 or resp.status_code >= 500:
                last = TransientError(f'HTTP {resp.status_code} from {url}')
                header = resp.headers.get('Retry-After', '')
                if header.replace('.', '', 1).isdigit():
                    retry_after = float(header)
            elif resp.status_code >= 400:
                raise PermanentError(f'HTTP {resp.status_code} from {url}')
            else:
                return resp
        if attempt < attempts:
            if retry_after is not None:
                delay = retry_after
            else:
                delay = base_delay * 2 ** (attempt - 1) + random.uniform(0, base_delay)
            await asyncio.sleep(delay)
    assert last is not None
    raise last
