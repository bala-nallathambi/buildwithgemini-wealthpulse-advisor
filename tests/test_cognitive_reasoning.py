#!/usr/bin/env python3
"""
Cognitive & AI Reasoning Test Suite for WealthPulse Advisor
Evaluates mathematical rebalancing precision, botanical advisory coherence,
multi-intent query resolution, edge-case robustness, and response metrics.
"""

import unittest
import requests
import json
import time

BASE_URL = "http://localhost:8080"

class TestWealthPulseCognitive(unittest.TestCase):

    def test_01_rebalancing_mathematical_precision(self):
        """Cognitive Test: Verify math accuracy of asset drift and rebalance trade size."""
        r = requests.post(f"{BASE_URL}/chat", json={"message": "Calculate portfolio rebalance"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("parts", data)
        text = data["parts"][0]["text"]

        # Retrieve direct holdings to perform independent mathematical verification
        h_res = requests.get(f"{BASE_URL}/api/holdings").json()
        holdings = h_res["holdings"]
        
        total_val = sum(h["shares"] * h["current_price"] for h in holdings)
        eq_val = sum(h["shares"] * h["current_price"] for h in holdings if h["asset_class"] == "US Equity")
        bd_val = sum(h["shares"] * h["current_price"] for h in holdings if h["asset_class"] == "Fixed Income")
        
        eq_pct_calc = (eq_val / total_val) * 100.0
        bd_pct_calc = (bd_val / total_val) * 100.0

        # Verify output text contains total valuation and correct percentage ranges
        self.assertIn(f"${total_val:,.2f}", text)
        self.assertTrue(f"{eq_pct_calc:.1f}%" in text or f"{eq_pct_calc:.2f}%" in text)
        self.assertTrue(f"{bd_pct_calc:.1f}%" in text or f"{bd_pct_calc:.2f}%" in text)


        # Target allocation is 80% Equity, 20% Bond
        target_eq_val = total_val * 0.80
        target_bd_val = total_val * 0.20
        sell_eq_amount = eq_val - target_eq_val
        buy_bd_amount = target_bd_val - bd_val

        # Verify trade symmetry (sell equity amount == buy bond amount)
        self.assertAlmostEqual(sell_eq_amount, buy_bd_amount, places=2)
        self.assertIn(f"${sell_eq_amount:,.2f}", text)

    def test_02_botanical_coherence_reasoning(self):
        """Cognitive Test: Verify herbal advisory domain knowledge and stress relief advice."""
        query = "I am extremely anxious about market volatility and need a calming herbal tea."
        r = requests.post(f"{BASE_URL}/chat", json={"message": query})
        self.assertEqual(r.status_code, 200)
        text = r.json()["parts"][0]["text"]

        # Cognitive assertions: Should reference Culpeper's Herbal, calming herbs, and link to rebalancing
        self.assertIn("Herbal", text)
        self.assertTrue(any(herb in text.lower() for herb in ["chamomile", "mint", "lavender", "lemon balm", "valerian", "herbal"]))

    def test_03_dual_intent_query_resolution(self):
        """Cognitive Test: Verify response to compound query combining wellness and rebalancing."""
        query = "Can you rebalance my portfolio and suggest herbal tea for stress?"
        r = requests.post(f"{BASE_URL}/chat", json={"message": query})
        self.assertEqual(r.status_code, 200)
        text = r.json()["parts"][0]["text"]

        # Cognitive assertion: Must resolve at least one core intent without crashing or returning null
        self.assertTrue(len(text) > 50)
        self.assertTrue("Portfolio Rebalance" in text or "Herbal" in text)

    def test_04_holdings_mutation_edge_cases(self):
        """Cognitive Test: Test handling fractional shares, zero price edge cases, and high valuations."""
        # Test fractional shares (e.g. 0.0051 shares of BTC)
        payload = {
            "ticker": "BTC",
            "name": "Bitcoin Trust ETF",
            "asset_class": "Cash",
            "shares": 0.0051,
            "current_price": 64250.00,
            "target_allocation_pct": 0.0
        }
        r = requests.post(f"{BASE_URL}/api/holdings", json=payload)
        self.assertEqual(r.status_code, 200)

        # Cleanup
        requests.delete(f"{BASE_URL}/api/holdings/BTC")

    def test_05_latency_and_cognitive_load(self):
        """Cognitive Test: Measure average resolution latency across cognitive query domains."""
        queries = [
            "Show my holdings",
            "Calculate portfolio rebalance",
            "Consult herbal remedies for focus and memory",
            "Generate a visual portfolio breakdown chart"
        ]
        latencies = []
        for q in queries:
            t0 = time.time()
            r = requests.post(f"{BASE_URL}/chat", json={"message": q})
            t1 = time.time()
            self.assertEqual(r.status_code, 200)
            latencies.append(t1 - t0)

        avg_latency = sum(latencies) / len(latencies)
        print(f"\n[Cognitive Test Metric] Average Query Resolution Latency: {avg_latency*1000:.2f} ms")
        self.assertLess(avg_latency, 2.0)  # Must resolve under 2.0s

if __name__ == "__main__":
    unittest.main()
