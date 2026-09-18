#!/usr/bin/env python3
"""
End-to-End QA Integration Test Suite for WealthPulse Advisor
Tests UI endpoints, REST APIs (Holdings CRUD), Chat fallback agent intents,
Export logic, and layout HTML structure.
"""

import unittest
import requests
import json
import time

BASE_URL = "http://localhost:8080"

class TestWealthPulseE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Verify server is responding
        try:
            r = requests.get(f"{BASE_URL}/", timeout=5)
            assert r.status_code == 200
        except Exception as e:
            raise RuntimeError(f"Server at {BASE_URL} is not accessible: {e}")

    def test_01_homepage_html_structure(self):
        """Test homepage HTML contains correct modal forms, button IDs, and CSS rules."""
        r = requests.get(f"{BASE_URL}/")
        self.assertEqual(r.status_code, 200)
        html = r.text
        
        # Verify button scoping
        self.assertIn('id="send-btn"', html)
        self.assertIn('.action-btn-edit', html)
        self.assertIn('.action-btn-delete', html)
        self.assertIn('.btn-add-position', html)
        
        # Verify modal HTML
        self.assertIn('id="holding-modal"', html)
        self.assertIn('id="holding-form"', html)
        self.assertIn('id="h-ticker"', html)
        self.assertIn('id="h-name"', html)
        self.assertIn('id="h-class"', html)
        self.assertIn('id="h-shares"', html)
        self.assertIn('id="h-price"', html)

    def test_02_get_initial_holdings(self):
        """Test GET /api/holdings returns valid holdings array."""
        r = requests.get(f"{BASE_URL}/api/holdings")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("holdings", data)
        tickers = [h["ticker"] for h in data["holdings"]]
        self.assertIn("VOO", tickers)
        self.assertIn("QQQ", tickers)
        self.assertIn("BND", tickers)

    def test_03_create_new_holding(self):
        """Test POST /api/holdings adds a new stock position (TSLA)."""
        payload = {
            "ticker": "TSLA",
            "name": "Tesla, Inc.",
            "asset_class": "US Equity",
            "shares": 10.0,
            "current_price": 220.00,
            "target_allocation_pct": 5.0
        }
        r = requests.post(f"{BASE_URL}/api/holdings", json=payload)
        self.assertEqual(r.status_code, 200)
        res = r.json()
        self.assertEqual(res.get("status"), "ok")
        
        # Verify TSLA is present in GET /api/holdings
        r_get = requests.get(f"{BASE_URL}/api/holdings")
        data = r_get.json()
        tickers = [h["ticker"] for h in data["holdings"]]
        self.assertIn("TSLA", tickers)

    def test_04_edit_existing_holding(self):
        """Test POST /api/holdings updates an existing position (VOO shares)."""
        payload = {
            "ticker": "VOO",
            "name": "Vanguard S&P 500 ETF",
            "asset_class": "US Equity",
            "shares": 160.0,
            "current_price": 480.25,
            "target_allocation_pct": 50.0
        }
        r = requests.post(f"{BASE_URL}/api/holdings", json=payload)
        self.assertEqual(r.status_code, 200)
        
        # Verify VOO shares updated
        r_get = requests.get(f"{BASE_URL}/api/holdings")
        data = r_get.json()
        voo = next((h for h in data["holdings"] if h["ticker"] == "VOO"), None)
        self.assertIsNotNone(voo)
        self.assertEqual(voo["shares"], 160.0)

    def test_05_delete_holding(self):
        """Test DELETE /api/holdings/{ticker} removes TSLA position."""
        r = requests.delete(f"{BASE_URL}/api/holdings/TSLA")
        self.assertEqual(r.status_code, 200)
        res = r.json()
        self.assertEqual(res.get("status"), "ok")
        
        # Verify TSLA is deleted
        r_get = requests.get(f"{BASE_URL}/api/holdings")
        data = r_get.json()
        tickers = [h["ticker"] for h in data["holdings"]]
        self.assertNotIn("TSLA", tickers)

    def test_06_chat_holdings_table_widget(self):
        """Test POST /chat returns holdings table HTML widget."""
        r = requests.post(f"{BASE_URL}/chat", json={"message": "Show my holdings"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("parts", data)
        text = data["parts"][0]["text"]
        self.assertIn("holdings-table-card", text)
        self.assertIn("Portfolio Holdings Management", text)
        self.assertIn("action-btn-edit", text)
        self.assertIn("action-btn-delete", text)
        self.assertIn("btn-add-position", text)

    def test_07_chat_rebalance_intent(self):
        """Test POST /chat returns rebalance recommendations."""
        r = requests.post(f"{BASE_URL}/chat", json={"message": "Calculate portfolio rebalance"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        text = data["parts"][0]["text"]
        self.assertIn("Portfolio Rebalance", text)
        self.assertIn("Equities", text)

    def test_08_chat_herbal_wellness_intent(self):
        """Test POST /chat returns herbal wellness advice."""
        r = requests.post(f"{BASE_URL}/chat", json={"message": "Consult herbal remedies for stress"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        text = data["parts"][0]["text"]
        self.assertIn("Herbal & Botanical Wellness", text)

    def test_09_chat_visual_chart_widget(self):
        """Test POST /chat returns visual chart widget HTML."""
        r = requests.post(f"{BASE_URL}/chat", json={"message": "Generate a visual portfolio breakdown chart"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        text = data["parts"][0]["text"]
        self.assertIn("visual-portfolio-card", text)
        self.assertIn("target-equity-slider", text)

if __name__ == "__main__":
    unittest.main()
