"""RAG pipeline, holding two kinds of Chroma collections in the same
persistent client:

- The knowledge base (chunk_knowledge_base/build_index/retrieve): rules,
  category definitions, examples, used to ground the content-clarity
  rubric, fix generation, and the agent loop's SUGGEST ranking.
- Per-business collections (ingest_business/retrieve_business_context):
  one business's own scraped website content, so generated fixes can be
  grounded in its real details instead of invented ones.

Both reuse the same generic chunker (chunk_text) and are kept separate
from agents.py so the LLM-calling code doesn't need to know about
embeddings or chunking.
"""

import re
import threading
from pathlib import Path

from src.agents import embed
from src.checkers import LOCAL_BUSINESS_TYPES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
KNOWLEDGE_BASE_PATH = DATA_DIR / "knowledge_base.md"
CHROMA_DIR = DATA_DIR / "chroma"
COLLECTION_NAME = "knowledge_base"
BUSINESS_COLLECTION_PREFIX = "business_"
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50

_client = None
_lock = threading.Lock()
_status = {
    "ready": False,
    "building": False,
    "error": None,
    "chunk_count": 0,
    "chunk_size": DEFAULT_CHUNK_SIZE,
}


def _get_client():
    global _client
    if _client is None:
        import chromadb

        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def _estimate_tokens(text):
    # Word-count approximation. Good enough for ~128-token chunk targets
    # without pulling in a separate tokenizer dependency.
    return len(text.split())


def _split_sentences(text):
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _split_sections(markdown_text):
    """Split markdown into (heading, body) sections on ## / ### headers."""
    sections = []
    heading = "Introduction"
    body_lines = []
    for line in markdown_text.splitlines():
        if line.startswith("## ") or line.startswith("### "):
            if body_lines:
                sections.append((heading, "\n".join(body_lines).strip()))
            heading = line.lstrip("#").strip()
            body_lines = []
        elif line.startswith("# "):
            continue  # top-level title, not section content
        else:
            body_lines.append(line)
    if body_lines:
        sections.append((heading, "\n".join(body_lines).strip()))
    return [(h, b) for h, b in sections if b]


def _make_chunk(heading, units):
    body = "\n\n".join(units)
    text = f"{heading}\n\n{body}" if heading else body
    return {"heading": heading, "text": text, "tokens": _estimate_tokens(text)}


def _overlap_tail(units, overlap):
    """Return the trailing units of `units` totaling up to ~overlap
    tokens, used to seed the next chunk with context from this one."""
    if overlap <= 0:
        return [], 0

    tail, tail_tokens = [], 0
    for unit in reversed(units):
        unit_tokens = _estimate_tokens(unit)
        if tail and tail_tokens + unit_tokens > overlap:
            break
        tail.insert(0, unit)
        tail_tokens += unit_tokens
    return tail, tail_tokens


def _paragraph_units(paragraph, chunk_size):
    """A paragraph that fits in chunk_size is one atomic unit, so packing
    never mixes unrelated paragraphs (e.g. separate FAQ entries) more than
    necessary. An oversized paragraph falls back to sentence-level units."""
    if _estimate_tokens(paragraph) <= chunk_size:
        return [paragraph]

    units, current, current_tokens = [], [], 0
    for sentence in _split_sentences(paragraph):
        sentence_tokens = _estimate_tokens(sentence)
        if current and current_tokens + sentence_tokens > chunk_size:
            units.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(sentence)
        current_tokens += sentence_tokens
    if current:
        units.append(" ".join(current))
    return units


def chunk_text(markdown_text, chunk_size=DEFAULT_CHUNK_SIZE, overlap=DEFAULT_CHUNK_OVERLAP):
    """Split markdown generically on ## / ### headers (no hardcoded
    section names, so this keeps working whichever headings the file
    has) into ~chunk_size-token chunks, never splitting a sentence or a
    paragraph, and never crossing a section boundary. Each chunk's text
    starts with its section heading. Consecutive chunks within an
    oversized section overlap by ~`overlap` tokens, so context near a
    cut point isn't lost to either chunk."""
    chunks = []
    for heading, body in _split_sections(markdown_text):
        units = []
        for paragraph in [p.strip() for p in body.split("\n\n") if p.strip()]:
            units.extend(_paragraph_units(paragraph, chunk_size))

        current, current_tokens = [], 0
        for unit in units:
            unit_tokens = _estimate_tokens(unit)
            if current and current_tokens + unit_tokens > chunk_size:
                chunks.append(_make_chunk(heading, current))
                current, current_tokens = _overlap_tail(current, overlap)
            current.append(unit)
            current_tokens += unit_tokens

        if current:
            chunks.append(_make_chunk(heading, current))

    for i, chunk in enumerate(chunks):
        chunk["id"] = f"chunk-{i}"
    return chunks


