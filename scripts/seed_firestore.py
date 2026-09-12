#!/usr/bin/env python3
"""Seed script for Firestore portfolio_holdings collection."""

from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-03-4c89eb0d0a8d"

SEED_HOLDINGS = [
    {
        "ticker": "VOO",
        "name": "Vanguard S&P 500 ETF",
        "asset_class": "US Equity",
        "shares": 50.0,
        "current_price": 510.20,
        "target_allocation_pct": 50.0,
        "last_updated": "2026-09-11",
    },
    {
        "ticker": "BND",
        "name": "Vanguard Total Bond Market ETF",
        "asset_class": "Fixed Income",
        "shares": 100.0,
        "current_price": 72.80,
        "target_allocation_pct": 20.0,
        "last_updated": "2026-09-11",
    },
    {
        "ticker": "VXUS",
        "name": "Vanguard Total International Stock ETF",
        "asset_class": "International Equity",
        "shares": 40.0,
        "current_price": 65.40,
        "target_allocation_pct": 15.0,
        "last_updated": "2026-09-11",
    },
    {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "asset_class": "US Equity",
        "shares": 25.0,
        "current_price": 230.50,
        "target_allocation_pct": 15.0,
        "last_updated": "2026-09-11",
    },
]


def seed_firestore():
    print(f"Connecting to Firestore for project: {PROJECT_ID}...")
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection("portfolio_holdings")

    for holding in SEED_HOLDINGS:
        doc_id = holding["ticker"]
        collection_ref.document(doc_id).set(holding)
        print(f"  ✓ Seeded document: portfolio_holdings/{doc_id}")

    print("Successfully seeded Firestore collection 'portfolio_holdings'!")


if __name__ == "__main__":
    seed_firestore()
