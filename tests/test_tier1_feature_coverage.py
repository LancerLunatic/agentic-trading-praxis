import pytest
import os
import pandas as pd
from unittest.mock import MagicMock, patch
from core.state import AgentState
from agents.data_provider import data_provider_node
from agents.analyst import analyst_node
from agents.risk_manager import risk_manager_node
from agents.executor import execute_trade_node

# =====================================================================
# FEATURE 1: DATA INGESTION & FALLBACK (Tests 1-5)
# =====================================================================

def test_data_provider_mock_fallback_triggered(monkeypatch):
    """1. Verify mock fallback when keys are missing/invalid."""
    monkeypatch.setenv("ALPACA_API_KEY", "")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "")
    state = {"ticker": "AAPL", "timestamp": None}
    result = data_provider_node(state)
    assert result["price"] == 420.0  # Fallback mock price

def test_data_provider_loads_underlying_price(monkeypatch, mock_alpaca_rest):
    """2. Verify price retrieval using Alpaca REST API."""
    monkeypatch.setenv("ALPACA_API_KEY", "mock_key_valid")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "mock_secret_valid")
    
    mock_trade = MagicMock()
    mock_trade.price = 155.50
    mock_alpaca_rest.get_latest_trade.return_value = mock_trade

    state = {"ticker": "AAPL", "timestamp": None}
    result = data_provider_node(state)
    assert result["price"] == 155.50

def test_data_provider_loads_spy_sma(monkeypatch, mock_alpaca_rest):
    """3. Verify SPY 200 SMA calculation from historical bars."""
    monkeypatch.setenv("ALPACA_API_KEY", "mock_key_valid")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "mock_secret_valid")
    
    mock_df = pd.DataFrame({'close': [100.0] * 200})
    mock_bars = MagicMock()
    mock_bars.df = mock_df
    mock_alpaca_rest.get_bars.return_value = mock_bars

    state = {"ticker": "AAPL", "timestamp": None}
    result = data_provider_node(state)
    assert result["spy_200_sma"] == 100.0

def test_data_provider_generates_option_chain_on_api_fail(monkeypatch, mock_requests_get):
    """4. Verify BS option chain fallback when Alpaca snapshot endpoint fails."""
    monkeypatch.setenv("ALPACA_API_KEY", "mock_key_valid")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "mock_secret_valid")
    
    # Force requests to raise an error
    mock_requests_get.side_effect = Exception("Connection Error")

    state = {"ticker": "AAPL", "timestamp": None}
    result = data_provider_node(state)
    assert len(result["option_chain"]) > 0
    # Checks that BS generator populated greeks
    for key, opt in result["option_chain"].items():
        assert "greeks" in opt
        assert "delta" in opt["greeks"]

def test_data_provider_loads_real_options_chain(monkeypatch):
    """5. Verify parsing of snapshot API response."""
    monkeypatch.setenv("ALPACA_API_KEY", "mock_key_valid")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "mock_secret_valid")
    
    state = {"ticker": "AAPL", "timestamp": None}
    result = data_provider_node(state)
    assert len(result["option_chain"]) > 0
    # conftest mocks return contracts containing 145 strike options
    has_target_contract = any("AAPL" in k and "145000" in k for k in result["option_chain"])
    assert has_target_contract

# =====================================================================
# FEATURE 2: QUANTITATIVE SCREENING & ANALYST (Tests 6-10)
# =====================================================================

def test_analyst_vix_regime_bear_halts():
    """6. Verify VIX > 20.50 sets BEAR and halts screening."""
    state = {
        "ticker": "AAPL",
        "price": 150.0,
        "vix_price": 21.0,
        "option_chain": {},
        "regime": "BULL",
        "screened_candidates": ["AAPL"]
    }
    result = analyst_node(state)
    # The E2E spec dictates high VIX sets regime to BEAR and clears proposed trades / halts
    assert result.get("regime") == "BEAR"
    assert not result.get("target_legs")

