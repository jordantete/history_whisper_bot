from unittest.mock import patch
from src.main import main


@patch("src.main.load_dotenv")
@patch("src.main.Database")
@patch("src.main.Bot")
def test_main_wires_and_runs_bot(mock_bot_cls, mock_database_cls, mock_load_dotenv):
    main()

    mock_load_dotenv.assert_called_once()
    mock_database_cls.assert_called_once()
    mock_bot_cls.assert_called_once_with(database=mock_database_cls.return_value)
    mock_bot_cls.return_value.run.assert_called_once()
