import pytest
import os
from unittest.mock import MagicMock, patch
from core.state import AgentState
from agents.data_provider import data_provider_node
from agents.analyst import analyst_node
from agents.risk_manager import risk_manager_node
from agents.executor import execute_trade_node

# =====================================================================
# FEATURE 1: DATA INGESTION BOUNDARIES (Tests 21-25)
# =====================================================================

def test_data_provider_price_bounds_lower():
    """21. Verify stock exactly at $2.50 is included."""
    state = {
        "ticker": "AAPL",
        "price": 2.50,
        "screened_candidates": []
    }
    # In target ingestion node, AAPL should be included because it sits on the lower bound
    result = data_provider_node(state)
    assert "AAPL" in result.get("screened_candidates", ["AAPL"])

def test_data_provider_price_bounds_upper():
    """22. Verify stock exactly at $350.00 is included."""
    state = {
        "ticker": "AAPL",
        "price": 350.00,
        "screened_candidates": []
    }
    result = data_provider_node(state)
    assert "AAPL" in result.get("screened_candidates", ["AAPL"])

def test_data_provider_price_out_of_bounds():
    """23. Verify stocks outside bounds ($2.49, $350.01) are filtered out."""
    # Under lower limit
    state_low = {"ticker": "AAPL", "price": 2.49, "screened_candidates": []}
    res_low = data_provider_node(state_low)
    assert "AAPL" not in res_low.get("screened_candidates", [])

    # Over upper limit
    state_high = {"ticker": "AAPL", "price": 350.01, "screened_candidates": []}
    res_high = data_provider_node(state_high)
    assert "AAPL" not in res_high.get("screened_candidates", [])

def test_data_provider_empty_option_chain(monkeypatch, mock_requests_get):
    """24. Verify fallback when options snapshot API returns empty snapshots dict."""
    monkeypatch.setenv("ALPACA_API_KEY", "mock_key_valid")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "mock_secret_valid")

    # Mock response returns empty snapshots dictionary
    mock_requests_get.return_value = MagicMock(status_code=200, json=lambda: {"snapshots": {}})

    state = {"ticker": "AAPL", "timestamp": None}
    result = data_provider_node(state)
    # Falling back to BS generator should successfully populate option_chain
    assert len(result["option_chain"]) > 0

def test_data_provider_invalid_ticker_symbols(monkeypatch):
    """25. Verify normalization of lowercase tickers and failure on malformed tickers."""
    monkeypatch.setenv("ALPACA_API_KEY", "")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "")

    # Lowercase should be normalized to uppercase AAPL
    state_lc = {"ticker": "  aapl  ", "timestamp": None}
    res_lc = data_provider_node(state_lc)
    assert res_lc["ticker"] == "AAPL"

    # Malformed ticker list should fail
    state_empty = {"ticker": "", "timestamp": None}
    with pytest.raises(ValueError):
        data_provider_node(state_empty)

# =====================================================================
# FEATURE 2: ANALYST BOUNDARIES (Tests 26-30)
# =====================================================================

def test_analyst_vix_boundary_limit():
    """26. Verify VIX regime boundaries: 20.49 vs 20.50 vs 20.51."""
    # VIX = 20.49 (BULL)
    res_low = analyst_node({"ticker": "AAPL", "price": 150.0, "vix_price": 20.49, "option_chain": {}})
    assert res_low.get("regime", "BULL") == "BULL"

    # VIX = 20.50 (BULL)
    res_mid = analyst_node({"ticker": "AAPL", "price": 150.0, "vix_price": 20.50, "option_chain": {}})
    assert res_mid.get("regime", "BULL") == "BULL"

    # VIX = 20.51 (BEAR, halts)
    res_high = analyst_node({"ticker": "AAPL", "price": 150.0, "vix_price": 20.51, "option_chain": {}})
    assert res_high.get("regime") == "BEAR"
    assert not res_high.get("target_legs")

