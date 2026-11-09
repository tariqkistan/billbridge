import os

from dotenv import load_dotenv

load_dotenv()

AZURE_OPENAI_ENDPOINT = os.environ.get('AZURE_OPENAI_ENDPOINT', 'https://fake.openai.azure.com/')
AZURE_OPENAI_KEY = os.environ.get('AZURE_OPENAI_KEY', 'fake-key')
AZURE_OPENAI_DEPLOYMENT = os.environ.get('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o')
AZURE_OPENAI_API_VERSION = os.environ.get('AZURE_OPENAI_API_VERSION', '2024-06-01')
LEGACY_BASE_URL = os.environ.get('LEGACY_BASE_URL', 'http://localhost:9000')
EVENTS_DB = os.environ.get('EVENTS_DB', './billbridge_events.db')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o')
MAX_TOOL_STEPS = int(os.environ.get('MAX_TOOL_STEPS', '6'))
MAX_VERIFY_ATTEMPTS = 3


def have_real_key() -> bool:
    return AZURE_OPENAI_KEY != 'fake-key' or bool(OPENAI_API_KEY)


def use_azure() -> bool:
    '''Azure OpenAI is the default; a plain OpenAI key is a fallback for local runs.'''
    return AZURE_OPENAI_KEY != 'fake-key' or not OPENAI_API_KEY


def llm_model() -> str:
    return AZURE_OPENAI_DEPLOYMENT if use_azure() else OPENAI_MODEL
