import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
from unittest.mock import MagicMock, patch

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Load env variables
load_dotenv()

from core.logger import get_logger
from main import app

logger = get_logger("backtest_simulation")

def run_backtest(ticker="SPY", start_date="2022-01-01", end_date="2022-03-01", initial_cash=100000.0):
    logger.info("Starting historical backtest", ticker=ticker, start_date=start_date, end_date=end_date, initial_cash=initial_cash)
    
    # 1. Fetch historical trading days and daily closing prices
    trading_days = []
    historical_prices = {}
    
    import alpaca_trade_api as tradeapi
    from alpaca_trade_api.rest import TimeFrame
    
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    
    use_mock_data = False
    
    # If keys are missing or placeholders, use simulated historical data
    if not api_key or not secret_key or "your_alpaca" in api_key or "your_alpaca" in secret_key:
        logger.warning("No valid Alpaca credentials found in env. Falling back to simulated/mock historical data.")
        use_mock_data = True
    else:
        try:
            api = tradeapi.REST(key_id=api_key, secret_key=secret_key, base_url="https://paper-api.alpaca.markets")
            bars = api.get_bars(ticker.upper(), TimeFrame.Day, start=start_date, end=end_date).df
            if not bars.empty:
                trading_days = [d.strftime("%Y-%m-%d") for d in bars.index]
                historical_prices = {d.strftime("%Y-%m-%d"): float(bars.loc[d, 'close']) for d in bars.index}
            else:
                logger.warning("Alpaca returned empty data. Falling back to mock data.")
                use_mock_data = True
        except Exception as e:
            logger.warning("Alpaca API call failed, falling back to mock data", error=str(e))
            use_mock_data = True

    if use_mock_data:
        # Generate 40 trading days of mock data simulating a regime
        dates = pd.date_range(start=start_date, periods=40, freq='B')
        trading_days = [d.strftime("%Y-%m-%d") for d in dates]
        # Simulate a downward trend (bear market) followed by a recovery
        t = np.linspace(0, 10, len(trading_days))
        prices = 420.0 - 40.0 * np.sin(t / 2.0) + np.random.normal(0, 2.0, len(trading_days))
        historical_prices = {d: float(prices[i]) for i, d in enumerate(trading_days)}

    # 2. Backtest simulation loop
    cash = initial_cash
    shares = 0
    portfolio_history = []
    
    logger.info("Data loaded successfully. Starting agentic loop simulation.", days_count=len(trading_days))
    
    for i, date_str in enumerate(trading_days):
        price = historical_prices[date_str]
        
        # Invoke the LangGraph app with the historical date.
        # We generate a unique thread ID per simulation date to isolate state.
        config = {"configurable": {"thread_id": f"backtest_{ticker}_{date_str}"}}
        
        try:
            # Under mock mode, we intercept Alpaca calls inside the data provider
            if use_mock_data:
                mock_rest_instance = MagicMock()
                
                # Mock latest trade price
                mock_trade = MagicMock()
                mock_trade.price = price
                mock_rest_instance.get_latest_trade.return_value = mock_trade
                
                # Mock historical bars for price & SPY SMA (SMA = 405)
                mock_bars_df = pd.DataFrame({
                    'close': [405.0] * 200
                })
                mock_bars_obj = MagicMock()
                mock_bars_obj.df = mock_bars_df
                mock_rest_instance.get_bars.return_value = mock_bars_obj
                
                with patch('alpaca_trade_api.REST', return_value=mock_rest_instance):
                    result = app.invoke({"ticker": ticker, "quantity": 1, "timestamp": date_str}, config=config)
            else:
                result = app.invoke({"ticker": ticker, "quantity": 1, "timestamp": date_str}, config=config)
                
            signal = result.get("signal", "HOLD")
            confidence = result.get("confidence_score", 1.0)
            critique = result.get("evaluation_critique", "")
            spy_sma = result.get("spy_200_sma", 0.0)
            
        except Exception as e:
            logger.error("Error executing graph step", date=date_str, error=str(e))
            signal = "HOLD"
            confidence = 0.0
            critique = f"Execution error: {str(e)}"
            spy_sma = 0.0
            
        # Execute trade decisions at the close of the day
        equity_before = cash + shares * price
        
        action = "HOLD"
        shares_traded = 0
        
        if signal == "BUY" and cash > 0:
            # Buy as many shares as possible
            shares_traded = int(cash // price)
            if shares_traded > 0:
                shares += shares_traded
                cash -= shares_traded * price
                action = f"BOUGHT {shares_traded} shares"
        elif signal == "SELL" and shares > 0:
            # Sell all shares
            shares_traded = shares
            cash += shares * price
            shares = 0
            action = f"SOLD {shares_traded} shares"
            
        equity_after = cash + shares * price
        
        record = {
            "date": date_str,
            "price": price,
            "spy_200_sma": spy_sma,
            "signal": signal,
            "evaluator_confidence": confidence,
            "critique": critique,
            "action": action,
            "shares": shares,
            "cash": cash,
            "equity": equity_after
        }
        portfolio_history.append(record)
        
        logger.info("Simulation Step Completed", 
                    date=date_str, 
                    price=price, 
                    sma_200=spy_sma, 
                    signal=signal, 
                    action=action, 
                    equity=equity_after)

    # 3. Calculate Performance Metrics
    df = pd.DataFrame(portfolio_history)
    if df.empty:
        logger.error("Simulation generated no results.")
        return
        
    df['equity_returns'] = df['equity'].pct_change().fillna(0)
    
    # Sharpe Ratio (annualized, assuming risk-free rate of 0)
    mean_ret = df['equity_returns'].mean()
    std_ret = df['equity_returns'].std()
    sharpe_ratio = (mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0
    
    # Max Drawdown
    df['peak'] = df['equity'].cummax()
    df['drawdown'] = (df['peak'] - df['equity']) / df['peak']
    max_drawdown = df['drawdown'].max()
    
    # Calculate Correlation between evaluator confidence and profitable trades
    df['next_day_price_change'] = df['price'].shift(-1) - df['price']
    df['next_day_return'] = df['next_day_price_change'] / df['price']
    
    decision_returns = []
    for idx, row in df.iterrows():
        sig = row['signal']
        ret = row['next_day_return']
        if pd.isna(ret):
            decision_returns.append(0.0)
        elif sig == "BUY":
            decision_returns.append(ret)
        elif sig == "SELL":
            decision_returns.append(-ret)
        else:
            decision_returns.append(0.0)
            
    df['decision_return'] = decision_returns
    
    # Compute correlation
    correlation = df['evaluator_confidence'].corr(df['decision_return'])
    if pd.isna(correlation):
        correlation = 0.0
        
    # Print Performance Summary Report
    print("\n" + "="*60)
    print("                 PERFORMANCE SUMMARY REPORT")
    print("="*60)
    print(f"Ticker:                        {ticker}")
    print(f"Date Range:                    {trading_days[0]} to {trading_days[-1]}")
    print(f"Initial Portfolio Value:      ${initial_cash:,.2f}")
    print(f"Final Portfolio Value:        ${df['equity'].iloc[-1]:,.2f}")
    print(f"Total Return:                  {((df['equity'].iloc[-1] - initial_cash) / initial_cash * 100):.2f}%")
    print(f"Annualized Sharpe Ratio:       {sharpe_ratio:.4f}")
    print(f"Max Drawdown:                  {max_drawdown * 100:.2f}%")
    print(f"Evaluator Confidence/Return Corr: {correlation:.4f}")
    print("="*60)
    
    # Save results to a CSV file in the scratch folder for user inspection
    csv_path = "C:/Users/apoll/.gemini/antigravity/brain/543d5a8e-0a33-47a3-9474-a87f235dbc79/scratch/backtest_results.csv"
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    df.to_csv(csv_path, index=False)
    logger.info("Backtest simulation completed. Detailed results saved.", csv_path=csv_path)

if __name__ == "__main__":
    run_backtest()
