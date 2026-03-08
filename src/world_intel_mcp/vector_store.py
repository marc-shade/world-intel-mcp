"""Vector store for world-intel-mcp — persistent semantic intelligence archive.

Uses Qdrant for vector storage and sentence-transformers for embeddings.
Unlike the SQLite TTL cache (ephemeral, serves live snapshots), this store
is append-only and accumulates intelligence over time for semantic retrieval.

Designed to be non-blocking: embedding + storage runs in the background via
asyncio.to_thread() so it never delays the main fetch path.
"""

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("world-intel-mcp.vector-store")

# ---------------------------------------------------------------------------
# Lazy imports — sentence-transformers is heavy (~2s first load).
# We import on first use so MCP server startup isn't penalized.
# ---------------------------------------------------------------------------
_embed_model = None
_qdrant_client = None

COLLECTION_NAME = "world_intel"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"  # FastEmbed ONNX model (~45MB, fast)
EMBEDDING_DIM = 384
QDRANT_URL = "http://localhost:6333"

# Maximum text length to embed (chars).  Longer text is truncated.
MAX_EMBED_CHARS = 2000

# Domain → human-readable category for filtering
DOMAIN_CATEGORIES = {
    "markets": "Financial Markets",
    "yahoo-finance": "Financial Markets",
    "coingecko": "Cryptocurrency",
    "crypto": "Cryptocurrency",
    "seismology": "Natural Disasters",
    "usgs": "Natural Disasters",
    "military": "Military & Defense",
    "adsblol": "Military & Defense",
    "opensky": "Military & Defense",
    "cyber": "Cyber Threats",
    "news": "News & Media",
    "rss": "News & Media",
    "gdelt": "News & Media",
    "maritime": "Maritime",
    "nga": "Maritime",
    "infrastructure": "Infrastructure",
    "cloudflare-radar": "Infrastructure",
    "wildfire": "Natural Disasters",
    "nasa-firms": "Natural Disasters",
    "prediction": "Prediction Markets",
    "polymarket": "Prediction Markets",
    "aviation": "Aviation",
    "faa": "Aviation",
    "climate": "Climate",
    "economic": "Economics",
    "energy": "Economics",
    "conflict": "Conflict & Security",
    "acled": "Conflict & Security",
    "ucdp": "Conflict & Security",
    "displacement": "Humanitarian",
    "intelligence": "Intelligence Analysis",
    "space-weather": "Space Weather",
    "ai-watch": "AI & Technology",
    "health": "Health",
    "elections": "Elections",
    "shipping": "Shipping & Trade",
    "social": "Social Signals",
    "nuclear": "Nuclear",
    "tech": "AI & Technology",
    "forex": "Financial Markets",
    "bonds": "Financial Markets",
    "earnings": "Financial Markets",
    "sec-edgar": "Financial Markets",
    "central-banks": "Economics",
    "traffic": "Traffic",
    "webcams": "Infrastructure",
    "sanctions": "Conflict & Security",
    "service-status": "Infrastructure",
    # Granular source names (from fetcher.get_json source= param)
    "sans-dshield": "Cyber Threats",
    "feodo-tracker": "Cyber Threats",
    "cisa-kev": "Cyber Threats",
    "urlhaus": "Cyber Threats",
    "alternative-me": "Financial Markets",
    "mempool": "Cryptocurrency",
    "hexdb": "Military & Defense",
    "nga-msi": "Maritime",
    "open-meteo": "Climate",
    "who-don": "Health",
    "unhcr": "Humanitarian",
    "hdx": "Humanitarian",
    "noaa-swpc": "Space Weather",
    "ofac-sdn": "Conflict & Security",
    "ioda": "Infrastructure",
    "ecb-frankfurter": "Financial Markets",
    "world-bank": "Economics",
    "eia": "Economics",
    "fred": "Economics",
    "hackernews": "AI & Technology",
    "github": "AI & Technology",
    "arxiv": "AI & Technology",
    "usaspending-gov": "Government",
    "eonet": "Natural Disasters",
    "gdacs": "Natural Disasters",
    "reddit": "Social Signals",
}


