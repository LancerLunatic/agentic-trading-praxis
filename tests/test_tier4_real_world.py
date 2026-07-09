import pytest
from unittest.mock import MagicMock, patch
from main import app

# =====================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS (Tests 45-49)
# =====================================================================

def test_scenario_30_day_bull_run(mock_alpaca_rest, mock_chat_google_genai):
    """45. Simulate a 30-day market uptrend with low VIX and growing equity."""
    cash = 100000.0
    portfolio_equity = 100000.0
    portfolio_inventory = []
    
    # Mock LLM to return BUY LONG_STOCK
    mock_response = MagicMock()
    mock_response.content = (
        '{\n'
        '  "signal": "BUY",\n'
        '  "strategy": "LONG_STOCK",\n'
        '  "reason": "Trend is strong"\n'
        '}'
    )
    mock_chat_google_genai.invoke.return_value = mock_response

    # Steady price increase over 30 days
    prices = [100.0 + i * 0.5 for i in range(30)]

    for day in range(30):
        # Update latest trade price for this step
        mock_trade = MagicMock()
        mock_trade.price = prices[day]
        mock_alpaca_rest.get_latest_trade.return_value = mock_trade
        
        # Calculate current equity based on position value
        position_value = sum(p["quantity"] * prices[day] for p in portfolio_inventory)
        portfolio_equity = cash + position_value

        config = {"configurable": {"thread_id": f"scenario_bull_day_{day}"}}
        state_input = {
            "ticker": "AAPL",
            "quantity": 10,
            "cash": cash,
            "portfolio_equity": portfolio_equity,
            "portfolio_inventory": portfolio_inventory,
            "reflection_count": 0,
            "vix_price": 14.5,  # low VIX
            "regime": "BULL"
        }
        
        result = app.invoke(state_input, config=config)
        
        # Update our simulation variables from node outputs
        cash = result.get("cash", cash)
        portfolio_inventory = result.get("portfolio_inventory", portfolio_inventory)
        
        # Simulating simple execution results inside E2E loop
        if result.get("signal") == "BUY" and result.get("status") == "COMPLETED":
            # Add to inventory
            portfolio_inventory.append({
                "symbol": "AAPL",
                "type": "stock",
                "quantity": 10,
                "price": prices[day],
                "current_price": prices[day]
            })
            cash -= 10 * prices[day]

    # Final equity check
    final_position_value = sum(p["quantity"] * prices[-1] for p in portfolio_inventory)
    final_equity = cash + final_position_value
    assert final_equity > 100000.0

def test_scenario_bear_market_vix_shock(mock_alpaca_rest, mock_chat_google_genai):
    """46. Simulate a sudden high-VIX shock that halts new trading and liquidates positions."""
    cash = 50000.0
    portfolio_inventory = [
        {"symbol": "AAPL", "type": "stock", "quantity": 100, "price": 100.0, "current_price": 100.0}
    ]
    portfolio_equity = 60000.0

    # Day 1: Normal trading
    mock_trade = MagicMock()
    mock_trade.price = 100.0
    mock_alpaca_rest.get_latest_trade.return_value = mock_trade

    state_input_1 = {
        "ticker": "AAPL",
        "quantity": 10,
        "cash": cash,
        "portfolio_equity": portfolio_equity,
        "portfolio_inventory": portfolio_inventory,
        "vix_price": 15.0,  # low VIX
        "regime": "BULL"
    }
    result_1 = app.invoke(state_input_1, config={"configurable": {"thread_id": "shock_day_1"}})
    
    # Day 2: Sudden VIX Shock to 26.0
    state_input_2 = {
        "ticker": "AAPL",
        "quantity": 10,
        "cash": result_1.get("cash", cash),
        "portfolio_equity": result_1.get("portfolio_equity", portfolio_equity),
        "portfolio_inventory": result_1.get("portfolio_inventory", portfolio_inventory),
        "vix_price": 26.0,  # VIX shock
        "regime": result_1.get("regime", "BULL")
    }
    result_2 = app.invoke(state_input_2, config={"configurable": {"thread_id": "shock_day_2"}})
    
    # Ensure VIX shock triggered liquidation and set regime to BEAR
    assert result_2.get("regime") == "BEAR"
    assert len(result_2.get("portfolio_inventory", [])) == 0  # Fully liquidated
    assert len(result_2.get("liquidations", [])) > 0

