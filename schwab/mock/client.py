"""
Mock Schwab client for agent testing.
Returns realistic sample data. Never touches live API or credentials.
"""
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / 'fixtures'


class MockResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self._data


def _load_fixture(name):
    path = FIXTURES / f'{name}.json'
    if path.exists():
        return json.loads(path.read_text())
    return {}


class MockSchwabClient:
    """Drop-in replacement for schwab client. Returns fixture data."""

    def get_quote(self, symbol):
        data = _load_fixture('spx_quote')
        return MockResponse(data)

    def get_quotes(self, symbols):
        data = _load_fixture('spx_quote')
        return MockResponse(data)

    def get_option_chain(self, symbol, **kwargs):
        data = _load_fixture('options_chain')
        return MockResponse(data)

    def get_account_numbers(self):
        return MockResponse([{'accountNumber': 'MOCK-0001', 'hashValue': 'mock'}])


def create_mock_client():
    """Create a mock client. Safe for agent use — no credentials, no network."""
    return MockSchwabClient()
