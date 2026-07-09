from core.state import AgentState
from langgraph.types import interrupt
from typing import Dict, Any, List
import copy

def calculate_portfolio_greeks(inventory: List[Dict[str, Any]]) -> Dict[str, float]:
    """Calculates the total aggregated Greeks for the portfolio."""
    tot_delta = 0.0
    tot_gamma = 0.0
    tot_theta = 0.0
    
    for pos in inventory:
        qty = pos["quantity"]
        p_type = pos["type"]
        greeks = pos.get("greeks", {}) or {}
        
        if p_type == "stock":
            # Stock delta is 1.0 per share. Other greeks are 0.
            tot_delta += float(qty)
        elif p_type in ("call", "put"):
            # Option Greeks scale by contract size (100 shares per contract)
            tot_delta += float(qty) * 100.0 * float(greeks.get("delta", 0.0))
            tot_gamma += float(qty) * 100.0 * float(greeks.get("gamma", 0.0))
            tot_theta += float(qty) * 100.0 * float(greeks.get("theta", 0.0))
            
    return {
        "delta": round(tot_delta, 2),
        "gamma": round(tot_gamma, 4),
        "theta": round(tot_theta, 2)
    }

def calculate_margin_requirement(inventory: List[Dict[str, Any]], stock_price: float) -> float:
    """
    Computes total margin required for stock + options positions.
    - Long stock: 50% margin
    - Vertical spreads: (width of spread - net premium) * 100 * contracts
    - Long options: 100% premium paid (cash-secured, no margin leverage)
    - Short naked options: 20% of underlying value
    """
    margin = 0.0
    opt_positions = [p for p in inventory if p["type"] in ("call", "put")]
    stock_positions = [p for p in inventory if p["type"] == "stock"]
    
    # 1. Stock Margin
    for p in stock_positions:
        val = p["quantity"] * stock_price
        margin += max(0.0, val * 0.50) # 50% margin
        
    # 2. Options Margin
    # Group by expiration and option type to detect vertical spreads
    groups = {}
    for p in opt_positions:
        key = (p["expiration_date"], p["type"])
        groups.setdefault(key, []).append(p)
        
    for key, group in groups.items():
        # Sort by strike
        group = sorted(group, key=lambda x: x["strike"])
        
        # If we have a vertical spread (one short leg and one long leg of same quantity)
        if len(group) == 2 and (group[0]["quantity"] * group[1]["quantity"] < 0) and (abs(group[0]["quantity"]) == abs(group[1]["quantity"])):
            short_leg = group[0] if group[0]["quantity"] < 0 else group[1]
            long_leg = group[0] if group[0]["quantity"] > 0 else group[1]
            width = abs(short_leg["strike"] - long_leg["strike"])
            # Premium collected / paid per option spread
            net_prem = short_leg["price"] - long_leg["price"]
            # Margin requirement is maximum risk of the spread: (width - net_premium)
            spread_margin = max(0.0, width - net_prem) * 100 * abs(short_leg["quantity"])
            margin += spread_margin
        else:
            # Naked or separate options legs
            for p in group:
                qty = p["quantity"]
                if qty < 0: # Short Option (naked)
                    # Standard rule of thumb: 20% of underlying contract value
                    margin += 0.20 * stock_price * 100 * abs(qty)
                else: # Long Option
                    margin += p["price"] * 100 * qty
                    
    return margin