def _get_embed_model():
    """Lazy-load the FastEmbed model (ONNX, ~45MB, no torch required)."""
    global _embed_model
    if _embed_model is None:
        from fastembed import TextEmbedding

        _embed_model = TextEmbedding(EMBEDDING_MODEL)
        logger.info("Loaded embedding model: %s", EMBEDDING_MODEL)
    return _embed_model


def _get_qdrant():
    """Lazy-load the Qdrant client and ensure collection exists."""
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        _qdrant_client = QdrantClient(url=QDRANT_URL, timeout=10)

        # Create collection if it doesn't exist
        collections = [c.name for c in _qdrant_client.get_collections().collections]
        if COLLECTION_NAME not in collections:
            _qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE,
                ),
            )
            # Create payload indexes for efficient filtering
            from qdrant_client.models import PayloadSchemaType

            _qdrant_client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="domain",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            _qdrant_client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="category",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            _qdrant_client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="timestamp",
                field_schema=PayloadSchemaType.FLOAT,
            )
            logger.info("Created Qdrant collection: %s", COLLECTION_NAME)
    return _qdrant_client


def _embed_text(text: str) -> list[float]:
    """Generate embedding vector for text using FastEmbed (ONNX)."""
    model = _get_embed_model()
    truncated = text[:MAX_EMBED_CHARS]
    embeddings = list(model.embed([truncated]))
    return embeddings[0].tolist()


def _data_to_text(domain: str, data: Any) -> str:
    """Convert structured intelligence data to embeddable text.

    Extracts the most meaningful text from each domain's response format.
    """
    if isinstance(data, str):
        return data

    if not isinstance(data, dict):
        return json.dumps(data, default=str)[:MAX_EMBED_CHARS]

    parts: list[str] = [f"Domain: {domain}"]

    # Extract events/items lists (most domains return {events: [...], count: N})
    for list_key in (
        "events",
        "items",
        "articles",
        "papers",
        "quotes",
        "threats",
        "warnings",
        "delays",
        "alerts",
        "outbreaks",
        "contracts",
        "filings",
        "repos",
        "stories",
        "results",
        "indicators",
        "rates",
        "signals",
    ):
        items = data.get(list_key)
        if isinstance(items, list) and items:
            for item in items[:20]:  # Cap at 20 items
                if isinstance(item, dict):
                    # Extract key text fields
                    for text_key in (
                        "title",
                        "headline",
                        "description",
                        "notes",
                        "summary",
                        "name",
                        "text",
                        "event_type",
                        "country",
                        "location",
                        "source",
                        "category",
                        "symbol",
                        "actor1",
                        "actor2",
                    ):
                        val = item.get(text_key)
                        if val and isinstance(val, str):
                            parts.append(val)
                elif isinstance(item, str):
                    parts.append(item)
            break

    # Extract top-level summary fields
    for key in (
        "summary",
        "verdict",
        "description",
        "status",
        "brief",
        "headline",
        "source",
        "error",
    ):
        val = data.get(key)
        if val and isinstance(val, str):
            parts.append(f"{key}: {val}")

    # Extract country/region context
    for key in ("country", "region", "location", "theater"):
        val = data.get(key)
        if val and isinstance(val, str):
            parts.append(f"{key}: {val}")

    # Include count for context
    count = data.get("count")
    if count is not None:
        parts.append(f"count: {count}")

    text = " | ".join(parts)
    return text[:MAX_EMBED_CHARS]


