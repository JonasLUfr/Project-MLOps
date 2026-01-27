# app_optimized.py
import os
import time
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient

from llama_index.core import Settings, VectorStoreIndex, StorageContext
from llama_index.core.retrievers import VectorIndexRetriever

from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.mongodb import MongoDBAtlasVectorSearch
from llama_index.llms.groq import Groq


# ----------------------------
# App / Env
# ----------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")
load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME", "rag")
COLL_NAME = os.getenv("COLLECTION_NAME", "documents")
VECTOR_INDEX_NAME = os.getenv("VECTOR_INDEX_NAME", "vector_index")

EMB_MODEL = os.getenv("EMB_MODEL", "BAAI/bge-small-en-v1.5")
EMB_DIM = int(os.getenv("EMB_DIM", "384"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

TOP_K = int(os.getenv("TOP_K", "6"))
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI not set in .env")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not set in .env")


# ----------------------------
# System prompt (one-shot email assistant)
# ----------------------------
SYSTEM_PROMPT = """You are an email security assistant specialized in phishing and spam response.
Input: the full raw email content pasted by the user (sender, subject, body, links, attachments if mentioned), plus a fraud probability, with optional retrieved context from a knowledge base.
Goal: produce a single self-contained response the user can follow immediately.

Hard rules:
- Do not invent facts. Only cite indicators that are visible in the email text or in retrieved context.
- Do not ask follow-up questions (the user will not chat back). If information is missing, state assumptions explicitly and provide safe default actions.
- Prefer safe, non-destructive advice (do not tell users to delete evidence if it may be needed). Avoid over-escalation.

Triage:
- Tier 1: suspicious email, NO click, NO attachment opened, NO credentials entered (assume "no click" unless the email text explicitly implies action happened).
- Tier 2: likely interaction risk (the email requests login/payment, contains a link/attachment, or urges action) OR email implies the user might have clicked.
- Tier 3: strong compromise indicators in the email (credential harvest + urgent reset + suspicious domains) OR retrieved context indicates a known active campaign/malicious domain.

What to do:
- Tier 1: reporting + blocking + hygiene.
- Tier 2: reporting + blocking + immediate account protection steps (password/MFA/session revoke) + endpoint scan guidance.
- Tier 3: containment + incident response escalation + evidence preservation + account/endpoint actions.

Output format (ALWAYS, in this order):

1) Verdict
- Classification: Tier X
- Confidence: Low/Medium/High

2) Why this email looks suspicious (evidence-based)
Provide 3–5 bullet indicators, grouped when possible:
- Sender / domain indicators
- Link / URL indicators
- Content & social-engineering indicators
- Attachment indicators (only if present)
Each bullet must reference a concrete element from the email (e.g., domain, wording, mismatch, urgency).

3) Immediate actions (do now)
Provide 3–5 concrete steps. Must be actionable for a normal user.
Include:
- safe handling (do not click, do not reply, do not forward)
- reporting steps (use report-phishing / forward to IT/security address if generic)
- blocking rules (sender/domain)
- if Tier 2–3: password reset + MFA + session revoke + mailbox rules check
- if Tier 2–3: device scan / antivirus guidance

4) What NOT to do
Exactly 5 bullets (short, strict).

Style constraints:
- Be concise and operational.
- No long theory. No policy language.
- Do not mention internal system design, RAG, embeddings, or models.

Now analyze the provided email content and produce the response in the exact format above.
"""


# ----------------------------
# LlamaIndex setup
# ----------------------------
Settings.embed_model = HuggingFaceEmbedding(model_name=EMB_MODEL)
Settings.llm = Groq(model=GROQ_MODEL, api_key=GROQ_API_KEY)

mongo = MongoClient(MONGODB_URI)

vector_store = MongoDBAtlasVectorSearch(
    mongo_client=mongo,
    db_name=DB_NAME,
    collection_name=COLL_NAME,
    vector_index_name=VECTOR_INDEX_NAME,
    embed_dim=EMB_DIM,
)

storage_ctx = StorageContext.from_defaults(vector_store=vector_store)
index = VectorStoreIndex.from_vector_store(vector_store=vector_store, storage_context=storage_ctx)

retriever = VectorIndexRetriever(index=index, similarity_top_k=TOP_K)


# ----------------------------
# Helpers
# ----------------------------
def _build_user_payload(user_text: str, fraud: Optional[bool], confidence: Optional[float]) -> str:
    meta = []
    if fraud is not None:
        meta.append(f"Fraud classifier: {'YES' if fraud else 'NO'}")
    if confidence is not None:
        meta.append(f"Confidence: {confidence:.3f}")
    header = "\n".join(meta).strip()
    if header:
        return f"{header}\n\nUser input:\n{user_text}"
    return f"User input:\n{user_text}"


def _extract_sources_from_nodes(nodes, limit: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for n in (nodes or [])[:limit]:
        node = getattr(n, "node", None)
        meta = getattr(node, "metadata", {}) or {}
        out.append(
            {
                "filename": meta.get("filename") or meta.get("source"),
                "page": meta.get("page"),
                "score": float(getattr(n, "score", 0.0) or 0.0),
                "snippet": ((getattr(node, "text", "") or "")[:220]).replace("\n", " "),
            }
        )
    return out


def _build_context_from_nodes(nodes, max_chars: int = 8000) -> str:
    """
    Build retrieved context for the LLM.
    Keep it bounded to avoid huge prompts.
    """
    parts: List[str] = []
    total = 0
    for n in nodes or []:
        text = (getattr(getattr(n, "node", None), "text", "") or "").strip()
        if not text:
            continue
        # Add a separator between chunks
        chunk = text + "\n\n---\n\n"
        if total + len(chunk) > max_chars:
            remain = max_chars - total
            if remain > 200:
                parts.append(chunk[:remain])
            break
        parts.append(chunk)
        total += len(chunk)
    return "".join(parts).strip()


def _llm_generate(system_prompt: str, payload: str, context: str) -> str:
    final_prompt = (
        f"{system_prompt}\n\n"
        f"Email input:\n{payload}\n\n"
        f"Retrieved context (may be empty):\n{context}\n"
    )
    return Settings.llm.complete(final_prompt).text.strip()


def answer_email_assistance(user_text: str, fraud: Optional[bool] = None, confidence: Optional[float] = None) -> Dict[str, Any]:
    payload = _build_user_payload(user_text, fraud, confidence)

    # 1) Retrieval ONLY on the email payload (do NOT pollute retrieval with SYSTEM_PROMPT)
    nodes = retriever.retrieve(payload)

    # 2) Build context + sources (sources can be empty; LLM still answers)
    context = _build_context_from_nodes(nodes)
    sources = _extract_sources_from_nodes(nodes)

    # 3) LLM generation (always)
    t0 = time.time()
    answer_text = _llm_generate(SYSTEM_PROMPT, payload, context)
    llm_seconds = time.time() - t0

    if DEBUG:
        print(f"[RAG] nodes={len(nodes) if nodes else 0} sources={len(sources)} llm_seconds={llm_seconds:.2f}")

    return {
        "response": answer_text,
        "sources": sources,
        "meta": {
            "retrieved_nodes": len(nodes) if nodes else 0,
            "llm_seconds": round(llm_seconds, 3),
            "top_k": TOP_K,
        },
    }


# ----------------------------
# Routes
# ----------------------------
@app.route("/")
def home():
    return render_template("chatbot.html")


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True}), 200


@app.route("/query", methods=["GET", "POST"])
def query_endpoint():
    # GET:  /query?text=...&fraud=true&confidence=0.93
    # POST: {"text":"...", "fraud": true, "confidence": 0.93}
    if request.method == "GET":
        text = request.args.get("text", "")
        fraud_raw = request.args.get("fraud")
        conf_raw = request.args.get("confidence")
    else:
        body = request.json or {}
        text = body.get("text", "")
        fraud_raw = body.get("fraud")
        conf_raw = body.get("confidence")

    if not text or not str(text).strip():
        return jsonify({"error": "No text provided"}), 400

    fraud: Optional[bool] = None
    if fraud_raw is not None:
        if isinstance(fraud_raw, bool):
            fraud = fraud_raw
        else:
            fraud = str(fraud_raw).lower() in ("1", "true", "yes", "y")

    confidence: Optional[float] = None
    if conf_raw is not None:
        try:
            confidence = float(conf_raw)
        except Exception:
            confidence = None

    try:
        result = answer_email_assistance(str(text).strip(), fraud=fraud, confidence=confidence)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


if __name__ == "__main__":
    app.run(debug=DEBUG, host=HOST, port=PORT)
