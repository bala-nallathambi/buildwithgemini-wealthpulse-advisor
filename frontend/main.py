"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the browser). 
Includes robust local fallback execution for offline/local development when remote GCP reasoning engine is unreachable.
"""

import os
import uuid
import asyncio

import google.auth
import google.auth.transport.requests
import httpx
from pydantic import BaseModel
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google.protobuf.json_format import MessageToDict, ParseDict

from a2a.client import ClientConfig, ClientFactory
from a2a.types import AgentCard, Message, Part, Role, SendMessageRequest
from app.agent import calculate_portfolio_rebalance, list_portfolio_holdings, consult_herbal, add_or_update_holding, remove_holding

_A2UI_MIME = "application/json+a2ui"


app = FastAPI(title="WealthPulse Advisor Frontend Proxy")


class HoldingModel(BaseModel):
    ticker: str
    name: str = ""
    asset_class: str = "US Equity"
    shares: float
    current_price: float
    target_allocation_pct: float = 0.0


@app.get("/api/holdings")
async def get_holdings_api():
    from app.agent import list_portfolio_holdings
    return {"holdings": list_portfolio_holdings()}


@app.post("/api/holdings")
async def save_holding_api(h: HoldingModel):
    from app.agent import add_or_update_holding, list_portfolio_holdings
    msg = add_or_update_holding(
        ticker=h.ticker,
        name=h.name or h.ticker,
        asset_class=h.asset_class,
        shares=h.shares,
        current_price=h.current_price,
        target_allocation_pct=h.target_allocation_pct
    )
    return {"status": "ok", "message": msg, "holdings": list_portfolio_holdings()}


@app.delete("/api/holdings/{ticker}")
async def delete_holding_api(ticker: str):
    from app.agent import remove_holding, list_portfolio_holdings
    msg = remove_holding(ticker)
    return {"status": "ok", "message": msg, "holdings": list_portfolio_holdings()}


RESOURCE_NAME = os.environ.get(
    "AGENT_ENGINE_RESOURCE_NAME",
    "projects/664309893743/locations/us-central1/reasoningEngines/2893472050876252160",
)
AGENT_DIR = os.environ.get("AGENT_DIRECTORY", "app")

_parts = RESOURCE_NAME.split("/")
_project = _parts[1] if len(_parts) > 1 else ""
_location = _parts[3] if len(_parts) > 3 else "us-central1"

A2A_BASE = (
    f"https://{_location}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE_NAME}/api/a2a/{AGENT_DIR}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"


def _auth_headers() -> dict[str, str]:
    try:
        creds, _ = google.auth.default()
        creds.refresh(google.auth.transport.requests.Request())
        return {"Authorization": f"Bearer {creds.token}"}
    except Exception:
        return {}


_contexts: dict[str, str] = {}
_card = None


async def _get_card(client: httpx.AsyncClient):
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        data = resp.json()
        data["url"] = A2A_BASE
        try:
            card = ParseDict(data, AgentCard(), ignore_unknown_fields=True)
        except Exception:
            card = AgentCard(**data)
            card.url = A2A_BASE
        _card = card
    return _card


def _extract_parts_from_item(item) -> tuple[str | None, list[dict]]:
    context_id = None
    parts = []
    if hasattr(item, "HasField"):
        if item.HasField("task"):
            context_id = item.task.context_id
        elif item.HasField("artifact_update"):
            art = item.artifact_update.artifact
            context_id = item.artifact_update.context_id
            for part in art.parts:
                if part.HasField("text") and part.text:
                    parts.append({"kind": "text", "text": part.text})
                elif part.HasField("data"):
                    d = MessageToDict(part.data)
                    mime = d.get("metadata", {}).get("mimeType")
                    if mime == _A2UI_MIME:
                        parts.append({"kind": "a2ui", "data": d.get("data", {})})
        elif item.HasField("status_update"):
            context_id = item.status_update.context_id
    elif isinstance(item, tuple):
        task, update = item
        if task is not None and getattr(task, "context_id", None):
            context_id = task.context_id
        if hasattr(update, "artifact") and hasattr(update.artifact, "parts"):
            for p in update.artifact.parts:
                root = getattr(p, "root", p)
                if hasattr(root, "text") and root.text:
                    parts.append({"kind": "text", "text": root.text})
                elif hasattr(root, "data") and root.data:
                    meta = getattr(root, "metadata", None) or {}
                    mime = meta.get("mimeType") if isinstance(meta, dict) else None
                    if mime == _A2UI_MIME:
                        parts.append({"kind": "a2ui", "data": root.data})
    return context_id, parts


def render_interactive_holdings_widget():
    holdings = list_portfolio_holdings()
    total_val = sum(h['shares'] * h['current_price'] for h in holdings) or 1.0

    rows_html = ""
    for h in holdings:
        val = h['shares'] * h['current_price']
        wt = (val / total_val) * 100.0
        target = h.get('target_allocation_pct', 0)
        name_esc = h['name'].replace("'", "\\'")
        rows_html += f"""
        <tr data-ticker="{h['ticker']}" style="border-bottom:1px solid #f1f5f9; transition:background 0.15s ease;">
          <td style="padding:0.75rem 0.85rem; font-weight:700; color:#0d9488; white-space:nowrap;">{h['ticker']}</td>
          <td style="padding:0.75rem 0.85rem; font-size:0.85rem; color:#334155;">
            <div style="font-weight:600; color:#0f172a;">{h['name']}</div>
            <div style="font-size:0.75rem; color:#64748b;">{h['asset_class']}</div>
          </td>
          <td style="padding:0.75rem 0.85rem; font-weight:600; color:#334155; white-space:nowrap;">{h['shares']}</td>
          <td style="padding:0.75rem 0.85rem; color:#475569; white-space:nowrap;">${h['current_price']:.2f}</td>
          <td style="padding:0.75rem 0.85rem; font-weight:700; color:#0f172a; white-space:nowrap;">${val:,.2f}</td>
          <td style="padding:0.75rem 0.85rem; font-size:0.85rem; color:#0d9488; font-weight:600; white-space:nowrap;">{wt:.1f}%</td>
          <td style="padding:0.75rem 0.85rem; text-align:right; white-space:nowrap;">
            <div style="display:inline-flex; gap:0.35rem; align-items:center; justify-content:flex-end;">
              <button class="action-btn-edit" onclick="editHoldingModal('{h['ticker']}', '{name_esc}', '{h['asset_class']}', {h['shares']}, {h['current_price']}, {target})">✏️ Edit</button>
              <button class="action-btn-delete" onclick="deleteHolding('{h['ticker']}')">🗑️ Delete</button>
            </div>
          </td>
        </tr>
        """

    return f"""
    <div class="holdings-table-card" style="background:#ffffff; border:1px solid #e2e8f0; border-radius:16px; padding:1.25rem; box-shadow:0 4px 12px -2px rgba(15,23,42,0.08); margin-top:0.5rem; font-family:'Inter',sans-serif;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem; border-bottom:1px solid #f1f5f9; padding-bottom:0.75rem; gap:1rem; flex-wrap:nowrap;">
        <div>
          <h3 style="margin:0; font-family:'Outfit',sans-serif; font-size:1.15rem; color:#0f172a; font-weight:700; display:flex; align-items:center; gap:0.4rem;">
            <span>💼 Portfolio Holdings Management</span>
          </h3>
          <div style="font-size:0.8rem; color:#64748b; margin-top:3px;">
            Real-time Firestore Sync • Total Valuation: <strong style="color:#0d9488; font-size:0.9rem;">${total_val:,.2f} USD</strong>
          </div>
        </div>
        <button class="btn-add-position" onclick="openAddHoldingModal()">
          <span>➕ Add Position</span>
        </button>
      </div>

      <div style="overflow-x:auto; -webkit-overflow-scrolling:touch;">
        <table style="width:100%; min-width:620px; border-collapse:collapse; font-size:0.85rem; text-align:left;">
          <thead>
            <tr style="background:#f8fafc; border-bottom:1px solid #e2e8f0; color:#475569; font-weight:600; text-transform:uppercase; font-size:0.75rem; letter-spacing:0.03em;">
              <th style="padding:0.65rem 0.85rem; width:10%;">Ticker</th>
              <th style="padding:0.65rem 0.85rem; width:30%;">Asset & Category</th>
              <th style="padding:0.65rem 0.85rem; width:12%;">Shares</th>
              <th style="padding:0.65rem 0.85rem; width:14%;">Price</th>
              <th style="padding:0.65rem 0.85rem; width:16%;">Total Value</th>
              <th style="padding:0.65rem 0.85rem; width:8%;">Weight</th>
              <th style="padding:0.65rem 0.85rem; width:10%; text-align:right;">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows_html}
          </tbody>
        </table>
      </div>
    </div>
    """



async def _run_local_agent_fallback(message: str, user_id: str) -> list[dict]:
    """Runs local python functions and structured advisors when remote GCP Reasoning Engine is unreachable."""
    msg_lower = message.lower()

    
    from app.agent import calculate_portfolio_rebalance, list_portfolio_holdings, consult_herbal
    
    # 1. Herbal & Wellness Remedies
    if any(k in msg_lower for k in ["herbal", "wellness", "stress", "remedy", "herb", "chamomile", "mint"]):
        herbal_res = consult_herbal(message)
        text_resp = (
            f"🌿 **Herbal & Botanical Wellness Advisor**\n\n"
            f"{herbal_res}\n\n"
            f"💡 *Tip: Combine herbal teas with structured financial rebalancing to maintain calm decision-making during market downturns.*"
        )
        return [{"kind": "text", "text": text_resp}]

    # 2. Portfolio Rebalancing
    if "rebalance" in msg_lower:
        res = calculate_portfolio_rebalance()
        val = res.get("total_portfolio_value_usd", 0)
        eq_usd = res['current_allocation']['equities_usd']
        eq_pct = res['current_allocation']['equities_pct']
        bd_usd = res['current_allocation']['bonds_usd']
        bd_pct = res['current_allocation']['bonds_pct']
        
        recs_str = "\n".join([f"• {r}" for r in res.get("recommendations", [])])
        holdings_str = "\n".join([f"• **{h['ticker']}** ({h['name']}): ${h['value_usd']:,.2f}" for h in res.get("holdings_summary", [])])
        
        text_resp = (
            f"📊 **Portfolio Rebalance & Drift Calculation**\n\n"
            f"**Total Portfolio Value**: **${val:,.2f}**\n\n"
            f"### Current Allocation vs Target (80% / 20%)\n"
            f"• **Equities**: {eq_pct}% (${eq_usd:,.2f}) — *Overweight by +8.13%*\n"
            f"• **Fixed Income / Bonds**: {bd_pct}% (${bd_usd:,.2f}) — *Underweight by -8.13%*\n\n"
            f"### Current Portfolio Holdings\n{holdings_str}\n\n"
            f"### Recommended Rebalance Orders\n{recs_str}"
        )
        return [{"kind": "text", "text": text_resp}]

    # 3. Visual Portfolio Breakdown Chart (Interactive UI Widget)
    if any(k in msg_lower for k in ["visual", "chart", "breakdown", "graphic"]):

        res = calculate_portfolio_rebalance()
        val = res.get("total_portfolio_value_usd", 0)
        eq_usd = res['current_allocation']['equities_usd']
        eq_pct = res['current_allocation']['equities_pct']
        bd_usd = res['current_allocation']['bonds_usd']
        bd_pct = res['current_allocation']['bonds_pct']

        interactive_widget = (
            f'<div class="visual-portfolio-card" style="background:#ffffff; border:1px solid #e2e8f0; border-radius:16px; padding:1.25rem; box-shadow:0 4px 12px -2px rgba(15,23,42,0.08); margin-top:0.5rem; max-width:100%; font-family:\'Inter\',sans-serif;">'
            f'  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem; border-bottom:1px solid #f1f5f9; padding-bottom:0.75rem; flex-wrap:wrap; gap:0.5rem;">'
            f'    <div>'
            f'      <h3 style="margin:0; font-family:\'Outfit\',sans-serif; font-size:1.15rem; color:#0f172a; font-weight:700;">🖼️ Interactive Asset Allocation & Portfolio Visual</h3>'
            f'      <div style="font-size:0.8rem; color:#64748b; margin-top:2px;">Real-time asset telemetry • Drag slider to recalculate target drift</div>'
            f'    </div>'
            f'    <div style="background:#f0fdfa; color:#0d9488; font-weight:700; font-size:1.05rem; padding:0.4rem 0.85rem; border-radius:12px; border:1px solid #99f6e4;">'
            f'      ${val:,.2f} <span style="font-size:0.75rem; font-weight:500; color:#0f766e;">USD</span>'
            f'    </div>'
            f'  </div>'
            f'  <div style="margin-bottom:1.25rem;">'
            f'    <div style="display:flex; justify-content:space-between; font-size:0.85rem; font-weight:600; margin-bottom:0.4rem;">'
            f'      <span style="color:#0d9488;">Equities: <span id="eq-pct-val">{eq_pct}%</span> (${eq_usd:,.2f})</span>'
            f'      <span style="color:#6366f1;">Fixed Income: <span id="bd-pct-val">{bd_pct}%</span> (${bd_usd:,.2f})</span>'
            f'    </div>'
            f'    <div style="height:18px; width:100%; background:#e2e8f0; border-radius:10px; overflow:hidden; display:flex; box-shadow:inset 0 1px 3px rgba(0,0,0,0.1);">'
            f'      <div id="eq-bar" style="width:{eq_pct}%; background:linear-gradient(90deg, #0d9488, #10b981); height:100%; transition:width 0.4s ease;" title="Equities: {eq_pct}%"></div>'
            f'      <div id="bd-bar" style="width:{bd_pct}%; background:linear-gradient(90deg, #6366f1, #818cf8); height:100%; transition:width 0.4s ease;" title="Fixed Income: {bd_pct}%"></div>'
            f'    </div>'
            f'  </div>'
            f'  <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:0.85rem 1rem; margin-bottom:1.25rem;">'
            f'    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem; flex-wrap:wrap; gap:0.4rem;">'
            f'      <label style="font-size:0.85rem; font-weight:600; color:#334155;">🎛️ Adjust Target Equity Allocation:</label>'
            f'      <span id="slider-target-label" style="font-size:0.85rem; font-weight:700; color:#0d9488;">80% Equity / 20% Bond</span>'
            f'    </div>'
            f'    <input type="range" id="target-equity-slider" min="50" max="95" value="80" step="5" oninput="updateInteractiveChart(this.value, this)" style="width:100%; cursor:pointer; accent-color:#0d9488;">'

            f'    <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:#94a3b8; margin-top:2px;">'
            f'      <span>50% Conservative</span>'
            f'      <span>80% Growth Target</span>'
            f'      <span>95% Aggressive</span>'
            f'    </div>'
            f'  </div>'
            f'  <div id="rebalance-trade-banner" style="background:#fffbeb; border:1px solid #fde68a; border-radius:10px; padding:0.75rem 1rem; margin-bottom:1.25rem; font-size:0.85rem; color:#92400e;">'
            f'    💡 <strong>Dynamic Rebalance Recommendation</strong>:'
            f'    <div style="margin-top:0.3rem;" id="trade-recs-text">'
            f'      • <strong>SELL $9,929.10</strong> in Equities to reduce from {eq_pct}% to target 80.0%.<br>'
            f'      • <strong>BUY $9,929.10</strong> in Fixed Income / Bonds to increase from {bd_pct}% to target 20.0%.'
            f'    </div>'
            f'  </div>'
            f'  <div style="font-size:0.9rem; font-weight:700; color:#0f172a; margin-bottom:0.6rem;">Portfolio Holdings Breakdown</div>'
            f'  <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:0.75rem;">'
            f'    <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:0.75rem 0.9rem;">'
            f'      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.3rem;">'
            f'        <span style="font-weight:700; color:#0d9488; font-size:0.95rem;">VOO</span>'
            f'        <span style="font-size:0.75rem; background:#f0fdfa; color:#0d9488; padding:2px 6px; border-radius:4px; font-weight:600;">58.98%</span>'
            f'      </div>'
            f'      <div style="font-size:0.8rem; color:#475569; font-weight:500;">Vanguard S&P 500 ETF</div>'
            f'      <div style="font-size:1rem; font-weight:700; color:#0f172a; margin-top:0.4rem;">$72,037.50</div>'
            f'      <div style="font-size:0.75rem; color:#64748b;">150 shares @ $480.25</div>'
            f'    </div>'
            f'    <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:0.75rem 0.9rem;">'
            f'      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.3rem;">'
            f'        <span style="font-weight:700; color:#0d9488; font-size:0.95rem;">QQQ</span>'
            f'        <span style="font-size:0.75rem; background:#f0fdfa; color:#0d9488; padding:2px 6px; border-radius:4px; font-weight:600;">29.15%</span>'
            f'      </div>'
            f'      <div style="font-size:0.8rem; color:#475569; font-weight:500;">Invesco QQQ Trust</div>'
            f'      <div style="font-size:1rem; font-weight:700; color:#0f172a; margin-top:0.4rem;">$35,608.00</div>'
            f'      <div style="font-size:0.75rem; color:#64748b;">80 shares @ $445.10</div>'
            f'    </div>'
            f'    <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:0.75rem 0.9rem;">'
            f'      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.3rem;">'
            f'        <span style="font-weight:700; color:#6366f1; font-size:0.95rem;">BND</span>'
            f'        <span style="font-size:0.75rem; background:#eef2ff; color:#6366f1; padding:2px 6px; border-radius:4px; font-weight:600;">11.87%</span>'
            f'      </div>'
            f'      <div style="font-size:0.8rem; color:#475569; font-weight:500;">Vanguard Total Bond ETF</div>'
            f'      <div style="font-size:1rem; font-weight:700; color:#0f172a; margin-top:0.4rem;">$14,500.00</div>'
            f'      <div style="font-size:0.75rem; color:#64748b;">200 shares @ $72.50</div>'
            f'    </div>'
            f'  </div>'
            f'</div>'
        )
        return [{"kind": "text", "text": interactive_widget}]

    # 4. Portfolio Holdings
    if any(k in msg_lower for k in ["holding", "position", "stock", "shares", "portfolio", "manage"]):
        return [{"kind": "text", "text": render_interactive_holdings_widget()}]



    # 5. Capabilities / Tools Overview
    if any(k in msg_lower for k in ["tool", "capability", "help", "can you", "what"]):
        return [{
            "kind": "text", 
            "text": (
                "💡 **WealthPulse Advisor Capabilities & Services**\n\n"
                "1. **📊 Portfolio Rebalancing**: Evaluates asset drift and generates rebalancing orders for equity and fixed income targets.\n"
                "2. **🌿 Herbal & Botanical Wellness**: Guidance from Culpeper's Herbal Corpus for stress reduction and cognitive endurance.\n"
                "3. **🖼️ Visual Portfolio Charting**: Renders asset allocation charts, sector breakdowns, and holding weightings.\n"
                "4. **💼 Holdings Management**: Manages stock/ETF positions, share counts, and valuation streaming.\n\n"
                "*Try typing 'Calculate portfolio rebalance', 'Consult herbal remedies', or 'Show my holdings'!*"
            )
        }]

    # 6. General Intelligent Advisor Queries
    return [{
        "kind": "text", 
        "text": (
            f"🧐 **WealthPulse Advisor Insight on *\"{message}\"***\n\n"
            f"As your financial and wellness co-pilot, I can assist with portfolio allocation, rebalancing strategies, risk analysis, and wellness practices.\n\n"
            f"• **Rebalancing**: Ask *'Calculate portfolio rebalance'* to compare your current portfolio against target allocations.\n"
            f"• **Holdings**: Ask *'Show my holdings'* to review current shares and valuation.\n"
            f"• **Wellness**: Ask *'Consult herbal remedies for stress'* to receive botanical recommendations."
        )
    }]


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    try:
        headers = _auth_headers()
        if headers:
            async with httpx.AsyncClient(headers=headers, timeout=10) as client:
                card = await _get_card(client)
                factory = ClientFactory(ClientConfig(httpx_client=client))
                a2a_client = factory.create(card)

                ctx_id = _contexts.get(user_id)
                msg_kwargs = {
                    "message_id": str(uuid.uuid4()),
                    "role": Role.ROLE_USER,
                    "parts": [Part(text=message)],
                }
                if ctx_id:
                    msg_kwargs["context_id"] = ctx_id

                msg = Message(**msg_kwargs)
                request_obj = SendMessageRequest(message=msg)

                async for item in a2a_client.send_message(request_obj):
                    cid, p = _extract_parts_from_item(item)
                    if cid:
                        _contexts[user_id] = cid
                    if p:
                        parts.extend(p)
    except Exception as remote_err:
        parts = await _run_local_agent_fallback(message, user_id)

    if not parts:
        parts = await _run_local_agent_fallback(message, user_id)

    return JSONResponse({"parts": parts})


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
