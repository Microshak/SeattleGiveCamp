"""
Knowledge Base manager — loads FAQ markdown files, embeds them with
all-MiniLM-L6-v2, and indexes them in Milvus Lite for semantic search.

Change detection via file hash avoids redundant re-indexing.

Uses pymilvus MilvusClient (newer API) which supports local file-based
embedded storage — no Docker needed.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

# ⚠️ config MUST be imported before sentence-transformers so HF_HOME is set
from email_monitor.config import settings

from pymilvus import DataType, MilvusClient
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

COLLECTION_NAME = "givecamp_kb"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2
HASH_FILE = "kb_hashes.json"
SIMILARITY_THRESHOLD = 0.55  # tuned for all-MiniLM-L6-v2 cosine scores


class KnowledgeBaseManager:
    """Manages the KB document lifecycle: load -> embed -> index -> search."""

    def __init__(self):
        self._encoder: Optional[SentenceTransformer] = None
        self._client: Optional[MilvusClient] = None
        self._initialized = False

    # ── Public API ──────────────────────────────────────────────────────

    def init_milvus(self):
        """Connect to Milvus Lite and ensure the collection exists."""
        if self._initialized:
            return

        uri = settings.milvus_db_path
        Path(uri).parent.mkdir(parents=True, exist_ok=True)
        logger.info("Connecting to Milvus Lite at %s", uri)
        self._client = MilvusClient(uri=uri)

        if self._client.has_collection(COLLECTION_NAME):
            self._client.load_collection(COLLECTION_NAME)
            logger.info("Loaded existing collection '%s'", COLLECTION_NAME)
        else:
            self._create_collection()
            logger.info("Created collection '%s'", COLLECTION_NAME)

        self._initialized = True

    def index_documents(self, kb_dir: Optional[str] = None) -> int:
        """
        Load, embed, and index all KB markdown files.

        Skips files whose content hash hasn't changed.  Returns the number
        of documents indexed (or skipped if unchanged).
        """
        self._ensure_ready()
        kb_dir = kb_dir or settings.kb_dir
        docs = self._load_documents(kb_dir)
        if not docs:
            logger.warning("No KB documents found in %s", kb_dir)
            return 0

        stored_hashes = self._load_hashes()
        current_hashes = {}
        to_index = []

        for doc in docs:
            file_hash = doc["file_hash"]
            current_hashes[doc["doc_id"]] = file_hash
            if stored_hashes.get(doc["doc_id"]) == file_hash:
                logger.debug("Skipping unchanged: %s", doc["doc_id"])
                continue
            to_index.append(doc)

        if not to_index:
            logger.info("All KB documents up to date — no indexing needed.")
            return len(docs)

        # Embed
        texts = [d["body"] for d in to_index]
        embeddings = self._encode(texts)

        # Prepare data for MilvusClient insert
        entities = []
        for i, doc in enumerate(to_index):
            entities.append(
                {
                    "doc_id": doc["doc_id"],
                    "title": doc["title"],
                    "category": doc["category"],
                    "body": doc["body"],
                    "embedding": embeddings[i].tolist(),
                }
            )

        # Insert into Milvus
        self._client.insert(COLLECTION_NAME, entities)
        self._client.flush(COLLECTION_NAME)

        # Load collection so it's ready for search
        self._client.load_collection(COLLECTION_NAME)

        # Save hashes
        self._save_hashes(current_hashes)

        logger.info("Indexed %d new/changed documents", len(to_index))
        return len(to_index)

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """
        Embed the query and search the Milvus collection.

        Returns a list of dicts sorted by descending similarity, each with:
            doc_id, title, category, body, score
        Results with score < SIMILARITY_THRESHOLD are excluded.
        """
        self._ensure_ready()

        # Ensure collection is loaded before search
        self._client.load_collection(COLLECTION_NAME)

        query_vec = self._encode([query]).tolist()[0]

        results = self._client.search(
            collection_name=COLLECTION_NAME,
            data=[query_vec],
            anns_field="embedding",
            search_params={"metric_type": "COSINE"},
            limit=top_k,
            output_fields=["doc_id", "title", "category", "body"],
        )

        hits = []
        for row in results[0]:
            score = row["distance"]
            if score < SIMILARITY_THRESHOLD:
                continue
            fields = row["entity"]
            hits.append(
                {
                    "doc_id": fields.get("doc_id", ""),
                    "title": fields.get("title", ""),
                    "category": fields.get("category", ""),
                    "body": fields.get("body", ""),
                    "score": score,
                }
            )

        return hits

    def check_reindex_needed(self, kb_dir: Optional[str] = None) -> bool:
        """Check whether KB files have changed since last index."""
        kb_dir = kb_dir or settings.kb_dir
        stored_hashes = self._load_hashes()
        docs = self._load_documents(kb_dir)

        for doc in docs:
            if stored_hashes.get(doc["doc_id"]) != doc["file_hash"]:
                return True
        return False

    # ── Internals ──────────────────────────────────────────────────────

    def _ensure_ready(self):
        if not self._initialized:
            self.init_milvus()

    def _create_collection(self):
        schema = MilvusClient.create_schema(
            auto_id=False,
            enable_dynamic_field=False,
        )
        schema.add_field("doc_id", datatype=DataType.VARCHAR, max_length=128, is_primary=True)
        schema.add_field("title", datatype=DataType.VARCHAR, max_length=256)
        schema.add_field("category", datatype=DataType.VARCHAR, max_length=64)
        schema.add_field("body", datatype=DataType.VARCHAR, max_length=8192)
        schema.add_field("embedding", datatype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            metric_type="COSINE",
            index_type="FLAT",  # FLAT for exact search; works well for small collections
        )

        self._client.create_collection(
            collection_name=COLLECTION_NAME,
            schema=schema,
            index_params=index_params,
        )

    def _load_documents(self, kb_dir: str) -> list[dict]:
        """Scan kb_dir for *.md files and parse YAML frontmatter + body."""
        docs = []
        kb_path = Path(kb_dir)
        if not kb_path.is_dir():
            logger.warning("KB directory %s does not exist", kb_dir)
            return docs

        for md_file in sorted(kb_path.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            frontmatter, body = self._parse_frontmatter(content)
            doc_id = md_file.stem
            docs.append(
                {
                    "doc_id": doc_id,
                    "title": frontmatter.get("title", doc_id),
                    "category": frontmatter.get("category", "general"),
                    "body": body.strip(),
                    "file_hash": self._hash_file(content),
                }
            )

        return docs

    @staticmethod
    def _parse_frontmatter(content: str) -> tuple[dict, str]:
        """Parse YAML-like frontmatter between --- delimiters."""
        frontmatter = {}
        body = content

        stripped = content.lstrip()
        if stripped.startswith("---"):
            end_idx = stripped.find("---", 3)
            if end_idx != -1:
                raw = stripped[3:end_idx].strip()
                body = stripped[end_idx + 3:].strip()
                for line in raw.split("\n"):
                    if ":" in line:
                        key, _, val = line.partition(":")
                        frontmatter[key.strip()] = val.strip().strip('"').strip("'")

        return frontmatter, body

    @staticmethod
    def _hash_file(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _encode(self, texts: list[str]):
        """Embed texts using all-MiniLM-L6-v2."""
        if self._encoder is None:
            logger.info("Loading embedding model 'all-MiniLM-L6-v2'...")
            self._encoder = SentenceTransformer("all-MiniLM-L6-v2")
        return self._encoder.encode(texts, show_progress_bar=False)

    def _load_hashes(self) -> dict:
        """Load the stored file hashes from the JSON sidecar."""
        path = Path(settings.db_path).parent / HASH_FILE
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_hashes(self, hashes: dict):
        """Persist file hashes to the JSON sidecar."""
        path = Path(settings.db_path).parent / HASH_FILE
        path.write_text(json.dumps(hashes, indent=2))

    def close(self):
        """Release the Milvus client connection."""
        if self._client is not None:
            try:
                self._client.release_collection(COLLECTION_NAME)
            except Exception:
                pass
            self._client.close()
            self._client = None
            self._initialized = False
            logger.info("Milvus client closed.")
