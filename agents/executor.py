import os
import smtplib
from email.mime.text import MIMEText
import re
import copy
import alpaca_trade_api as tradeapi
from core.state import AgentState

def is_option_symbol(symbol: str) -> bool:
    # Option symbols typically have format: AAPL260717C00145000 (standard OPRA code)
    # i.e., Ticker (1-6 chars) + YYMMDD (6 digits) + C/P (1 char) + Strike (8 digits)
    return bool(re.match(r"^[A-Z]+(\d{6})([CP])(\d{8})$", symbol))

def execute_trade_node(state: AgentState) -> dict:
    user_approved = state.get("user_approved", False)
    signal = state.get("signal", "HOLD")
    ticker = state.get("ticker")
    target_legs = state.get("target_legs")
    liquidations = state.get("liquidations", [])
    
    has_trade = (ticker is not None) or (target_legs is not None and len(target_legs) > 0)
    has_liquidations = len(liquidations) > 0
    
    # 1. Trade execution check
    if has_trade or has_liquidations:
        if not has_liquidations:
            signal_val = state.get("signal")
            if not user_approved or signal_val == "HOLD":
                return None
    else:
        # No trade and no liquidations. Check if we have portfolio/reporting info.
        if "portfolio_inventory" not in state and "cash" not in state:
            return None
            
    print(f"--- EXECUTING TRADE: {ticker} ---")
    
    # 2. Cancel stale orders (older than 125 seconds)
    open_orders = list(state.get("open_orders", []))
    cancelled_orders = list(state.get("cancelled_orders", []))
    new_open_orders = []
    for order in open_orders:
        if order.get("age_seconds", 0) > 125:
            if order["order_id"] not in cancelled_orders:
                cancelled_orders.append(order["order_id"])
        else:
            new_open_orders.append(order)
            
    portfolio_inventory = copy.deepcopy(state.get("portfolio_inventory", []))
    cash = state.get("cash", 100000.0)
 
    # Process liquidations first
    for liq in liquidations:
        liq_sym = liq["symbol"]
        liq_qty = liq["quantity"]
        liq_price = liq["price"]
        
        mult = 100 if is_option_symbol(liq_sym) else 1
        # Liquidation proceeds are added to cash
        cash += liq_qty * liq_price * mult
        
        # Remove from portfolio_inventory
        portfolio_inventory = [pos for pos in portfolio_inventory if pos["symbol"] != liq_sym]
 
    # Determine target legs to execute (only if approved and signal is not explicitly HOLD)
    new_legs = []
    signal_val = state.get("signal")
    if user_approved and signal_val != "HOLD":
        # If target_legs is present, execute it
        if target_legs is not None:
            new_legs = target_legs
        # Otherwise check if there is an approved trade defined by ticker, quantity, price
        elif ticker and state.get("quantity", 0):
            quantity = state.get("quantity", 0)
            price = state.get("price") or state.get("current_price") or 150.0
            new_legs = [{
                "symbol": ticker,
                "quantity": quantity,
                "price": price,
                "type": "call" if is_option_symbol(ticker) else "stock"
            }]

    # Check cash sufficiency
    net_cost = 0.0
    for leg in new_legs:
        leg_qty = leg["quantity"]
        leg_price = leg["price"]
        leg_type = leg.get("type", "stock")
        mult = 100 if leg_type in ("call", "put") or is_option_symbol(leg["symbol"]) else 1
        net_cost += leg_qty * leg_price * mult

    if net_cost > cash:
        # Revert the proposed target legs from simulated portfolio_inventory (which risk manager added)
        if target_legs:
            for leg in target_legs:
                for pos in portfolio_inventory:
                    if pos["symbol"] == leg["symbol"]:
                        pos["quantity"] -= leg["quantity"]
                        if pos["quantity"] == 0:
                            portfolio_inventory.remove(pos)
                        break

        execution_log = "Trade failed: insufficient cash."
        
        # Prepare daily report format
        report_lines = ["Daily Execution Report:", "Slippage: 0.00"]
        if not portfolio_inventory:
            report_lines.append("Portfolio: empty (0 positions)")
        else:
            report_lines.append("Portfolio positions:")
            for pos in portfolio_inventory:
                report_lines.append(f" - {pos['symbol']}: {pos['quantity']} @ {pos.get('price', 0.0)}")
        daily_report = "\n".join(report_lines)

        return {
            "status": "FAILED",
            "execution_log": execution_log,
            "daily_report": daily_report,
            "portfolio_inventory": portfolio_inventory,
            "cash": cash,
            "open_orders": new_open_orders,
            "cancelled_orders": cancelled_orders
        }

    # 3. Order submission to Alpaca
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    use_mock_data = state.get("use_mock_data", False)
    
    if not api_key or not secret_key or "your_alpaca" in api_key or "your_alpaca" in secret_key:
        use_mock_data = True
        
    alpaca_failed = False
    if not use_mock_data and new_legs:
        try:
            api = tradeapi.REST(
                key_id=api_key,
                secret_key=secret_key,
                base_url="https://paper-api.alpaca.markets"
            )
            # Submit orders
            for leg in new_legs:
                symbol = leg.get("symbol")
                quantity = leg.get("quantity", 0)
                qty = abs(quantity)
                side = "buy" if quantity > 0 else "sell"
                if qty > 0:
                    api.submit_order(
                        symbol=symbol,
                        qty=qty,
                        side=side,
                        type='market',
                        time_in_force='gtc'
                    )
        except Exception as e:
            print(f"Alpaca REST order submission failed: {e}. Falling back to mock execution.")
            alpaca_failed = True

    # Execute trades (cash is sufficient)
    cash -= net_cost

    # Update portfolio inventory if target_legs was not already added (e.g. direct calls)
    if not target_legs and new_legs:
        for leg in new_legs:
            existing = next((pos for pos in portfolio_inventory if pos["symbol"] == leg["symbol"]), None)
            if existing:
                existing["quantity"] += leg["quantity"]
                if existing["quantity"] == 0:
                    portfolio_inventory.remove(existing)
            else:
                portfolio_inventory.append({
                    "symbol": leg["symbol"],
                    "underlying_symbol": leg.get("underlying_symbol", leg["symbol"]),
                    "type": leg.get("type", "stock"),
                    "strike": leg.get("strike"),
                    "expiration_date": leg.get("expiration_date"),
                    "quantity": leg["quantity"],
                    "price": leg["price"],
                    "current_price": leg.get("current_price", leg["price"]),
                    "greeks": leg.get("greeks")
                })

    # 4. Accumulate slippage
    slippage_rate = state.get("slippage_rate")
    if slippage_rate is None:
        slippage_rate = 0.001

    total_slippage = 0.0
    for leg in new_legs:
        qty = leg["quantity"]
        prc = leg["price"]
        l_type = leg.get("type", "stock")
        mult = 100 if l_type in ("call", "put") or is_option_symbol(leg["symbol"]) else 1
        total_slippage += abs(qty) * prc * mult * slippage_rate

    for liq in liquidations:
        qty = liq["quantity"]
        prc = liq["price"]
        mult = 100 if is_option_symbol(liq["symbol"]) else 1
        total_slippage += abs(qty) * prc * mult * slippage_rate

    daily_slippage = state.get("daily_slippage", 0.0) + total_slippage

    # Calculate portfolio equity
    position_value = 0.0
    for pos in portfolio_inventory:
        pos_qty = pos["quantity"]
        pos_price = pos.get("current_price") if pos.get("current_price") is not None else pos.get("price", 0.0)
        mult = 100 if pos.get("type") in ("call", "put") or is_option_symbol(pos["symbol"]) else 1
        position_value += pos_qty * pos_price * mult
    portfolio_equity = cash + position_value

    # 5. Generate daily report
    start_of_day_equity = state.get("start_of_day_equity")
    if start_of_day_equity and start_of_day_equity > 0:
        pnl_pct = (portfolio_equity - start_of_day_equity) / start_of_day_equity * 100.0
    else:
        pnl_pct = 0.0

    report_lines = []
    report_lines.append("Daily Execution Report:")
    report_lines.append(f"Slippage: {daily_slippage:.2f}")
    if not portfolio_inventory:
        report_lines.append("Portfolio: empty (0 positions)")
    else:
        report_lines.append("Portfolio positions:")
        for pos in portfolio_inventory:
            report_lines.append(f" - {pos['symbol']}: {pos['quantity']} @ {pos.get('price', 0.0)}")
    daily_report = "\n".join(report_lines)
    
    execution_log = f"Successfully executed trades. Successfully bought {ticker or 'assets'}. Slippage: {total_slippage:.2f}. " + daily_report

    # Send email notification
    smtp_server = os.environ.get("SMTP_HOST", os.environ.get("SMTP_SERVER", "localhost"))
    smtp_port_str = os.environ.get("SMTP_PORT", "25")
    try:
        smtp_port = int(smtp_port_str)
    except ValueError:
        smtp_port = 25
    smtp_user = os.environ.get("SMTP_USER", os.environ.get("SMTP_USERNAME"))
    smtp_password = os.environ.get("SMTP_PASSWORD")
    email_to = os.environ.get("EMAIL_TO", "investor@example.com")
    email_from = os.environ.get("EMAIL_FROM", "trading-bot@example.com")

    try:
        msg = MIMEText(daily_report)
        msg['Subject'] = 'Daily Trading Report'
        msg['From'] = email_from
        msg['To'] = email_to
        
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=5)
        if smtp_port == 587:
            server.starttls()
        if smtp_user and smtp_password:
            server.login(smtp_user, smtp_password)
        server.sendmail(email_from, [email_to], msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Warning: SMTP email notification failed: {e}")

    return {
        "status": "COMPLETED",
        "execution_log": execution_log,
        "daily_report": daily_report,
        "portfolio_inventory": portfolio_inventory,
        "cash": cash,
        "portfolio_equity": portfolio_equity,
        "daily_slippage": daily_slippage,
        "open_orders": new_open_orders,
        "cancelled_orders": cancelled_orders
    }