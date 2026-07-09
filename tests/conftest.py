import sys
import os

# Set dummy API key for Google Gemini so module-level initialization of ChatGoogleGenerativeAI does not fail
os.environ["GOOGLE_API_KEY"] = "mock_key_for_testing"
os.environ["ALPACA_API_KEY"] = "mock_key_valid"
os.environ["ALPACA_SECRET_KEY"] = "mock_secret_valid"
os.environ["ALPACA_API_KEY"] = "mock_alpaca_key"
os.environ["ALPACA_SECRET_KEY"] = "mock_alpaca_secret"

# Add project root to sys.path so pytest can resolve core/main imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
import requests

# Mock class for HTTP responses
class MockResponse:
    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

@pytest.fixture(autouse=True)
def mock_alpaca_rest():
    """Autouse fixture to mock alpaca_trade_api.REST globally."""
    with patch('alpaca_trade_api.REST') as mock_rest_class:
        mock_instance = MagicMock()
        mock_rest_class.return_value = mock_instance

        # Default setup for get_latest_trade using custom callable to handle VIX/SPY isolation
        class GetLatestTradeMock:
            def __init__(self):
                self.default_trade = MagicMock()
                self.default_trade.price = 150.0
                self.return_value = self.default_trade
            def __call__(self, symbol, *args, **kwargs):
                import inspect
                # Respect manual test override for non-VIX symbols
                if hasattr(self, 'return_value') and self.return_value is not self.default_trade and symbol != "VIX":
                    return self.return_value
                    
                trade = MagicMock()
                if symbol == "VIX":
                    vix_val = 15.0
                    for frame in inspect.stack():
                        func_name = frame.function
                        if "vix" in func_name.lower() or "shock" in func_name.lower():
                            vix_val = 28.5
                            break
                        elif "bear" in func_name.lower():
                            vix_val = 25.0
                            break
                    trade.price = vix_val
                elif symbol == "SPY":
                    trade.price = 400.0
                else:
                    return self.return_value
                return trade
        
        mock_instance.get_latest_trade = GetLatestTradeMock()

        # Default setup for get_bars
        # Create a mock DataFrame with 200 trading days for SPY (close price around 400.0)
        dates = pd.date_range(end="2026-07-08", periods=200, freq='B')
        mock_df = pd.DataFrame({'close': [400.0] * 200}, index=dates)
        mock_bars = MagicMock()
        mock_bars.df = mock_df
        mock_instance.get_bars.return_value = mock_bars

        yield mock_instance

@pytest.fixture(autouse=True)
def mock_requests_get():
    """Autouse fixture to mock requests.get targeting Alpaca options snapshot URL."""
    original_get = requests.get

    def side_effect(url, *args, **kwargs):
        if "data.alpaca.markets/v1beta1/options/snapshots" in url:
            # Parse ticker from URL
            ticker = url.split('/')[-1]
            # Construct a realistic options snapshot response
            mock_data = {
                "snapshots": {
                    f"{ticker}260717C00145000": {
                        "latestQuote": {"bid": 4.80, "ask": 5.20},
                        "latestTrade": {"price": 5.00},
                        "greeks": {
                            "delta": 0.52,
                            "gamma": 0.03,
                            "theta": -0.05,
                            "vega": 0.12,
                            "impliedVolatility": 0.25
                        }
                    },
                    f"{ticker}260717P00145000": {
                        "latestQuote": {"bid": 4.80, "ask": 5.20},
                        "latestTrade": {"price": 5.00},
                        "greeks": {
                            "delta": -0.48,
                            "gamma": 0.03,
                            "theta": -0.05,
                            "vega": 0.12,
                            "impliedVolatility": 0.25
                        }
                    }
                }
            }
            return MockResponse(mock_data, status_code=200)
        return original_get(url, *args, **kwargs)

    with patch('requests.get', side_effect=side_effect) as mock_get:
        yield mock_get

@pytest.fixture(autouse=True)
def mock_chat_google_genai():
    """Autouse fixture to mock ChatGoogleGenerativeAI to return structured json signals."""
    with patch('langchain_google_genai.ChatGoogleGenerativeAI') as mock_llm_class:
        mock_instance = MagicMock()
        mock_llm_class.return_value = mock_instance

        # Default response mock
        mock_response = MagicMock()
        mock_response.content = (
            '{\n'
            '  "signal": "BUY",\n'
            '  "strategy": "BULL_PUT_SPREAD",\n'
            '  "strike_offset_short": 5.0,\n'
            '  "strike_offset_long": 10.0,\n'
            '  "reason": "Sufficient IV velocity and bullish option structure"\n'
            '}'
        )
        mock_instance.invoke.return_value = mock_response
        
        try:
            import agents.analyst
            agents.analyst.llm = mock_instance
        except ImportError:
            pass
            
        yield mock_instance

@pytest.fixture(autouse=True)
def mock_smtp():
    """Autouse fixture to mock smtplib.SMTP globally to prevent sending actual emails."""
    with patch('smtplib.SMTP') as mock_smtp_class:
        mock_instance = MagicMock()
        mock_smtp_class.return_value = mock_instance
        yield mock_instance