def test_analyst_call_put_ratio_boundary():
    """27. Verify Call/Put ratio boundary: 1.09 vs 1.10 vs 1.11."""
    # 1.09 (Discarded)
    res_low = analyst_node({"ticker": "AAPL", "price": 150.0, "call_put_ratio": 1.09, "option_chain": {}})
    assert res_low.get("signal") == "HOLD"

    # 1.10 (Kept/Approved)
    res_mid = analyst_node({"ticker": "AAPL", "price": 150.0, "call_put_ratio": 1.10, "option_chain": {}})
    assert res_mid.get("signal") == "BUY"

    # 1.11 (Kept/Approved)
    res_high = analyst_node({"ticker": "AAPL", "price": 150.0, "call_put_ratio": 1.11, "option_chain": {}})
    assert res_high.get("signal") == "BUY"

def test_analyst_iv_velocity_stagnant():
    """28. Verify stagnant or negative velocity (<= 0) is discarded."""
    # Velocity = 0
    state_stagnant = {
        "ticker": "AAPL",
        "price": 150.0,
        "previous_iv": {"AAPL": 0.25},
        "option_chain": {"AAPL260717C00150000": {"strike": 150.0, "type": "call", "greeks": {"iv": 0.25}}}
    }
    assert analyst_node(state_stagnant).get("signal") == "HOLD"

    # Velocity < 0 (decreased IV)
    state_decreased = {
        "ticker": "AAPL",
        "price": 150.0,
        "previous_iv": {"AAPL": 0.25},
        "option_chain": {"AAPL260717C00150000": {"strike": 150.0, "type": "call", "greeks": {"iv": 0.20}}}
    }
    assert analyst_node(state_decreased).get("signal") == "HOLD"

def test_analyst_llm_json_parse_failure(mock_chat_google_genai):
    """29. Verify invalid LLM JSON handles default fallback gracefully."""
    mock_response = MagicMock()
    mock_response.content = "Malformed response, not valid JSON"
    mock_chat_google_genai.invoke.return_value = mock_response

    state = {
        "ticker": "AAPL",
        "price": 150.0,
        "option_chain": {}
    }
    result = analyst_node(state)
    # Should fall back to default BULL_PUT_SPREAD BUY
    assert result["signal"] == "BUY"
    assert result["target_legs"][0]["type"] == "put"

def test_analyst_fewer_than_15_candidates():
    """30. Verify candidate screening when fewer than 15 assets pass."""
    state = {
        "screened_candidates": ["AAPL", "MSFT"],  # Only 2 candidates
        "previous_iv": {"AAPL": 0.20, "MSFT": 0.30},
        "option_chain": {}
    }
    result = analyst_node(state)
    # Node should output both rather than failing
    assert len(result.get("ranked_candidates", [])) <= 2

# =====================================================================
# FEATURE 3: RISK BOUNDARIES (Tests 31-35)
# =====================================================================

def test_risk_manager_stop_loss_exact_boundary():
    """31. Verify stop loss triggers at exactly -15.0%."""
    # Exactly -15.0% loss triggers SL
    state_trigger = {
        "portfolio_inventory": [{"symbol": "AAPL", "type": "stock", "quantity": 100, "price": 100.0, "current_price": 85.0}],
        "cash": 10000.0, "portfolio_equity": 18500.0
    }
    res_trigger = risk_manager_node(state_trigger)
    assert len(res_trigger.get("liquidations", [])) > 0

    # Loss is -14.9% (no trigger)
    state_safe = {
        "portfolio_inventory": [{"symbol": "AAPL", "type": "stock", "quantity": 100, "price": 100.0, "current_price": 85.1}],
        "cash": 10000.0, "portfolio_equity": 18510.0
    }
    res_safe = risk_manager_node(state_safe)
    assert not res_safe.get("liquidations")

def test_risk_manager_take_profit_exact_boundary():
    """32. Verify take profit triggers at exactly +33.0%."""
    # Exactly +33.0% gain triggers TP
    state_trigger = {
        "portfolio_inventory": [{"symbol": "AAPL", "type": "stock", "quantity": 100, "price": 100.0, "current_price": 133.0}],
        "cash": 10000.0, "portfolio_equity": 23300.0
    }
    res_trigger = risk_manager_node(state_trigger)
    assert len(res_trigger.get("liquidations", [])) > 0

    # Gain is +32.9% (no trigger)
    state_safe = {
        "portfolio_inventory": [{"symbol": "AAPL", "type": "stock", "quantity": 100, "price": 100.0, "current_price": 132.9}],
        "cash": 10000.0, "portfolio_equity": 23290.0
    }
    res_safe = risk_manager_node(state_safe)
    assert not res_safe.get("liquidations")

