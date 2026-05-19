from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from flask import Flask, request, jsonify
from flask import send_from_directory

try:
    import app.runtime as runtime_mod
except ModuleNotFoundError:
    # Allow running `python app/api.py` from the repository root where the
    # package `app` may not be importable. Add the `app` directory to sys.path
    # and import the module as a top-level module.
    import sys
    from pathlib import Path

    app_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(app_dir))
    import runtime as runtime_mod

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.route("/query", methods=["POST"])
def query() -> Any:
    body = request.get_json() or {}
    question = body.get("question")
    if not question:
        return jsonify({"error": "missing 'question' in request body"}), 400

    collection = body.get("collection") or runtime_mod.DEFAULT_COLLECTION
    qdrant_url = body.get("qdrant_url") or runtime_mod.DEFAULT_QDRANT_URL
    tei_url = body.get("tei_url") or runtime_mod.DEFAULT_TEI_URL
    db_path = Path(body.get("db_path")) if body.get("db_path") else runtime_mod.DEFAULT_DB_PATH
    use_reranker = body.get("use_reranker", True)
    agentic = body.get("agentic", False)
    max_iterations = int(body.get("max_iterations", 3))
    search_limit = int(body.get("search_limit", 50))
    top_passages = int(body.get("top_passages", 10))

    qdrant = runtime_mod.QdrantClient(qdrant_url)
    tei = runtime_mod.TeiClient(tei_url)
    ingestion = runtime_mod.IngestionStore(db_path)

    try:
        if agentic:
            answer = runtime_mod.agentic_rag(
                query=question,
                qdrant=qdrant,
                tei=tei,
                ingestion=ingestion,
                collection=collection,
                search_limit=search_limit,
                top_passages=top_passages,
                use_reranker=use_reranker,
                max_iterations=max_iterations,
            )
        else:
            answer = runtime_mod.one_shot_rag(
                query=question,
                qdrant=qdrant,
                tei=tei,
                ingestion=ingestion,
                collection=collection,
                search_limit=search_limit,
                top_passages=top_passages,
                use_reranker=use_reranker,
            )
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        ingestion.close()


@app.route('/', methods=['GET'])
def index():
    # Serve the static test page
    static_dir = Path(__file__).resolve().parent / 'static'
    return send_from_directory(str(static_dir), 'index.html')


if __name__ == "__main__":
    # Run using Flask's built-in server: python app/api.py
    app.run(host="0.0.0.0", port=8000)