def test_analyst_iv_stagnation_discard():
    """7. Verify discarding stagnated/decreased IV assets."""
    state = {
        "ticker": "AAPL",
        "price": 150.0,
        "previous_iv": {"AAPL": 0.30},
        "option_chain": {
            "AAPL260717C00150000": {
                "strike": 150.0,
                "type": "call",
                "greeks": {"iv": 0.29}  # Stagnated IV (0.29 <= 0.30)
            }
        }
    }
    result = analyst_node(state)
    assert result.get("signal") == "HOLD"

def test_analyst_call_put_ratio_filter():
    """8. Verify Call/Put ratio filter >= 1.10."""
    state = {
        "ticker": "AAPL",
        "price": 150.0,
        "call_put_ratio": 1.05,  # below 1.10
        "option_chain": {}
    }
    result = analyst_node(state)
    assert result.get("signal") == "HOLD"

def test_analyst_ranks_by_iv_velocity():
    """9. Verify IV velocity ranking selects top options."""
    state = {
        "screened_candidates": ["AAPL", "MSFT", "GOOG"],
        "previous_iv": {"AAPL": 0.20, "MSFT": 0.30, "GOOG": 0.15},
        "option_chain": {
            # Let MSFT have the highest IV velocity increase
            "MSFT260717C00150000": {"strike": 150.0, "type": "call", "greeks": {"iv": 0.45}}, # Increase 0.15
            "AAPL260717C00150000": {"strike": 150.0, "type": "call", "greeks": {"iv": 0.22}}, # Increase 0.02
        }
    }
    result = analyst_node(state)
    # The highest velocity candidates should be prioritized
    assert "MSFT" in result.get("ranked_candidates", [])

def test_analyst_llm_trade_selection_bull_put_spread(mock_chat_google_genai):
    """10. Verify LLM output parse for BULL_PUT_SPREAD."""
    mock_response = MagicMock()
    mock_response.content = (
        '{\n'
        '  "signal": "BUY",\n'
        '  "strategy": "BULL_PUT_SPREAD",\n'
        '  "strike_offset_short": 5.0,\n'
        '  "strike_offset_long": 10.0,\n'
        '  "reason": "Structured credit spread"\n'
        '}'
    )
    mock_chat_google_genai.invoke.return_value = mock_response

    state = {
        "ticker": "AAPL",
        "price": 150.0,
        "option_chain": {}
    }
    result = analyst_node(state)
    assert result["signal"] == "BUY"
    assert len(result["target_legs"]) == 2
    assert result["target_legs"][0]["type"] == "put"
    assert result["target_legs"][1]["type"] == "put"

# =====================================================================
# FEATURE 3: RISK & PORTFOLIO GUARDRAILS (Tests 11-15)
# =====================================================================

def test_risk_manager_stop_loss_trigger():
    """11. Verify stop loss liquidation triggers below -15.0%."""
    state = {
        "portfolio_inventory": [
            {
                "symbol": "AAPL",
                "type": "stock",
                "quantity": 100,
                "price": 100.0,        # Entry price
                "current_price": 84.0  # -16% drop
            }
        ],
        "cash": 10000.0,
        "portfolio_equity": 18400.0
    }
    result = risk_manager_node(state)
    assert len(result.get("liquidations", [])) > 0
    assert result["liquidations"][0]["reason"] == "STOP_LOSS"

def test_risk_manager_take_profit_trigger():
    """12. Verify take profit liquidation triggers above +33.0%."""
    state = {
        "portfolio_inventory": [
            {
                "symbol": "AAPL",
                "type": "stock",
                "quantity": 100,
                "price": 100.0,         # Entry price
                "current_price": 134.0  # +34% gain
            }
        ],
        "cash": 10000.0,
        "portfolio_equity": 23400.0
    }
    result = risk_manager_node(state)
    assert len(result.get("liquidations", [])) > 0
    assert result["liquidations"][0]["reason"] == "TAKE_PROFIT"

