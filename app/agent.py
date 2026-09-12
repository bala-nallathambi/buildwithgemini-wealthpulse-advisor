# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import uuid
import datetime
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import (
    AgentEngineSandboxCodeExecutor,
)
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google import genai
from google.genai import types

from .a2ui_utils import a2ui_callback


MODEL = "gemini-3.6-flash"
PROJECT_ID = "qwiklabs-gcp-03-4c89eb0d0a8d"
BUCKET_NAME = "wealthpulse-assets-qwiklabs-gcp-03-4c89eb0d0a8d"
AGENT_ENGINE_RESOURCE_NAME = (
    "projects/664309893743/locations/us-central1/reasoningEngines/2893472050876252160"
)




async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE: After each turn, send the session to Memory Bank for extraction."""
    await callback_context.add_session_to_memory()
    return None


def list_portfolio_holdings() -> list[dict]:
    """Retrieves all current investment portfolio holdings from the Firestore database.

    Returns:
        A list of dictionaries containing holding details (ticker, name, asset_class, shares, current_price, target_allocation_pct, last_updated).
    """
    db = firestore.Client(project=PROJECT_ID)
    docs = db.collection("portfolio_holdings").stream()
    holdings = []
    for doc in docs:
        data = doc.to_dict()
        holdings.append(data)
    return holdings


def add_or_update_holding(
    ticker: str,
    name: str,
    asset_class: str,
    shares: float,
    current_price: float,
    target_allocation_pct: float,
) -> str:
    """Adds a new investment holding or updates an existing holding in the portfolio database.

    Args:
        ticker: The stock/ETF ticker symbol (e.g., 'AAPL', 'VOO', 'BND').
        name: The full name of the asset/company.
        asset_class: Category such as 'US Equity', 'International Equity', 'Fixed Income', 'Cash'.
        shares: Number of shares owned.
        current_price: Current market price per share in USD.
        target_allocation_pct: Target percentage of portfolio (e.g. 20.0 for 20%).

    Returns:
        Confirmation message detailing the updated or added holding.
    """
    db = firestore.Client(project=PROJECT_ID)
    ticker_clean = ticker.strip().upper()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d")
    holding_data = {
        "ticker": ticker_clean,
        "name": name,
        "asset_class": asset_class,
        "shares": float(shares),
        "current_price": float(current_price),
        "target_allocation_pct": float(target_allocation_pct),
        "last_updated": now_str,
    }
    db.collection("portfolio_holdings").document(ticker_clean).set(holding_data)
    total_val = float(shares) * float(current_price)
    return f"Successfully saved holding for {ticker_clean} ({name}): {shares} shares @ ${current_price:.2f} (Total value: ${total_val:,.2f}, Target: {target_allocation_pct}%)."


def remove_holding(ticker: str) -> str:
    """Removes an investment holding from the portfolio database by its ticker symbol.

    Args:
        ticker: The stock/ETF ticker symbol to remove (e.g., 'AAPL').

    Returns:
        Confirmation or error message.
    """
    db = firestore.Client(project=PROJECT_ID)
    ticker_clean = ticker.strip().upper()
    doc_ref = db.collection("portfolio_holdings").document(ticker_clean)
    if not doc_ref.get().exists:
        return f"Holding for ticker '{ticker_clean}' was not found in the portfolio database."
    doc_ref.delete()
    return f"Successfully removed holding '{ticker_clean}' from the portfolio database."


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


def calculate_portfolio_rebalance(
    target_equity_pct: float = 80.0,
    target_bond_pct: float = 20.0,
) -> dict:
    """Calculates portfolio rebalancing recommendations based on target asset allocation percentages.

    Reads current holdings from Firestore, sums total value by asset class (Equity vs Fixed Income/Bond),
    compares current percentages against target percentages, and calculates dollar adjustments needed.

    Args:
        target_equity_pct: Target percentage for Equities (e.g. 80.0 for 80%).
        target_bond_pct: Target percentage for Fixed Income/Bonds (e.g. 20.0 for 20%).

    Returns:
        A dictionary containing total portfolio value, current allocation breakdown, target allocation, and rebalancing recommendations.
    """
    holdings = list_portfolio_holdings()
    if not holdings:
        return {"error": "No holdings found in the portfolio database."}

    total_value = 0.0
    equity_value = 0.0
    bond_value = 0.0
    other_value = 0.0

    breakdown = []
    for h in holdings:
        val = float(h.get("shares", 0.0)) * float(h.get("current_price", 0.0))
        total_value += val
        asset_cls = str(h.get("asset_class", "")).lower()
        if "equity" in asset_cls or "stock" in asset_cls:
            equity_value += val
        elif "fixed income" in asset_cls or "bond" in asset_cls:
            bond_value += val
        else:
            other_value += val

        breakdown.append({
            "ticker": h.get("ticker"),
            "name": h.get("name"),
            "asset_class": h.get("asset_class"),
            "value_usd": round(val, 2),
        })

    if total_value == 0:
        return {"error": "Total portfolio value is zero."}

    current_equity_pct = round((equity_value / total_value) * 100, 2)
    current_bond_pct = round((bond_value / total_value) * 100, 2)
    current_other_pct = round((other_value / total_value) * 100, 2)

    target_equity_usd = round(total_value * (target_equity_pct / 100.0), 2)
    target_bond_usd = round(total_value * (target_bond_pct / 100.0), 2)

    equity_diff_usd = round(target_equity_usd - equity_value, 2)
    bond_diff_usd = round(target_bond_usd - bond_value, 2)

    recommendations = []
    if equity_diff_usd > 0:
        recommendations.append(f"BUY ${equity_diff_usd:,.2f} in Equities to reach target {target_equity_pct}%.")
    elif equity_diff_usd < 0:
        recommendations.append(f"SELL ${abs(equity_diff_usd):,.2f} in Equities to reduce to target {target_equity_pct}%.")
    else:
        recommendations.append(f"Equities are on target at {target_equity_pct}%.")

    if bond_diff_usd > 0:
        recommendations.append(f"BUY ${bond_diff_usd:,.2f} in Fixed Income/Bonds to reach target {target_bond_pct}%.")
    elif bond_diff_usd < 0:
        recommendations.append(f"SELL ${abs(bond_diff_usd):,.2f} in Fixed Income/Bonds to reduce to target {target_bond_pct}%.")
    else:
        recommendations.append(f"Bonds are on target at {target_bond_pct}%.")

    return {
        "total_portfolio_value_usd": round(total_value, 2),
        "current_allocation": {
            "equities_usd": round(equity_value, 2),
            "equities_pct": current_equity_pct,
            "bonds_usd": round(bond_value, 2),
            "bonds_pct": current_bond_pct,
            "other_usd": round(other_value, 2),
            "other_pct": current_other_pct,
        },
        "target_allocation": {
            "equities_pct": target_equity_pct,
            "equities_usd": target_equity_usd,
            "bonds_pct": target_bond_pct,
            "bonds_usd": target_bond_usd,
        },
        "adjustment_required": {
            "equities_adjustment_usd": equity_diff_usd,
            "bonds_adjustment_usd": bond_diff_usd,
        },
        "recommendations": recommendations,
        "holdings_summary": breakdown,
    }


RAG_CORPUS_NAME = "projects/664309893743/locations/us-central1/ragCorpora/7797586930606014464"


def consult_herbal(query: str) -> str:
    """Retrieves passages from Culpeper's Complete Herbal reference corpus for plant, herb, and herbal remedy information.

    Args:
        query: What plant, herb, symptom, or herbal remedy topic to search for (e.g. 'camomile', 'mint', 'headache').

    Returns:
        Excerpted passages from the herbal corpus.
    """
    from vertexai.preview import rag
    import vertexai

    vertexai.init(project=PROJECT_ID, location="us-central1")
    try:
        resp = rag.retrieval_query(
            text=query,
            rag_resources=[rag.RagResource(rag_corpus=RAG_CORPUS_NAME)],
            rag_retrieval_config=rag.RagRetrievalConfig(top_k=4),
        )
        contexts = getattr(resp.contexts, "contexts", [])
        passages = [c.text.strip() for c in contexts if getattr(c, "text", "").strip()]
        return "\n\n---\n\n".join(passages) or "No relevant passages found in herbal corpus."
    except Exception as e:
        return f"Herbal retrieval error: {e}"


def generate_portfolio_visual_image(
    prompt: str,
    tool_context: ToolContext = None,
) -> dict:
    """Generates a financial asset chart, portfolio visual, or investment graphic using gemini-3.1-flash-lite-image in the global region.

    Saves the image artifact to the active session and uploads image bytes directly to Cloud Storage to produce a public URL.

    Args:
        prompt: Description of the financial visual or portfolio chart image to generate (e.g. 'A modern pie chart showing 80% Equities and 20% Bonds for WealthPulse').
        tool_context: Tool execution context provided automatically by the runtime.

    Returns:
        A dictionary containing the public HTTPS URL of the uploaded image and a success status message.
    """
    genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    response = genai_client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"]
        ),
    )

    image_bytes = None
    mime_type = "image/png"
    if response.candidates:
        for candidate in response.candidates:
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if part.inline_data:
                        image_bytes = part.inline_data.data
                        mime_type = part.inline_data.mime_type or "image/png"
                        break

    if not image_bytes:
        return {"error": "Failed to generate image bytes from model response."}

    artifact_filename = f"financial_visual_{uuid.uuid4().hex[:6]}.png"

    # (1) Save artifact with tool_context.save_artifact
    if tool_context and hasattr(tool_context, "save_artifact"):
        part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=artifact_filename, artifact=part)

    # (2) Upload image bytes to public Cloud Storage bucket
    object_name = f"generated_charts/{artifact_filename}"
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(object_name)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{object_name}"
    return {
        "status": "success",
        "public_url": public_url,
        "artifact_filename": artifact_filename,
    }


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are WealthPulse, an AI personal finance and investment advisor. "
        "You help users manage and optimize their investment portfolio, look up holdings from Firestore, "
        "calculate portfolio rebalancing targets, add or update assets, generate portfolio chart visuals and financial images, "
        "consult the herbal medicine corpus for holistic wellness advice, execute Python code safely in a sandbox, and provide personalized financial advice."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    code_executor=AgentEngineSandboxCodeExecutor(
        agent_engine_resource_name=AGENT_ENGINE_RESOURCE_NAME,
    ),
    tools=[
        PreloadMemoryTool(),
        list_portfolio_holdings,
        add_or_update_holding,
        remove_holding,
        calculate_portfolio_rebalance,
        generate_portfolio_visual_image,
        consult_herbal,
        get_weather,
        get_current_time,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)


app = App(
    root_agent=root_agent,
    name="app",
)



