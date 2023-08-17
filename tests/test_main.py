import pytest
from unittest.mock import Mock, patch
from main import main, OK_RESPONSE, ERROR_RESPONSE
from tests.mocks import MockBot, MockDatabase, MockLogger

def mock_get_event_loop():
    loop = asyncio.new_event_loop()
    loop.run_until_complete = asyncio.coroutine(lambda _: None)
    return loop

@pytest.mark.asyncio
async def test_main_successful_execution():
    mock_event = {"body": {"text": "Coucou"}}

    with patch('main.Database', MockDatabase), patch('main.Bot', return_value=MockBot()), patch('main.LOGGER', MockLogger), patch('main.asyncio.get_event_loop', mock_get_event_loop):
        response = await main(event=mock_event)

    assert response == OK_RESPONSE

@pytest.mark.asyncio
async def test_main_exception():
    mock_event = {"body": {"text": "Coucou"}}

    with patch('main.Database', MockDatabase), patch('main.Bot', return_value=MockBot), patch('main.LOGGER', MockLogger), patch('main.asyncio.get_event_loop', mock_get_event_loop):
        # Raise an exception to simulate an error
        MockBot.start.side_effect = Exception()
        response = await main(event=mock_event)

    assert response == ERROR_RESPONSE