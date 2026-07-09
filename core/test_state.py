import unittest
from typing import List, Dict, Any
from core.state import AgentState

class TestAgentState(unittest.TestCase):
    def test_required_fields_exist(self):
        # Retrieve all fields and their types from AgentState
        annotations = AgentState.__annotations__
        
        required_fields = {
            "vix_price": float,
            "regime": str,
            "screened_candidates": List[str],
            "proposed_trades": List[Dict[str, Any]],
            "previous_iv": Dict[str, float],
            "start_of_day_equity": float,
            "daily_slippage": float,
            "liquidations": List[Dict[str, Any]],
            "portfolio_inventory": List[Dict[str, Any]],
            "cash": float,
            "portfolio_equity": float
        }
        
        for field, expected_type in required_fields.items():
            with self.subTest(field=field):
                self.assertIn(field, annotations, f"Field '{field}' is missing from AgentState")
                actual_type = annotations[field]
                
                # Check types structure/names to avoid strict comparison issues with typing generics in different Python versions
                # E.g. List[str] vs typing.List[str]
                self.assertEqual(
                    str(actual_type).replace("typing.", ""), 
                    str(expected_type).replace("typing.", ""), 
                    f"Type mismatch for field '{field}'. Expected {expected_type}, got {actual_type}"
                )

    def test_existing_fields_preserved(self):
        # Verify that original important fields are still present
        annotations = AgentState.__annotations__
        original_fields = [
            "ticker", "signal", "is_approved", "risk_reason", "price", 
            "user_approved", "status", "execution_log", "quantity", 
            "market_data", "analysis_recs", "evaluation_critique", 
            "confidence_score", "risk_approved", "margin_utilization", 
            "portfolio_greeks", "option_chain", "target_legs", 
            "loop_count", "loop_failed", "reflection_count", 
            "spy_200_sma", "current_price", "timestamp"
        ]
        for field in original_fields:
            with self.subTest(field=field):
                self.assertIn(field, annotations, f"Original field '{field}' was not preserved in AgentState")

if __name__ == "__main__":
    unittest.main()
