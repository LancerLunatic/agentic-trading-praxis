import pytest
from unittest.mock import MagicMock, patch
from main import app
from core.state import AgentState

# =====================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS (Tests 41-44)
# =====================================================================

def test_combo_bull_ingestion_screening_execution(mock_alpaca_rest, mock_chat_google_genai):
    """41. Verify full BULL market flow from ingestion, screening, risk approval to execution."""
    # Ensure low VIX / low price to pass all screening and risk checks
    # mock_alpaca_rest returns price of 150.0 and SPY 200 SMA of 400.0, which is below SMA
    # mock_chat_google_genai is mocked to return BUY signal
    
    config = {"configurable": {"thread_id": "test_combo_bull"}}
    state_input = {
        "ticker": "AAPL",
        "quantity": 10,
        "cash": 100000.0,
        "portfolio_equity": 100000.0,
        "reflection_count": 0,
        "vix_price": 15.0,  # Low VIX
        "regime": "BULL"
    }
    
    result = app.invoke(state_input, config=config)
    
    # Assert successful traversal of the graph
    assert result.get("signal") == "BUY"
    assert result.get("status") == "COMPLETED"
    assert "successfully bought" in result.get("execution_log", "").lower()

def test_combo_bear_regime_halts_pipeline(mock_alpaca_rest, mock_chat_google_genai):
    """42. Verify high-VIX bear regime halts screening and prevents execution."""
    config = {"configurable": {"thread_id": "test_combo_bear"}}
    state_input = {
        "ticker": "AAPL",
        "quantity": 10,
        "cash": 100000.0,
        "portfolio_equity": 100000.0,
        "reflection_count": 0,
        "vix_price": 25.0,  # High VIX triggers BEAR halt
        "regime": "BULL"
    }
    
    result = app.invoke(state_input, config=config)
    
    # Assert pipeline flagged regime as BEAR, did not approve, and halted execution
    assert result.get("regime") == "BEAR"
    assert result.get("status") != "COMPLETED"
    assert not result.get("user_approved")

def test_combo_high_vix_liquidate_all(mock_alpaca_rest):
    """43. Verify that high VIX mid-run triggers immediate portfolio liquidation."""
    config = {"configurable": {"thread_id": "test_combo_vix_liq"}}
    state_input = {
        "ticker": "AAPL",
        "quantity": 10,
        "cash": 100000.0,
        "portfolio_equity": 100000.0,
        "reflection_count": 0,
        "vix_price": 28.5,  # High VIX shock
        "portfolio_inventory": [
            {"symbol": "AAPL", "type": "stock", "quantity": 100, "price": 100.0, "current_price": 100.0}
        ]
    }
    
    result = app.invoke(state_input, config=config)
    
    # Verify that the high VIX triggers liquidations for all assets
    assert len(result.get("liquidations", [])) > 0
    assert len(result.get("portfolio_inventory", [])) == 0  # Liquidated
    assert result.get("regime") == "BEAR"

def test_combo_risk_violation_corrective_loop(mock_alpaca_rest, mock_chat_google_genai):
    """44. Verify corrector loop: evaluator critique triggers LLM corrector which switches signal to HOLD."""
    config = {"configurable": {"thread_id": "test_combo_corrector_loop"}}
    
    # Set price to 420.0 and SPY 200 SMA to 400.0 so price is above SMA (violates SMA rule)
    mock_trade = MagicMock()
    mock_trade.price = 420.0
    mock_alpaca_rest.get_latest_trade.return_value = mock_trade
    
    mock_bars = MagicMock()
    mock_bars.df = MagicMock(empty=False)
    mock_bars.df.mean.return_value = 400.0
    mock_alpaca_rest.get_bars.return_value = mock_bars
    
    # Setup LLM mock to return BUY first, then HOLD in the corrector loop
    mock_response_buy = MagicMock()
    mock_response_buy.content = (
        '{\n'
        '  "signal": "BUY",\n'
        '  "strategy": "LONG_STOCK",\n'
        '  "reason": "Strong momentum"\n'
        '}'
    )
    mock_response_hold = MagicMock()
    mock_response_hold.content = (
        '{\n'
        '  "signal": "HOLD",\n'
        '  "strategy": "HOLD",\n'
        '  "reason": "Corrected due to SPY 200-SMA technical constraint"\n'
        '}'
    )
    
    mock_chat_google_genai.invoke.side_effect = [mock_response_buy, mock_response_hold]
    
    state_input = {
        "ticker": "SPY",
        "quantity": 10,
        "cash": 100000.0,
        "portfolio_equity": 100000.0,
        "reflection_count": 0
    }
    
    result = app.invoke(state_input, config=config)
    
    # Assert corrector loop finished with HOLD signal after receiving critique
    assert result.get("signal") == "HOLD"
    assert result.get("reflection_count") == 1
    assert "violation" in result.get("evaluation_critique", "").lower() or "passed" in result.get("evaluation_critique", "").lower()