def risk_manager_node(state: Dict[str, Any]) -> Dict[str, Any]:
    ticker = state.get("ticker", "SPY")
    price = state.get("price", 0.0)
    inventory = state.get("portfolio_inventory", [])
    target_legs = state.get("target_legs")
    cash = state.get("cash", 100000.0)
    portfolio_equity = state.get("portfolio_equity", 100000.0)
    signal = state.get("signal", "HOLD")
    
    # --- 1. Cancel Stale Orders ---
    open_orders = list(state.get("open_orders", []))
    cancelled_orders = list(state.get("cancelled_orders", []))
    new_open_orders = []
    for order in open_orders:
        if order.get("age_seconds", 0) > 125:
            cancelled_orders.append(order["order_id"])
        else:
            new_open_orders.append(order)
            
    # --- 2. Programmatically Monitor Existing Positions (SL/TP / VIX Shock / BEAR Regime) ---
    liquidations = list(state.get("liquidations", []))
    remaining_inventory = []
    
    vix_price = state.get("vix_price")
    regime = state.get("regime", "BULL")
    defensive_cash_mode = state.get("defensive_cash_mode", False)
    
    vix_shock = vix_price is not None and vix_price > 20.50
    if vix_shock or regime == "BEAR":
        regime = "BEAR"
        defensive_cash_mode = True
        for pos in inventory:
            current_price = pos.get("current_price") if pos.get("current_price") is not None else pos.get("price", 0.0)
            liquidations.append({
                "symbol": pos["symbol"],
                "reason": "VIX_SHOCK" if vix_shock else "BEAR_REGIME",
                "quantity": pos["quantity"],
                "price": current_price
            })
    else:
        for pos in inventory:
            entry_price = pos.get("entry_price") if pos.get("entry_price") is not None else pos.get("price")
            current_price = pos.get("current_price") if pos.get("current_price") is not None else entry_price
            
            unrealized_return = 0.0
            if entry_price and entry_price != 0:
                unrealized_return = (current_price - entry_price) / entry_price
                
            if unrealized_return <= -0.15:
                liquidations.append({
                    "symbol": pos["symbol"],
                    "reason": "STOP_LOSS",
                    "quantity": pos["quantity"],
                    "price": current_price
                })
            elif unrealized_return >= 0.33:
                liquidations.append({
                    "symbol": pos["symbol"],
                    "reason": "TAKE_PROFIT",
                    "quantity": pos["quantity"],
                    "price": current_price
                })
            else:
                remaining_inventory.append(pos)
                
    # --- 3. Intraday Drawdown Breaker ---
    start_of_day_equity = state.get("start_of_day_equity")
    
    drawdown_breaker_triggered = False
    if start_of_day_equity and start_of_day_equity > 0:
        drawdown_pct = (portfolio_equity - start_of_day_equity) / start_of_day_equity
        if drawdown_pct <= -0.05:
            drawdown_breaker_triggered = True
            
    if drawdown_breaker_triggered:
        regime = "BEAR"
        defensive_cash_mode = True
        for pos in remaining_inventory:
            current_price = pos.get("current_price") if pos.get("current_price") is not None else pos.get("price", 0.0)
            liquidations.append({
                "symbol": pos["symbol"],
                "reason": "DRAWDOWN_BREAKER",
                "quantity": pos["quantity"],
                "price": current_price
            })
        remaining_inventory = []
        
    # If drawdown breaker is triggered, reject any proposed trade immediately
    if drawdown_breaker_triggered and signal == "BUY" and target_legs:
        msg = "Order aborted: Intraday drawdown breaker triggered (-5% or worse)."
        return {
            "user_approved": False,
            "is_approved": False,
            "risk_reason": msg,
            "status": msg,
            "portfolio_inventory": remaining_inventory,
            "liquidations": liquidations,
            "regime": regime,
            "defensive_cash_mode": defensive_cash_mode,
            "open_orders": new_open_orders,
            "cancelled_orders": cancelled_orders
        }

    # --- 4. Auto-pass if signal is HOLD or target_legs is empty ---
    if signal == "HOLD" or not target_legs:
        current_greeks = calculate_portfolio_greeks(remaining_inventory)
        current_margin = calculate_margin_requirement(remaining_inventory, price)
        
        # If BEAR regime or defensive cash mode is active, reject approval
        is_appr = not (defensive_cash_mode or regime == "BEAR")
        status_msg = "No trade proposed. Automated risk checks passed." if is_appr else "BEAR/Defensive mode active. Risk checks failed."
        
        return {
            "user_approved": is_appr,
            "is_approved": is_appr,
            "status": status_msg,
            "portfolio_greeks": current_greeks,
            "margin_utilization": current_margin,
            "portfolio_inventory": remaining_inventory,
            "liquidations": liquidations,
            "regime": regime,
            "defensive_cash_mode": defensive_cash_mode,
            "open_orders": new_open_orders,
            "cancelled_orders": cancelled_orders
        }

    # Copy target_legs to scale down if necessary
    target_legs_scaled = copy.deepcopy(target_legs)
    
    # --- 5. Credit Spread Rule ---
    is_credit_spread = False
    if len(target_legs_scaled) == 2:
        leg1, leg2 = target_legs_scaled[0], target_legs_scaled[1]
        if leg1["type"] == leg2["type"] and leg1.get("expiration_date") == leg2.get("expiration_date"):
            is_credit_spread = (leg1["quantity"] * leg2["quantity"] < 0)

    if is_credit_spread:
        short_leg = target_legs_scaled[0] if target_legs_scaled[0]["quantity"] < 0 else target_legs_scaled[1]
        long_leg = target_legs_scaled[0] if target_legs_scaled[0]["quantity"] > 0 else target_legs_scaled[1]
        width = abs(short_leg["strike"] - long_leg["strike"])
        net_credit = short_leg["price"] - long_leg["price"]
        
        if net_credit > 0:
            premium_ratio = net_credit / width if width > 0 else 0.0
            
            print(f"--- RISK EVAL: Credit Spread width is {width}, premium ratio is {premium_ratio:.2%} ---")
            
            if premium_ratio < 0.30:
                msg = f"Order aborted: credit premium collected (${net_credit:.2f}) is below 30% threshold of width ({width:.2f}). Ratio: {premium_ratio:.2%}"
                print(f"--- RISK MANAGER REJECTION: {msg} ---")
                return {
                    "user_approved": False,
                    "is_approved": False,
                    "risk_reason": msg,
                    "status": msg,
                    "portfolio_inventory": remaining_inventory,
                    "liquidations": liquidations,
                    "regime": regime,
                    "defensive_cash_mode": defensive_cash_mode,
                    "open_orders": new_open_orders,
                    "cancelled_orders": cancelled_orders
                }

    # --- 6. Sizing Constraints (2% Capital Rule) ---
    sizing_capital = portfolio_equity * 0.02
    is_stock_trade = len(target_legs_scaled) == 1 and target_legs_scaled[0]["type"] == "stock"
    is_vertical_spread = len(target_legs_scaled) == 2 and target_legs_scaled[0]["type"] in ("call", "put") and target_legs_scaled[1]["type"] in ("call", "put")
    
    if is_stock_trade:
        leg = target_legs_scaled[0]
        leg_price = leg.get("price") if leg.get("price") is not None else price
        max_qty = 0
        if leg_price > 0:
            max_qty = int(sizing_capital / leg_price)
            
        if max_qty <= 0:
            msg = f"Order rejected: 2% capital sizing rule limits quantity to {max_qty} shares (stock price: ${leg_price:.2f}, sizing capital: ${sizing_capital:.2f})"
            return {
                "user_approved": False,
                "is_approved": False,
                "risk_reason": msg,
                "status": msg,
                "portfolio_inventory": remaining_inventory,
                "liquidations": liquidations,
                "regime": regime,
                "defensive_cash_mode": defensive_cash_mode,
                "open_orders": new_open_orders,
                "cancelled_orders": cancelled_orders
            }
        else:
            if abs(leg["quantity"]) > max_qty:
                sign = 1 if leg["quantity"] > 0 else -1
                leg["quantity"] = sign * max_qty
                
    elif is_vertical_spread:
        leg1 = target_legs_scaled[0]
        leg2 = target_legs_scaled[1]
        
        short_leg = leg1 if leg1["quantity"] < 0 else leg2
        long_leg = leg1 if leg1["quantity"] > 0 else leg2
        
        if short_leg["quantity"] < 0 and long_leg["quantity"] > 0:
            width = abs(short_leg["strike"] - long_leg["strike"])
            net_credit = short_leg["price"] - long_leg["price"]
            risk_per_contract = (width - net_credit) * 100
            
            max_contracts = 999999
            if risk_per_contract > 0:
                max_contracts = int(sizing_capital / risk_per_contract)
            else:
                max_contracts = 0
                
            if max_contracts <= 0:
                msg = f"Order rejected: 2% capital sizing rule limits contracts to {max_contracts} (risk per contract: ${risk_per_contract:.2f}, sizing capital: ${sizing_capital:.2f})"
                return {
                    "user_approved": False,
                    "is_approved": False,
                    "risk_reason": msg,
                    "status": msg,
                    "portfolio_inventory": remaining_inventory,
                    "liquidations": liquidations,
                    "regime": regime,
                    "defensive_cash_mode": defensive_cash_mode,
                    "open_orders": new_open_orders,
                    "cancelled_orders": cancelled_orders
                }
            else:
                for leg in target_legs_scaled:
                    if abs(leg["quantity"]) > max_contracts:
                        sign = 1 if leg["quantity"] > 0 else -1
                        leg["quantity"] = sign * max_contracts

    # --- 7. Total stock exposure limit (1.6x Rule) ---
    total_stock_exposure = 0.0
    for pos in remaining_inventory:
        if pos.get("type") == "stock":
            pos_qty = pos.get("quantity", 0)
            pos_price = pos.get("current_price") if pos.get("current_price") is not None else pos.get("price", 0.0)
            total_stock_exposure += abs(pos_qty) * pos_price
            
    for leg in target_legs_scaled:
        if leg.get("type") == "stock":
            leg_qty = leg.get("quantity", 0)
            leg_price = leg.get("price") if leg.get("price") is not None else price
            total_stock_exposure += abs(leg_qty) * leg_price
            
    if total_stock_exposure > 1.6 * portfolio_equity:
        msg = f"Order aborted: total stock exposure (${total_stock_exposure:.2f}) exceeds 1.6x equity limit of ${1.6 * portfolio_equity:.2f}."
        return {
            "user_approved": False,
            "is_approved": False,
            "risk_reason": msg,
            "status": msg,
            "portfolio_inventory": remaining_inventory,
            "liquidations": liquidations,
            "regime": regime,
            "defensive_cash_mode": defensive_cash_mode,
            "open_orders": new_open_orders,
            "cancelled_orders": cancelled_orders
        }

    # --- 8. Simulate proposed portfolio inventory ---
    simulated_inventory = [dict(pos) for pos in remaining_inventory]
    for leg in target_legs_scaled:
        existing = next((pos for pos in simulated_inventory if pos["symbol"] == leg["symbol"]), None)
        if existing:
            existing["quantity"] += leg["quantity"]
            if existing["quantity"] == 0:
                simulated_inventory.remove(existing)
        else:
            simulated_inventory.append({
                "symbol": leg["symbol"],
                "underlying_symbol": leg.get("underlying_symbol", leg.get("symbol", ticker)),
                "type": leg["type"],
                "strike": leg.get("strike"),
                "expiration_date": leg.get("expiration_date"),
                "quantity": leg["quantity"],
                "price": leg["price"],
                "current_price": leg.get("current_price", leg["price"]),
                "greeks": leg.get("greeks")
            })

    # --- 9. Greeks & Margin Calculations for simulated inventory ---
    sim_greeks = calculate_portfolio_greeks(simulated_inventory)
    sim_delta = sim_greeks["delta"]
    print(f"--- RISK EVAL: Simulated Portfolio Delta: {sim_delta} ---")

    sim_margin = calculate_margin_requirement(simulated_inventory, price)
    margin_ratio = sim_margin / portfolio_equity if portfolio_equity > 0 else 0.0
    print(f"--- RISK EVAL: Simulated Margin utilization: ${sim_margin:.2f} ({margin_ratio:.2%}) ---")

    # --- 10. Safety Breaches (Portfolio Delta limits and Margin Utilization limits) ---
    delta_breach = abs(sim_delta) >= 1000.0
    margin_breach = margin_ratio >= 0.80
    
    if (delta_breach or margin_breach) and not state.get("user_approved"):
        reasons = []
        if delta_breach:
            reasons.append(f"Simulated portfolio delta ({sim_delta}) breaches the limit of +/-1000")
        if margin_breach:
            reasons.append(f"Simulated margin requirement (${sim_margin:.2f}) exceeds 80% limit of equity (${portfolio_equity:.2f})")
            
        reason_str = " & ".join(reasons)
        
        # Trigger Human manual override breakpoint
        human_decision = interrupt({
            "action": "MANUAL_APPROVAL_REQUIRED",
            "reason": reason_str,
            "portfolio_delta": sim_delta,
            "margin_requirement": sim_margin,
            "portfolio_equity": portfolio_equity
        })
        
        if human_decision == "approve":
            return {
                "user_approved": True,
                "is_approved": True,
                "portfolio_inventory": simulated_inventory,
                "portfolio_greeks": sim_greeks,
                "margin_utilization": sim_margin,
                "status": "Override granted by user. Trade approved.",
                "target_legs": target_legs_scaled,
                "liquidations": liquidations,
                "regime": regime,
                "defensive_cash_mode": defensive_cash_mode,
                "open_orders": new_open_orders,
                "cancelled_orders": cancelled_orders
            }
        else:
            return {
                "user_approved": False,
                "is_approved": False,
                "risk_reason": f"Aborted: {reason_str}",
                "status": "Order aborted by human supervisor.",
                "portfolio_inventory": remaining_inventory,
                "liquidations": liquidations,
                "regime": regime,
                "defensive_cash_mode": defensive_cash_mode,
                "open_orders": new_open_orders,
                "cancelled_orders": cancelled_orders
            }

    # All checks passed or manual override already granted
    return {
        "user_approved": True,
        "is_approved": True,
        "portfolio_inventory": simulated_inventory,
        "portfolio_greeks": sim_greeks,
        "margin_utilization": sim_margin,
        "status": "Automated risk checks passed.",
        "target_legs": target_legs_scaled,
        "liquidations": liquidations,
        "regime": regime,
        "defensive_cash_mode": defensive_cash_mode,
        "open_orders": new_open_orders,
        "cancelled_orders": cancelled_orders
    }