import pytest


@pytest.mark.asyncio
async def test_enrichment(tmpdir, api_key_from_config, store_json_column, httpx_mock):
    assert 1 == 1