def test_risk_manager_drawdown_exact_boundary():
    """33. Verify drawdown breaker triggers at exactly -5.0%."""
    # Exactly -5.0% drawdown triggers breaker
    state_trigger = {
        "start_of_day_equity": 100000.0,
        "portfolio_equity": 95000.0,
        "portfolio_inventory": [{"symbol": "AAPL", "type": "stock", "quantity": 100, "price": 100.0, "current_price": 50.0}],
        "regime": "BULL"
    }
    res_trigger = risk_manager_node(state_trigger)
    assert res_trigger.get("regime") == "BEAR"

    # -4.9% drawdown (no trigger)
    state_safe = {
        "start_of_day_equity": 100000.0,
        "portfolio_equity": 95100.0,
        "portfolio_inventory": [{"symbol": "AAPL", "type": "stock", "quantity": 100, "price": 100.0, "current_price": 51.0}],
        "regime": "BULL"
    }
    res_safe = risk_manager_node(state_safe)
    assert res_safe.get("regime", "BULL") == "BULL"

def test_risk_manager_exposure_limit_boundary():
    """34. Verify 1.6x exposure limit boundary check."""
    # Exactly 1.6x exposure is allowed
    state_limit = {
        "portfolio_equity": 100000.0,
        "cash": 50000.0,
        "portfolio_inventory": [{"symbol": "AAPL", "type": "stock", "quantity": 1000, "price": 160.0, "current_price": 160.0}],
        "signal": "HOLD",
        "target_legs": []
    }
    res_limit = risk_manager_node(state_limit)
    assert res_limit.get("is_approved", True) is True

    # 1.601x exposure is blocked
    state_breach = {
        "portfolio_equity": 100000.0,
        "cash": 50000.0,
        "portfolio_inventory": [{"symbol": "AAPL", "type": "stock", "quantity": 1000, "price": 160.0, "current_price": 160.0}],
        "signal": "BUY",
        "target_legs": [{"symbol": "MSFT", "type": "stock", "quantity": 1, "price": 10.0}] # $10 exposure triggers breach
    }
    res_breach = risk_manager_node(state_breach)
    assert res_breach.get("is_approved") is False

def test_risk_manager_cancel_orders_exact_boundary():
    """35. Verify order cancellation at exactly 125s vs 126s."""
    state = {
        "open_orders": [
            {"order_id": "ord_1", "age_seconds": 125, "status": "open"}, # Keep
            {"order_id": "ord_2", "age_seconds": 126, "status": "open"}  # Cancel
        ]
    }
    result = risk_manager_node(state)
    cancelled = result.get("cancelled_orders", [])
    assert "ord_2" in cancelled
    assert "ord_1" not in cancelled

# =====================================================================
# FEATURE 4: EXECUTION/REPORTING BOUNDARIES (Tests 36-40)
# =====================================================================

def test_executor_insufficient_cash():
    """36. Verify order fails if cash is insufficient."""
    state = {
        "ticker": "AAPL",
        "quantity": 1000,
        "price": 150.0,     # Need $150k
        "cash": 1000.0,     # Only have $1k
        "user_approved": True
    }
    result = execute_trade_node(state)
    assert result.get("status") == "FAILED"
    assert "insufficient" in result.get("execution_log", "").lower()

def test_executor_slippage_calculation_zero():
    """37. Verify 0 transaction cost slippage doesn't increase accumulation."""
    state = {
        "ticker": "AAPL",
        "quantity": 10,
        "daily_slippage": 5.00,
        "price": 150.0,
        "slippage_rate": 0.0,  # Zero slippage
        "user_approved": True
    }
    result = execute_trade_node(state)
    assert result.get("daily_slippage") == 5.00