def chunk_knowledge_base(chunk_size=DEFAULT_CHUNK_SIZE, overlap=DEFAULT_CHUNK_OVERLAP):
    return chunk_text(KNOWLEDGE_BASE_PATH.read_text(), chunk_size, overlap)


def get_status():
    with _lock:
        return dict(_status)


def build_index(chunk_size=DEFAULT_CHUNK_SIZE, overlap=DEFAULT_CHUNK_OVERLAP):
    """Chunk the knowledge base, embed each chunk, and store in ChromaDB.
    Deletes and recreates the collection first, so this fully replaces
    whatever was previously indexed rather than adding to it."""
    with _lock:
        _status["building"] = True
        _status["error"] = None

    try:
        chunks = chunk_knowledge_base(chunk_size, overlap)
        embeddings = embed([c["text"] for c in chunks])

        client = _get_client()
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        collection = client.create_collection(
            COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
        )
        collection.add(
            ids=[c["id"] for c in chunks],
            embeddings=embeddings,
            documents=[c["text"] for c in chunks],
            metadatas=[{"heading": c["heading"], "tokens": c["tokens"]} for c in chunks],
        )

        with _lock:
            _status.update(
                ready=True,
                building=False,
                chunk_count=len(chunks),
                chunk_size=chunk_size,
            )
        return chunks
    except Exception as error:
        with _lock:
            _status["building"] = False
            _status["error"] = str(error)
        raise


def start_background_build(chunk_size=DEFAULT_CHUNK_SIZE):
    thread = threading.Thread(target=build_index, args=(chunk_size,), daemon=True)
    thread.start()
    return thread


def _ensure_ready():
    """Builds the knowledge-base index synchronously on the first call
    that actually needs it (retrieve()), rather than app.py kicking off
    start_background_build() unconditionally at import time. That eager
    boot-time build was the other half of the startup memory spike:
    even with lazy imports above, calling build_index() immediately at
    boot still pulls the whole model+chromadb stack into memory before
    the process has served a single request. Building on first real use
    instead means gunicorn can boot (and pass Render's health check)
    without ever loading them if nothing's asked for RAG yet."""
    with _lock:
        if _status["ready"] or _status["building"]:
            return
    build_index()


def get_indexed_chunks():
    """Return the chunks currently stored in ChromaDB, in order."""
    client = _get_client()
    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception:
        return []

    data = collection.get()
    chunks = [
        {
            "id": chunk_id,
            "text": data["documents"][i],
            "heading": data["metadatas"][i]["heading"],
            "tokens": data["metadatas"][i]["tokens"],
        }
        for i, chunk_id in enumerate(data["ids"])
    ]
    chunks.sort(key=lambda c: int(c["id"].split("-")[1]))
    return chunks


def retrieve(question, top_k=3):
    """Embed the question and return the top_k most similar chunks.
    Builds the index first if this is the first call since boot (see
    _ensure_ready)."""
    _ensure_ready()
    query_embedding = embed([question])

    client = _get_client()
    collection = client.get_collection(COLLECTION_NAME)
    results = collection.query(query_embeddings=query_embedding, n_results=top_k)

    sources = []
    for i, chunk_id in enumerate(results["ids"][0]):
        distance = results["distances"][0][i]
        sources.append(
            {
                "id": chunk_id,
                "text": results["documents"][0][i],
                "heading": results["metadatas"][0][i]["heading"],
                "similarity": round(1 - distance, 3),
            }
        )
    return sources


def _flatten_schema(schema):
    items = []
    for item in schema or []:
        if not isinstance(item, dict):
            continue
        graph = item.get("@graph")
        if isinstance(graph, list):
            items.extend(sub for sub in graph if isinstance(sub, dict))
        else:
            items.append(item)
    return items


def _stringify_schema_value(value):
    if isinstance(value, dict):
        return ", ".join(f"{k}: {v}" for k, v in value.items() if isinstance(v, (str, int, float)))
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if isinstance(v, (str, int, float)))
    return str(value)


# Structural nodes (WebPage, CollectionPage, WebSite, BreadcrumbList,
# ImageObject, SearchAction, ...) carry no retrievable meaning and just
# crowd out real page copy in the chunker, so only render nodes that
# describe the business itself, and only their meaningful fields.
BUSINESS_SCHEMA_TYPES = LOCAL_BUSINESS_TYPES | {"Organization"}
BUSINESS_SCHEMA_FIELDS = ("name", "address", "telephone", "openingHours", "areaServed", "description")