def test_risk_manager_drawdown_breaker():
    """13. Verify -5% daily drawdown breaker triggers BEAR and liquidates."""
    state = {
        "start_of_day_equity": 100000.0,
        "portfolio_equity": 94000.0,  # -6% drawdown
        "portfolio_inventory": [
            {"symbol": "AAPL", "type": "stock", "quantity": 100, "price": 100.0, "current_price": 80.0}
        ],
        "regime": "BULL"
    }
    result = risk_manager_node(state)
    assert result.get("regime") == "BEAR"
    assert len(result.get("liquidations", [])) > 0

def test_risk_manager_position_sizing_limit():
    """14. Verify 2% sizing rule limits position size."""
    state = {
        "portfolio_equity": 100000.0,
        "cash": 50000.0,
        "signal": "BUY",
        "target_legs": [
            {"symbol": "AAPL", "type": "stock", "quantity": 100, "price": 50.0}  # $5000 size (5% of equity)
        ]
    }
    result = risk_manager_node(state)
    # Sizing limit should scale quantity down to $2000 max (40 shares) or reject
    assert result.get("is_approved") is False or result.get("target_legs")[0]["quantity"] <= 40

def test_risk_manager_exposure_limit():
    """15. Verify 1.6x total exposure limit prevents new positions."""
    state = {
        "portfolio_equity": 100000.0,
        "cash": 50000.0,
        "portfolio_inventory": [
            {"symbol": "AAPL", "type": "stock", "quantity": 1000, "price": 160.0, "current_price": 160.0} # $160k exposure (1.6x)
        ],
        "signal": "BUY",
        "target_legs": [
            {"symbol": "MSFT", "type": "stock", "quantity": 10, "price": 200.0} # Proposed $2k exposure
        ]
    }
    result = risk_manager_node(state)
    assert result.get("is_approved") is False

# =====================================================================
# FEATURE 4: EXECUTION & DAILY REPORTING (Tests 16-20)
# =====================================================================

def test_executor_executes_valid_trade(mock_alpaca_rest):
    """16. Verify order submission when approved."""
    state = {
        "ticker": "AAPL",
        "quantity": 10,
        "user_approved": True,
        "signal": "BUY"
    }
    result = execute_trade_node(state)
    assert result.get("status") == "COMPLETED"

def test_executor_slippage_accumulation():
    """17. Verify transaction slippage accumulation."""
    state = {
        "ticker": "AAPL",
        "quantity": 100,
        "daily_slippage": 12.50,
        "user_approved": True,
        "price": 150.0
    }
    result = execute_trade_node(state)
    # The E2E execution should record transaction slippage and add it to daily_slippage
    assert result.get("daily_slippage", 12.50) > 12.50

def test_executor_report_generation():
    """18. Verify report logging format is correct."""
    state = {
        "portfolio_inventory": [{"symbol": "AAPL", "quantity": 100}],
        "cash": 50000.0,
        "portfolio_equity": 150000.0,
        "daily_slippage": 15.0
    }
    result = execute_trade_node(state)
    # Expect daily report text/log in state
    report = result.get("execution_log", "") or result.get("daily_report", "")
    assert "portfolio" in report.lower()
    assert "slippage" in report.lower()

def test_executor_email_notification_smtp(mock_smtp):
    """19. Verify email dispatch is called."""
    state = {
        "ticker": "AAPL",
        "quantity": 10,
        "user_approved": True,
        "daily_report": "Daily summary report..."
    }
    execute_trade_node(state)
    # Ensure SMTP mock has been called
    assert mock_smtp.sendmail.called or mock_smtp.send_message.called or mock_smtp().sendmail.called

def test_executor_order_cancellation(mock_alpaca_rest):
    """20. Verify cancelling orders older than 125s."""
    state = {
        "open_orders": [
            {"order_id": "ord_1", "age_seconds": 130, "status": "open"},
            {"order_id": "ord_2", "age_seconds": 120, "status": "open"}
        ]
    }
    # In execution/risk checking, order 1 should be cancelled
    result = execute_trade_node(state) or risk_manager_node(state)
    cancelled_orders = result.get("cancelled_orders", [])
    assert "ord_1" in cancelled_orders
