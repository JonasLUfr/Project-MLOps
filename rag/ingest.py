import os
import re
from pathlib import Path
from typing import List, Tuple

import fitz 
from dotenv import load_dotenv
from pymongo import MongoClient

from llama_index.core import Document, StorageContext, VectorStoreIndex, Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.mongodb import MongoDBAtlasVectorSearch


# ----------------------------
# ENV / CONFIG
# ----------------------------
load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME", "rag")
COLL_NAME = os.getenv("COLLECTION_NAME", "documents")
VECTOR_INDEX_NAME = os.getenv("VECTOR_INDEX_NAME", "vector_index")

PDF_DIR = os.getenv("PDF_DIR", "data")

EMB_MODEL = os.getenv("EMB_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_DIM = int(os.getenv("EMBED_DIM", "384"))

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "650"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "120"))

PURGE_SOURCES = os.getenv("PURGE_SOURCES", "true").lower() == "true"

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI not set")


# ----------------------------
# FILTERING RULES
# ----------------------------
# Stop indexing after these headings
STOP_HEADINGS = [
    "references",
    "bibliography",
    "références",
    "bibliographie",
    "references and notes",
]

# Very common ref-list pattern lines: [1] ...  or (1) ... etc.
REF_LINE_RE = re.compile(r"^\s*(\[\d+\]|\(\d+\)|\d+\.)\s+")

CTRL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
MULTI_WS = re.compile(r"\s+")


def clean_text(t: str) -> str:
    t = t or ""
    t = CTRL_CHARS.sub(" ", t)
    t = MULTI_WS.sub(" ", t).strip()
    return t


def looks_like_references_page(page_text: str) -> bool:
    """
    Heuristic: if a page has lots of citation-list lines, it's likely references.
    """
    lines = [ln.strip() for ln in (page_text or "").splitlines() if ln.strip()]
    if len(lines) < 10:
        return False
    ref_like = sum(1 for ln in lines if REF_LINE_RE.match(ln))
    return (ref_like / max(len(lines), 1)) >= 0.35


def find_stop_point(text: str) -> int:
    """
    Returns index in text where references/bibliography starts.
    If not found, returns -1.
    """
    lower = text.lower()
    for h in STOP_HEADINGS:
        # match headings as standalone-ish lines/words
        m = re.search(rf"(^|\n)\s*{re.escape(h)}\s*(\n|$)", lower)
        if m:
            return m.start()
    return -1


def extract_pdf_documents(pdf_path: Path) -> List[Document]:
    """
    Extract content page-by-page, but:
    - stop at the page where "References"/"Bibliography" begins (and truncate that page)
    - skip pages that look like pure references lists
    """
    docs: List[Document] = []
    pdf = fitz.open(pdf_path)

    stop_all_further_pages = False

    for page_idx in range(len(pdf)):
        if stop_all_further_pages:
            break

        raw = pdf[page_idx].get_text("text") or ""
        # Before cleaning, detect stop heading on raw (keeps newlines)
        stop_at = find_stop_point(raw)

        if stop_at != -1:
            raw = raw[:stop_at]
            stop_all_further_pages = True  # do not index anything after this

        # Skip if this page is basically references
        if looks_like_references_page(raw):
            stop_all_further_pages = True
            break

        txt = clean_text(raw)
        if len(txt) < 150:
            continue

        docs.append(
            Document(
                text=txt,
                metadata={
                    "source": str(pdf_path),
                    "filename": pdf_path.name,
                    "page": page_idx + 1,
                    "doc_type": "phishing_paper",
                },
            )
        )

    pdf.close()
    return docs


def purge_existing_sources(mongo: MongoClient, sources: List[str]) -> None:
    coll = mongo[DB_NAME][COLL_NAME]
    res = coll.delete_many({"metadata.source": {"$in": sources}})
    print(f"[PURGE_SOURCES] deleted {res.deleted_count} docs")


def iter_pdfs(pdf_dir: str) -> List[Path]:
    base = Path(pdf_dir)
    if not base.exists():
        raise RuntimeError(f"PDF_DIR does not exist: {pdf_dir}")
    return [p for p in base.rglob("*.pdf") if p.is_file()]


def main() -> None:
    pdfs = iter_pdfs(PDF_DIR)
    if not pdfs:
        print(f"No PDFs in {PDF_DIR}")
        return

    # Extract
    all_docs: List[Document] = []
    sources = []
    for p in pdfs:
        sources.append(str(p))
        all_docs.extend(extract_pdf_documents(p))

    print(f"PDFs: {len(pdfs)}")
    print(f"Docs (page-level, filtered): {len(all_docs)}")
    if not all_docs:
        print("No docs extracted (after filtering).")
        return

    mongo = MongoClient(MONGODB_URI)
    if PURGE_SOURCES:
        purge_existing_sources(mongo, sources)

    # LlamaIndex setup
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMB_MODEL)
    splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

    vector_store = MongoDBAtlasVectorSearch(
        mongo_client=mongo,
        db_name=DB_NAME,
        collection_name=COLL_NAME,
        index_name=VECTOR_INDEX_NAME,
        embed_dim=EMBED_DIM,
    )
    storage = StorageContext.from_defaults(vector_store=vector_store)

    _index = VectorStoreIndex.from_documents(
        all_docs,
        storage_context=storage,
        transformations=[splitter],
        show_progress=True,
    )

    print("Ingest done.")


if __name__ == "__main__":
    main()
