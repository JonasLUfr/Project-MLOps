import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient

from llama_index.core import Settings, VectorStoreIndex, StorageContext
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine

from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.mongodb import MongoDBAtlasVectorSearch
from llama_index.llms.groq import Groq


# App / Env
app = Flask(__name__, static_folder="static", template_folder="templates")
load_dotenv()

MONGODB_URI       = os.getenv("MONGODB_URI")
DB_NAME           = os.getenv("DB_NAME", "rag")
COLL_NAME         = os.getenv("COLLECTION_NAME", "documents")
VECTOR_INDEX_NAME = os.getenv("VECTOR_INDEX_NAME", "vector_index")

EMB_MODEL         = os.getenv("EMB_MODEL", "BAAI/bge-small-en-v1.5")
EMB_DIM           = int(os.getenv("EMB_DIM", "384"))

GROQ_API_KEY      = os.getenv("GROQ_API_KEY")
GROQ_MODEL        = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

TOP_K             = int(os.getenv("TOP_K", "6"))
HOST              = os.getenv("HOST", "127.0.0.1")
PORT              = int(os.getenv("PORT", "5000"))

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI not set in .env")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not set in .env")


# System prompt (email triage assistant)
SYSTEM_PROMPT = """You are an email security assistant specialized in phishing and spam response.
Input: the full raw email content pasted by the user (sender, subject, body, links, attachments if mentioned), plus fraud probability with an optional retrieved context from a knowledge base.
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
Provide 3-5 bullet indicators, grouped when possible:
- Sender / domain indicators
- Link / URL indicators
- Content & social-engineering indicators
- Attachment indicators (only if present)
Each bullet must reference a concrete element from the email (e.g., domain, wording, mismatch, urgency).

3) Immediate actions (do now)
Provide 3-5 concrete steps. Must be actionable for a normal user.
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


# LlamaIndex setup
Settings.embed_model = HuggingFaceEmbedding(model_name=EMB_MODEL)
Settings.llm = Groq(model=GROQ_MODEL, api_key=GROQ_API_KEY)

client = MongoClient(MONGODB_URI)
vector_store = MongoDBAtlasVectorSearch(
    mongo_client=client,
    db_name=DB_NAME,
    collection_name=COLL_NAME,
    vector_index_name=VECTOR_INDEX_NAME,
    embed_dim=EMB_DIM,
)

storage_ctx = StorageContext.from_defaults(vector_store=vector_store)
index = VectorStoreIndex.from_vector_store(vector_store=vector_store, storage_context=storage_ctx)

retriever = VectorIndexRetriever(index=index, similarity_top_k=TOP_K)
query_engine = RetrieverQueryEngine.from_args(retriever=retriever)


# Answering logic (LLM-led with RAG grounding)
def _build_user_payload(user_text: str, fraud: bool | None, confidence: float | None) -> str:
    meta = []
    if fraud is not None:
        meta.append(f"Fraud classifier: {'YES' if fraud else 'NO'}")
    if confidence is not None:
        meta.append(f"Confidence: {confidence:.3f}")
    header = "\n".join(meta).strip()
    if header:
        return f"{header}\n\nUser input:\n{user_text}"
    return f"User input:\n{user_text}"


def _extract_sources(res, limit: int = 5):
    sources = []
    for sn in getattr(res, "source_nodes", [])[:limit]:
        node = getattr(sn, "node", None)
        meta = getattr(node, "metadata", {}) or {}
        sources.append(
            {
                "filename": meta.get("filename") or meta.get("source"),
                "page": meta.get("page"),
                "score": float(getattr(sn, "score", 0.0) or 0.0),
                "snippet": ((getattr(node, "text", "") or "")[:220]).replace("\n", " "),
            }
        )
    return sources


def _safe_generic_advice(payload: str) -> str:
    return (
        "1) Verdict\n"
        "- Classification: Tier 1\n"
        "- Confidence: Low\n\n"
        "2) Why this email may be suspicious (limited evidence)\n"
        "- The system did not retrieve specific playbook context for this sample.\n"
        "- Treat as potentially unsafe until verified.\n\n"
        "3) Immediate actions (do now)\n"
        "- Do not click links or open attachments.\n"
        "- Use your mail client’s “Report phishing” / “Report spam” feature.\n"
        "- If this is a corporate account, forward the email to your IT/security reporting address.\n"
        "- Block the sender/domain if your mail client allows it.\n\n"
        "4) What NOT to do\n"
        "- Do not reply.\n"
        "- Do not forward to colleagues.\n"
        "- Do not enter passwords or MFA codes from this email.\n"
        "- Do not call phone numbers included in the email.\n"
        "- Do not download files from it.\n\n")


def answer_email_assistance(user_text: str, fraud: bool | None = None, confidence: float | None = None) -> dict:
    payload = _build_user_payload(user_text, fraud, confidence)
    prompt = f"{SYSTEM_PROMPT}\n\n{payload}"

    # Retrieve context + synthesize answer (LLM-led but grounded by retrieval)
    res = query_engine.query(prompt)

    answer_text = (getattr(res, "response", None) or str(res)).strip()
    sources = _extract_sources(res)

    # If retrieval returned nothing useful, do NOT hallucinate: generic safe advice.
    if not sources or not answer_text or answer_text.lower().startswith("empty response"):
        return {"response": _safe_generic_advice(payload), "sources": []}

    return {"response": answer_text, "sources": sources}


# Routes
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

    fraud = None
    if fraud_raw is not None:
        if isinstance(fraud_raw, bool):
            fraud = fraud_raw
        else:
            fraud = str(fraud_raw).lower() in ("1", "true", "yes", "y")

    confidence = None
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
    app.run(debug=True, host=HOST, port=PORT)