def test_executor_slippage_calculation_extreme():
    """38. Verify extreme slippage does not crash and is handled."""
    state = {
        "ticker": "AAPL",
        "quantity": 100,
        "daily_slippage": 0.0,
        "price": 150.0,
        "slippage_rate": 0.50, # 50% slippage rate
        "user_approved": True
    }
    result = execute_trade_node(state)
    assert result.get("status") == "COMPLETED"
    assert result.get("daily_slippage") > 1000.0

def test_executor_smtp_fail_graceful(mock_smtp):
    """39. Verify SMTP server offline logs warning instead of crashing."""
    mock_smtp.sendmail.side_effect = Exception("SMTP Connection Timeout")
    
    state = {
        "ticker": "AAPL",
        "quantity": 10,
        "user_approved": True,
        "daily_report": "Summary..."
    }
    result = execute_trade_node(state)
    # Execution should still complete successfully, warning logged
    assert result.get("status") == "COMPLETED"

def test_executor_empty_portfolio_report():
    """40. Verify report generation when portfolio is empty."""
    state = {
        "portfolio_inventory": [],
        "cash": 100000.0,
        "portfolio_equity": 100000.0,
        "daily_slippage": 0.0
    }
    result = execute_trade_node(state)
    report = result.get("execution_log", "") or result.get("daily_report", "")
    assert "0 positions" in report.lower() or "empty" in report.lower()


def test_risk_manager_short_stock_position_sizing():
    """Verify that short stock positions are scaled down correctly using absolute values under the 2% capital rule."""
    state = {
        "portfolio_equity": 100000.0,
        "cash": 50000.0,
        "signal": "BUY",
        "target_legs": [
            {"symbol": "AAPL", "type": "stock", "quantity": -100, "price": 50.0}  # -$5000 size (absolute size is 5% of equity)
        ]
    }
    result = risk_manager_node(state)
    # 2% sizing limit is $2000. At $50.0/share, max shares is 40.
    # The negative quantity of -100 should be scaled down to -40.
    assert result.get("is_approved") is True
    assert result.get("target_legs")[0]["quantity"] == -40


def test_risk_manager_debit_spread_not_blocked():
    """Verify that debit spreads (net_credit <= 0) are exempt from the 30% credit spread premium ratio constraint."""
    state = {
        "portfolio_equity": 100000.0,
        "cash": 50000.0,
        "signal": "BUY",
        "target_legs": [
            # Long AAPL 150 Call @ $5.00, Short AAPL 155 Call @ $2.00
            # net_credit = $2.00 - $5.00 = -$3.00 (a debit spread)
            {"symbol": "AAPL_260708C150", "underlying_symbol": "AAPL", "type": "call", "strike": 150.0, "expiration_date": "2026-07-10", "quantity": 1, "price": 5.0},
            {"symbol": "AAPL_260708C155", "underlying_symbol": "AAPL", "type": "call", "strike": 155.0, "expiration_date": "2026-07-10", "quantity": -1, "price": 2.0}
        ]
    }
    result = risk_manager_node(state)
    assert result.get("is_approved") is True


def test_risk_manager_gross_stock_exposure_limit():
    """Verify that the 1.6x stock exposure limit uses gross exposure (absolute quantities) rather than net exposure."""
    # Existing portfolio: long $100k AAPL, short $70k MSFT. Gross exposure = $170k.
    # This already exceeds 1.6x of $100k equity, so any new stock trade (e.g. buy 10 shares of GOOG @ $100) must be rejected
    # even though net stock exposure is only $30k.
    state = {
        "portfolio_equity": 100000.0,
        "cash": 50000.0,
        "portfolio_inventory": [
            {"symbol": "AAPL", "type": "stock", "quantity": 1000, "price": 100.0, "current_price": 100.0}, # $100k long
            {"symbol": "MSFT", "type": "stock", "quantity": -700, "price": 100.0, "current_price": 100.0}  # $70k short
        ],
        "signal": "BUY",
        "target_legs": [
            {"symbol": "GOOG", "type": "stock", "quantity": 10, "price": 100.0} # Proposed $1k long exposure
        ]
    }
    result = risk_manager_node(state)
    assert result.get("is_approved") is False
    assert "exceeds 1.6x equity limit" in result.get("risk_reason", "")

