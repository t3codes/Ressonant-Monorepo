import pytest_asyncio
from common.http import HttpClientRegistry


@pytest_asyncio.fixture
async def registry():
    registry = HttpClientRegistry()
    yield registry
    await registry.aclose()
