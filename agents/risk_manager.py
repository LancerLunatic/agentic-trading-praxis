from core.state import AgentState
from langgraph.types import interrupt
from typing import Dict, Any, List

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
    
    # Auto-pass if signal is HOLD or target_legs is empty
    if signal == "HOLD" or not target_legs:
        current_greeks = calculate_portfolio_greeks(inventory)
        current_margin = calculate_margin_requirement(inventory, price)
        return {
            "user_approved": True,
            "status": "No trade proposed. Automated risk checks passed.",
            "portfolio_greeks": current_greeks,
            "margin_utilization": current_margin
        }

    # 1. Detect and Evaluate Credit Spread rule (premium collected must be >= 30% of spread width)
    # Check if target_legs is a vertical credit spread
    is_credit_spread = False
    if len(target_legs) == 2:
        leg1, leg2 = target_legs[0], target_legs[1]
        if leg1["type"] == leg2["type"] and leg1["expiration_date"] == leg2["expiration_date"]:
            is_credit_spread = (leg1["quantity"] * leg2["quantity"] < 0)

    if is_credit_spread:
        short_leg = target_legs[0] if target_legs[0]["quantity"] < 0 else target_legs[1]
        long_leg = target_legs[0] if target_legs[0]["quantity"] > 0 else target_legs[1]
        width = abs(short_leg["strike"] - long_leg["strike"])
        net_credit = short_leg["price"] - long_leg["price"]
        
        premium_ratio = net_credit / width if width > 0 else 0.0
        
        print(f"--- RISK EVAL: Credit Spread width is {width}, premium ratio is {premium_ratio:.2%} ---")
        
        if premium_ratio < 0.30:
            msg = f"Order aborted: credit premium collected (${net_credit:.2f}) is below 30% threshold of width ({width:.2f}). Ratio: {premium_ratio:.2%}"
            print(f"--- RISK MANAGER REJECTION: {msg} ---")
            return {
                "user_approved": False,
                "is_approved": False,
                "risk_reason": msg,
                "status": msg
            }

    # 2. Simulate proposed portfolio inventory with the new target legs added
    simulated_inventory = list(inventory)
    for leg in target_legs:
        # Check if already exists to adjust quantity, or append
        existing = next((pos for pos in simulated_inventory if pos["symbol"] == leg["symbol"]), None)
        if existing:
            existing["quantity"] += leg["quantity"]
            if existing["quantity"] == 0:
                simulated_inventory.remove(existing)
        else:
            simulated_inventory.append({
                "symbol": leg["symbol"],
                "underlying_symbol": leg["underlying_symbol"],
                "type": leg["type"],
                "strike": leg["strike"],
                "expiration_date": leg["expiration_date"],
                "quantity": leg["quantity"],
                "price": leg["price"],
                "current_price": leg["price"],
                "greeks": leg.get("greeks")
            })

    # 3. Calculate portfolio Greeks for simulated inventory
    sim_greeks = calculate_portfolio_greeks(simulated_inventory)
    sim_delta = sim_greeks["delta"]
    print(f"--- RISK EVAL: Simulated Portfolio Delta: {sim_delta} ---")

    # 4. Calculate Margin Requirement for simulated inventory
    sim_margin = calculate_margin_requirement(simulated_inventory, price)
    margin_ratio = sim_margin / portfolio_equity if portfolio_equity > 0 else 0.0
    print(f"--- RISK EVAL: Simulated Margin utilization: ${sim_margin:.2f} ({margin_ratio:.2%}) ---")

    # 5. Check Safety Breaches (Portfolio Delta limits and Margin Utilization limits)
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
                "status": "Override granted by user. Trade approved."
            }
        else:
            return {
                "user_approved": False,
                "is_approved": False,
                "risk_reason": f"Aborted: {reason_str}",
                "status": "Order aborted by human supervisor."
            }

    # All checks passed or manual override already granted
    return {
        "user_approved": True,
        "is_approved": True,
        "portfolio_inventory": simulated_inventory,
        "portfolio_greeks": sim_greeks,
        "margin_utilization": sim_margin,
        "status": "Automated risk checks passed."
    }