def _schema_to_text(schema):
    """Render business-identity schema.org nodes (LocalBusiness/subtypes,
    Organization) as short readable lines, using only their meaningful
    fields (see BUSINESS_SCHEMA_FIELDS) — everything else (@id, @context,
    inLanguage, isPartOf, potentialAction, ...) is skipped."""
    lines = []
    for item in _flatten_schema(schema):
        item_type = item.get("@type")
        types = item_type if isinstance(item_type, list) else [item_type]
        if not any(t in BUSINESS_SCHEMA_TYPES for t in types if t):
            continue

        type_str = ", ".join(t for t in types if t)
        fields = ", ".join(
            f"{field}: {_stringify_schema_value(item[field])}"
            for field in BUSINESS_SCHEMA_FIELDS
            if item.get(field)
        )
        if fields:
            lines.append(f"{type_str} - {fields}")
    return "\n".join(lines)


def _business_source_text(snapshot):
    parts = []
    if snapshot.get("title"):
        parts.append(f"Page title: {snapshot['title']}")
    if snapshot.get("meta_description"):
        parts.append(f"Meta description: {snapshot['meta_description']}")
    schema_text = _schema_to_text(snapshot.get("schema"))
    if schema_text:
        parts.append(f"Structured data:\n{schema_text}")
    if snapshot.get("text"):
        parts.append(snapshot["text"])
    return "\n\n".join(parts)


def ingest_business(business_id, snapshot):
    """Chunk and embed a business's scraped website snapshot into its own
    collection (business_<id>), so generated fixes can be grounded in the
    business's real details instead of invented ones. Deletes and
    recreates the collection first, same pattern as build_index(), so
    re-running an audit replaces the old content rather than piling
    chunks on top of it. Returns the chunk count."""
    chunks = chunk_text(_business_source_text(snapshot))
    if not chunks:
        return 0

    embeddings = embed([c["text"] for c in chunks])

    source_url = snapshot.get("final_url") or snapshot.get("url") or ""
    page_title = snapshot.get("title") or ""

    client = _get_client()
    collection_name = f"{BUSINESS_COLLECTION_PREFIX}{business_id}"
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(collection_name, metadata={"hnsw:space": "cosine"})
    collection.add(
        ids=[c["id"] for c in chunks],
        embeddings=embeddings,
        documents=[c["text"] for c in chunks],
        metadatas=[
            {"business_id": business_id, "source_url": source_url, "page_title": page_title}
            for _ in chunks
        ],
    )
    return len(chunks)


def retrieve_business_context(business_id, query, k=5):
    """Same idea as retrieve(), scoped to one business's own collection.
    Returns [] instead of raising if that business hasn't been ingested
    yet (e.g. before its first audit)."""
    client = _get_client()
    try:
        collection = client.get_collection(f"{BUSINESS_COLLECTION_PREFIX}{business_id}")
    except Exception:
        return []

    query_embedding = embed([query])
    results = collection.query(query_embeddings=query_embedding, n_results=k)
    return results["documents"][0] if results["ids"] and results["ids"][0] else []


if __name__ == "__main__":
    import json
    import sys

    from src.db import get_business, get_connection

    connection = get_connection()
    row = connection.execute(
        "SELECT * FROM business_snapshots ORDER BY created_at DESC, rowid DESC LIMIT 1"
    ).fetchone()
    connection.close()

    if not row:
        print("No snapshots in the database yet. Run an audit first.")
        sys.exit(1)

    business = get_business(row["business_id"])
    snapshot = {
        "text": row["website_text"] or "",
        "schema": json.loads(row["website_schema_json"] or "[]"),
        "title": business["name"] if business else "",
        "final_url": business["website_url"] if business else "",
    }

    # business_snapshots only stores the merged text, not a per-page
    # breakdown, so re-scrape live to show how much each crawled page
    # actually contributed — useful for diagnosing why real page copy
    # might be thin relative to the number of pages crawled.
    website_url = business["website_url"] if business else None
    if website_url:
        from src.components.scrape_website import scrape_website

        print(f"Re-scraping {website_url} for a per-page text breakdown...")
        live_scrape = scrape_website(website_url)
        for page_url, length in live_scrape["page_text_lengths"].items():
            print(f"  {length:>6} chars  {page_url}")
        print()

    print(f"Ingesting snapshot {row['id']} for business {row['business_id']} ({snapshot['title']})...")
    chunk_count = ingest_business(row["business_id"], snapshot)
    print(f"Indexed {chunk_count} chunks.\n")

    for query in ("what services does this business offer", "where is this business located"):
        print(f"Query: {query}")
        for chunk in retrieve_business_context(row["business_id"], query):
            print(f"  - {chunk[:200]}")
        print()