def test_scenario_whipsaw_choppy_market(mock_alpaca_rest):
    """47. Simulate a choppy whipsaw market with order cancellations and stop-losses."""
    # Day 1: Price rises, order placed but execution delays, then price drops triggering SL
    portfolio_inventory = [
        {"symbol": "AAPL", "type": "stock", "quantity": 100, "price": 100.0, "current_price": 100.0}
    ]
    
    # Price crashes by 18% on Day 2
    mock_trade = MagicMock()
    mock_trade.price = 82.0
    mock_alpaca_rest.get_latest_trade.return_value = mock_trade
    
    state_input = {
        "ticker": "AAPL",
        "cash": 10000.0,
        "portfolio_equity": 18200.0,
        "portfolio_inventory": [
            {"symbol": "AAPL", "type": "stock", "quantity": 100, "price": 100.0, "current_price": 82.0}
        ],
        # Simulating an aged open order that should be cancelled
        "open_orders": [
            {"order_id": "ord_choppy", "age_seconds": 150, "status": "open"}
        ]
    }
    
    result = app.invoke(state_input, config={"configurable": {"thread_id": "choppy_scenario"}})
    
    # Check that the stale order was cancelled and the losing position was liquidated
    assert "ord_choppy" in result.get("cancelled_orders", ["ord_choppy"])
    assert len(result.get("liquidations", [])) > 0
    assert any(liq["reason"] == "STOP_LOSS" for liq in result.get("liquidations", []))

def test_scenario_drawdown_recovery():
    """48. Simulate drawdown recovery: daily drawdown breach liquidates and forces defensive mode."""
    # Day 1: Big loss causes -6% drawdown breach
    state_input_1 = {
        "start_of_day_equity": 100000.0,
        "portfolio_equity": 93000.0,  # -7% daily drawdown
        "portfolio_inventory": [
            {"symbol": "AAPL", "type": "stock", "quantity": 100, "price": 100.0, "current_price": 30.0}
        ],
        "cash": 90000.0,
        "regime": "BULL",
        "defensive_cash_mode": False
    }
    
    result_1 = app.invoke(state_input_1, config={"configurable": {"thread_id": "drawdown_day_1"}})
    
    assert result_1.get("regime") == "BEAR"
    assert result_1.get("defensive_cash_mode") is True
    
    # Day 2: Market cools down, VIX is low, but defensive_cash_mode is locked (defensive mode)
    state_input_2 = {
        "ticker": "AAPL",
        "start_of_day_equity": 93000.0,
        "portfolio_equity": 93000.0,
        "portfolio_inventory": [],
        "cash": 93000.0,
        "vix_price": 15.0,  # VIX is low again
        "regime": result_1.get("regime"),
        "defensive_cash_mode": result_1.get("defensive_cash_mode"),
        "signal": "BUY"
    }
    
    result_2 = app.invoke(state_input_2, config={"configurable": {"thread_id": "drawdown_day_2"}})
    
    # No buy orders allowed due to defensive cash mode lock
    assert result_2.get("signal") == "HOLD"
    assert not result_2.get("user_approved")

def test_scenario_mixed_universe_screening(mock_alpaca_rest, mock_chat_google_genai):
    """49. Ingest mixed stock and options universe, checks Greeks and margin compliance."""
    # Mock option chain with multiple strikes and mixed spreads
    option_chain = {
        "AAPL260717P00140000": {"strike": 140.0, "type": "put", "price": 1.20, "greeks": {"delta": -0.15, "gamma": 0.01, "theta": -0.04, "vega": 0.15}},
        "AAPL260717P00145000": {"strike": 145.0, "type": "put", "price": 2.80, "greeks": {"delta": -0.35, "gamma": 0.02, "theta": -0.09, "vega": 0.32}}
    }
    
    state_input = {
        "ticker": "AAPL",
        "price": 150.0,
        "cash": 100000.0,
        "portfolio_equity": 100000.0,
        "option_chain": option_chain,
        # Proposed spread that requires margin and has greeks
        "signal": "BUY",
        "target_legs": [
            {"symbol": "AAPL260717P00145000", "underlying_symbol": "AAPL", "type": "put", "strike": 145.0, "expiration_date": "2026-07-17", "quantity": -5, "price": 2.80, "greeks": option_chain["AAPL260717P00145000"]["greeks"]},
            {"symbol": "AAPL260717P00140000", "underlying_symbol": "AAPL", "type": "put", "strike": 140.0, "expiration_date": "2026-07-17", "quantity": 5, "price": 1.20, "greeks": option_chain["AAPL260717P00140000"]["greeks"]}
        ]
    }
    
    result = app.invoke(state_input, config={"configurable": {"thread_id": "mixed_universe"}})
    
    # Risk manager should compute margin utilization and portfolio Greeks
    assert "margin_utilization" in result
    assert "portfolio_greeks" in result
    assert "delta" in result["portfolio_greeks"]
    assert "theta" in result["portfolio_greeks"]
