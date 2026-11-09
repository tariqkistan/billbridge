from openai import AsyncAzureOpenAI, AsyncOpenAI

from billbridge import config


def make_llm() -> AsyncAzureOpenAI | AsyncOpenAI:
    if config.use_azure():
        return AsyncAzureOpenAI(
            azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
            api_key=config.AZURE_OPENAI_KEY,
            api_version=config.AZURE_OPENAI_API_VERSION,
        )
    return AsyncOpenAI(api_key=config.OPENAI_API_KEY)