def _content_hash(domain: str, data: Any) -> str:
    """Generate a content hash for deduplication."""
    raw = json.dumps({"d": domain, "v": data}, default=str, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class VectorStore:
    """Persistent vector store for intelligence data."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._store_queue: asyncio.Queue | None = None
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the background storage worker."""
        if not self.enabled:
            return
        self._store_queue = asyncio.Queue(maxsize=500)
        self._worker_task = asyncio.create_task(self._storage_worker())
        logger.info("Vector store worker started")

    async def stop(self) -> None:
        """Stop the background worker."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    async def _storage_worker(self) -> None:
        """Background worker that processes the store queue."""
        while True:
            try:
                domain, data, timestamp = await self._store_queue.get()
                try:
                    await asyncio.to_thread(self._store_sync, domain, data, timestamp)
                except Exception as exc:
                    logger.warning("Vector store write failed: %s", exc)
                finally:
                    self._store_queue.task_done()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("Vector store worker error: %s", exc)
                await asyncio.sleep(1)

    def _store_sync(self, domain: str, data: Any, timestamp: float) -> None:
        """Synchronous store operation (runs in thread pool)."""
        from qdrant_client.models import PointStruct

        client = _get_qdrant()
        text = _data_to_text(domain, data)
        if len(text) < 20:
            return  # Skip trivially small data

        vector = _embed_text(text)
        content_hash = _content_hash(domain, data)
        point_id = int(
            hashlib.md5(f"{domain}:{content_hash}:{timestamp}".encode()).hexdigest()[
                :16
            ],
            16,
        )

        # Determine category
        category = DOMAIN_CATEGORIES.get(domain, "Other")
        # Try prefix match for RSS feeds etc
        if category == "Other":
            prefix = domain.split(":")[0] if ":" in domain else domain
            category = DOMAIN_CATEGORIES.get(prefix, "Other")

        # Extract geographic context if available
        geo = self._extract_geo(data)

        payload = {
            "domain": domain,
            "category": category,
            "text": text[:2000],
            "content_hash": content_hash,
            "timestamp": timestamp,
            "datetime": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
            "has_error": bool(isinstance(data, dict) and data.get("error")),
        }
        if geo:
            payload.update(geo)

        # Count for context
        if isinstance(data, dict) and "count" in data:
            payload["event_count"] = data["count"]

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            ],
        )

    @staticmethod
    def _extract_geo(data: Any) -> dict | None:
        """Extract geographic info from data if available."""
        if not isinstance(data, dict):
            return None
        geo = {}
        # Direct lat/lon
        for lat_key in ("latitude", "lat"):
            for lon_key in ("longitude", "lon"):
                if lat_key in data and lon_key in data:
                    geo["lat"] = data[lat_key]
                    geo["lon"] = data[lon_key]
                    return geo
        # Country
        for key in ("country", "country_code", "region"):
            if key in data and isinstance(data[key], str):
                geo["country"] = data[key]
        # Check first event for geo
        for list_key in ("events", "items"):
            items = data.get(list_key)
            if isinstance(items, list) and items and isinstance(items[0], dict):
                first = items[0]
                for lat_key in ("latitude", "lat"):
                    if lat_key in first:
                        geo["lat"] = first[lat_key]
                        break
                for lon_key in ("longitude", "lon"):
                    if lon_key in first:
                        geo["lon"] = first[lon_key]
                        break
                for key in ("country", "country_code"):
                    if key in first:
                        geo["country"] = first[key]
                        break
        return geo if geo else None

    async def store(self, domain: str, data: Any) -> None:
        """Queue data for async vector storage.  Non-blocking, fire-and-forget."""
        if not self.enabled or self._store_queue is None:
            return
        if isinstance(data, dict) and data.get("error"):
            return  # Don't store error responses
        try:
            self._store_queue.put_nowait((domain, data, time.time()))
        except asyncio.QueueFull:
            logger.debug("Vector store queue full, dropping %s", domain)

    # ------------------------------------------------------------------
    # Search API
    # ------------------------------------------------------------------

    async def semantic_search(
        self,
        query: str,
        limit: int = 20,
        domain: str | None = None,
        category: str | None = None,
        hours: float | None = None,
    ) -> dict:
        """Semantic search across all stored intelligence.

        Args:
            query: Natural language search query.
            limit: Max results (default 20).
            domain: Filter by source domain (e.g., "markets", "conflict").
            category: Filter by category (e.g., "Financial Markets").
            hours: Only return results from last N hours.

        Returns:
            Dict with results list, each containing score, domain, text, datetime.
        """
        return await asyncio.to_thread(
            self._search_sync, query, limit, domain, category, hours
        )

    def _search_sync(
        self,
        query: str,
        limit: int,
        domain: str | None,
        category: str | None,
        hours: float | None,
    ) -> dict:
        from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

        client = _get_qdrant()
        vector = _embed_text(query)

        # Build filters
        conditions = []
        if domain:
            conditions.append(
                FieldCondition(key="domain", match=MatchValue(value=domain))
            )
        if category:
            conditions.append(
                FieldCondition(key="category", match=MatchValue(value=category))
            )
        if hours:
            cutoff = time.time() - (hours * 3600)
            conditions.append(FieldCondition(key="timestamp", range=Range(gte=cutoff)))
        # Exclude error entries
        conditions.append(
            FieldCondition(key="has_error", match=MatchValue(value=False))
        )

        query_filter = Filter(must=conditions) if conditions else None

        results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )

        return {
            "query": query,
            "results": [
                {
                    "score": round(r.score, 4),
                    "domain": r.payload.get("domain", ""),
                    "category": r.payload.get("category", ""),
                    "text": r.payload.get("text", ""),
                    "datetime": r.payload.get("datetime", ""),
                    "event_count": r.payload.get("event_count"),
                    "country": r.payload.get("country"),
                }
                for r in results
            ],
            "count": len(results),
            "filters": {
                "domain": domain,
                "category": category,
                "hours": hours,
            },
        }

    async def find_similar(
        self,
        domain: str,
        text: str,
        limit: int = 10,
        hours: float | None = None,
    ) -> dict:
        """Find historically similar events/data to a given text."""
        return await asyncio.to_thread(self._similar_sync, domain, text, limit, hours)

    def _similar_sync(
        self,
        domain: str,
        text: str,
        limit: int,
        hours: float | None,
    ) -> dict:
        from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

        client = _get_qdrant()
        vector = _embed_text(text)

        conditions = [
            FieldCondition(key="has_error", match=MatchValue(value=False)),
        ]
        if hours:
            cutoff = time.time() - (hours * 3600)
            conditions.append(FieldCondition(key="timestamp", range=Range(gte=cutoff)))

        results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=vector,
            query_filter=Filter(must=conditions),
            limit=limit,
            with_payload=True,
        )

        return {
            "reference_domain": domain,
            "reference_text": text[:200],
            "similar": [
                {
                    "score": round(r.score, 4),
                    "domain": r.payload.get("domain", ""),
                    "category": r.payload.get("category", ""),
                    "text": r.payload.get("text", ""),
                    "datetime": r.payload.get("datetime", ""),
                    "country": r.payload.get("country"),
                }
                for r in results
            ],
            "count": len(results),
        }

    async def timeline(
        self,
        domain: str | None = None,
        category: str | None = None,
        hours: float = 24.0,
        limit: int = 50,
    ) -> dict:
        """Get chronological timeline of stored intelligence."""
        return await asyncio.to_thread(
            self._timeline_sync, domain, category, hours, limit
        )

    def _timeline_sync(
        self,
        domain: str | None,
        category: str | None,
        hours: float,
        limit: int,
    ) -> dict:
        from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

        client = _get_qdrant()
        cutoff = time.time() - (hours * 3600)

        conditions = [
            FieldCondition(key="timestamp", range=Range(gte=cutoff)),
            FieldCondition(key="has_error", match=MatchValue(value=False)),
        ]
        if domain:
            conditions.append(
                FieldCondition(key="domain", match=MatchValue(value=domain))
            )
        if category:
            conditions.append(
                FieldCondition(key="category", match=MatchValue(value=category))
            )

        # Scroll with filter (no vector search — chronological)
        results, _ = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(must=conditions),
            limit=limit,
            with_payload=True,
            order_by="timestamp",
        )

        entries = sorted(
            [
                {
                    "domain": r.payload.get("domain", ""),
                    "category": r.payload.get("category", ""),
                    "text": r.payload.get("text", "")[:300],
                    "datetime": r.payload.get("datetime", ""),
                    "timestamp": r.payload.get("timestamp", 0),
                    "event_count": r.payload.get("event_count"),
                    "country": r.payload.get("country"),
                }
                for r in results
            ],
            key=lambda x: x["timestamp"],
            reverse=True,
        )

        return {
            "hours": hours,
            "entries": entries[:limit],
            "count": len(entries),
            "filters": {"domain": domain, "category": category},
        }

    async def collection_stats(self) -> dict:
        """Get vector store statistics."""
        try:
            return await asyncio.to_thread(self._stats_sync)
        except Exception as exc:
            return {"error": str(exc), "enabled": self.enabled}

    def _stats_sync(self) -> dict:
        client = _get_qdrant()
        info = client.get_collection(COLLECTION_NAME)
        return {
            "enabled": self.enabled,
            "collection": COLLECTION_NAME,
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "status": info.status.value if info.status else "unknown",
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dim": EMBEDDING_DIM,
        }
