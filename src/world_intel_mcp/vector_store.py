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
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.util import find_spec
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

try:
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PayloadSchemaType,
        PointStruct,
        Range,
        VectorParams,
    )
except ImportError:
    Distance = None
    PayloadSchemaType = None
    VectorParams = None

    @dataclass(slots=True)
    class MatchValue:
        value: Any

    @dataclass(slots=True)
    class Range:
        gte: float | None = None
        lte: float | None = None

    @dataclass(slots=True)
    class FieldCondition:
        key: str
        match: Any = None
        range: Any = None

    @dataclass(slots=True)
    class Filter:
        must: list[Any]

    @dataclass(slots=True)
    class PointStruct:
        id: int
        vector: list[float]
        payload: dict[str, Any]


def vector_dependencies_available() -> bool:
    return find_spec("fastembed") is not None and find_spec("qdrant_client") is not None


def _get_embed_model():
    """Lazy-load the FastEmbed model (ONNX, ~45MB, no torch required)."""
    global _embed_model
    if _embed_model is None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError(
                'Vector store dependencies not installed. Install with `pip install -e ".[vector]"`.'
            ) from exc

        _embed_model = TextEmbedding(EMBEDDING_MODEL)
        logger.info("Loaded embedding model: %s", EMBEDDING_MODEL)
    return _embed_model


def _get_qdrant():
    """Lazy-load the Qdrant client and ensure collection exists."""
    global _qdrant_client
    if _qdrant_client is None:
        if not vector_dependencies_available() or any(
            dep is None for dep in (Distance, VectorParams, PayloadSchemaType)
        ):
            raise RuntimeError(
                'Vector store dependencies not installed. Install with `pip install -e ".[vector]"`.'
            )
        from qdrant_client import QdrantClient

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
        filters = {"domain": domain, "category": category, "hours": hours}
        try:
            return await asyncio.to_thread(
                self._search_sync, query, limit, domain, category, hours
            )
        except Exception as exc:
            return {
                "error": str(exc),
                "query": query,
                "results": [],
                "count": 0,
                "filters": filters,
            }

    def _search_sync(
        self,
        query: str,
        limit: int,
        domain: str | None,
        category: str | None,
        hours: float | None,
    ) -> dict:
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
        try:
            return await asyncio.to_thread(self._similar_sync, domain, text, limit, hours)
        except Exception as exc:
            return {
                "error": str(exc),
                "reference_domain": domain,
                "reference_text": text[:200],
                "similar": [],
                "count": 0,
            }

    def _similar_sync(
        self,
        domain: str,
        text: str,
        limit: int,
        hours: float | None,
    ) -> dict:
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
        filters = {"domain": domain, "category": category}
        try:
            return await asyncio.to_thread(
                self._timeline_sync, domain, category, hours, limit
            )
        except Exception as exc:
            return {
                "error": str(exc),
                "hours": hours,
                "entries": [],
                "count": 0,
                "filters": filters,
            }

    def _timeline_sync(
        self,
        domain: str | None,
        category: str | None,
        hours: float,
        limit: int,
    ) -> dict:
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

    # ------------------------------------------------------------------
    # Cross-domain correlation
    # ------------------------------------------------------------------

    async def cross_domain_correlate(
        self,
        query: str,
        hours: float = 24.0,
        limit_per_domain: int = 5,
    ) -> dict:
        """Find correlated signals across multiple intelligence domains.

        Given a topic, searches all domains and groups results by category,
        showing how different intelligence streams relate to the same event.
        """
        try:
            return await asyncio.to_thread(
                self._correlate_sync, query, hours, limit_per_domain
            )
        except Exception as exc:
            return {
                "error": str(exc),
                "query": query,
                "hours": hours,
                "domains_found": 0,
                "correlations": [],
                "total_signals": 0,
            }

    def _correlate_sync(
        self,
        query: str,
        hours: float,
        limit_per_domain: int,
    ) -> dict:
        client = _get_qdrant()
        vector = _embed_text(query)

        conditions = [
            FieldCondition(key="has_error", match=MatchValue(value=False)),
        ]
        if hours:
            cutoff = time.time() - (hours * 3600)
            conditions.append(FieldCondition(key="timestamp", range=Range(gte=cutoff)))

        # Fetch more results to ensure coverage across domains
        results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=vector,
            query_filter=Filter(must=conditions),
            limit=100,
            with_payload=True,
        )

        # Group by category, keep top N per category
        by_category: dict[str, list[dict]] = {}
        for r in results:
            cat = r.payload.get("category", "Other")
            if cat not in by_category:
                by_category[cat] = []
            if len(by_category[cat]) < limit_per_domain:
                by_category[cat].append(
                    {
                        "score": round(r.score, 4),
                        "domain": r.payload.get("domain", ""),
                        "text": r.payload.get("text", "")[:300],
                        "datetime": r.payload.get("datetime", ""),
                        "country": r.payload.get("country"),
                    }
                )

        # Sort categories by best score
        sorted_cats = sorted(
            by_category.items(),
            key=lambda kv: max(e["score"] for e in kv[1]) if kv[1] else 0,
            reverse=True,
        )

        return {
            "query": query,
            "hours": hours,
            "domains_found": len(by_category),
            "correlations": [
                {
                    "category": cat,
                    "signal_count": len(entries),
                    "best_score": max(e["score"] for e in entries),
                    "signals": entries,
                }
                for cat, entries in sorted_cats
            ],
            "total_signals": sum(len(v) for v in by_category.values()),
        }

    # ------------------------------------------------------------------
    # Domain summary
    # ------------------------------------------------------------------

    async def domain_summary(self, hours: float = 24.0) -> dict:
        """Get per-domain summary of stored intelligence."""
        try:
            return await asyncio.to_thread(self._domain_summary_sync, hours)
        except Exception as exc:
            return {
                "error": str(exc),
                "hours": hours,
                "total_data_points": 0,
                "categories": 0,
                "summary": [],
            }

    def _domain_summary_sync(self, hours: float) -> dict:
        client = _get_qdrant()
        cutoff = time.time() - (hours * 3600)

        # Scroll all points in the time window (no vector search)
        conditions = [
            FieldCondition(key="timestamp", range=Range(gte=cutoff)),
            FieldCondition(key="has_error", match=MatchValue(value=False)),
        ]

        all_points = []
        offset = None
        while True:
            points, next_offset = client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=Filter(must=conditions),
                limit=200,
                offset=offset,
                with_payload=["domain", "category", "timestamp", "event_count"],
            )
            all_points.extend(points)
            if next_offset is None or len(points) == 0:
                break
            offset = next_offset

        # Aggregate by category
        by_category: dict[str, dict] = {}
        for p in all_points:
            cat = p.payload.get("category", "Other")
            if cat not in by_category:
                by_category[cat] = {
                    "count": 0,
                    "domains": set(),
                    "latest": 0.0,
                    "earliest": float("inf"),
                    "total_events": 0,
                }
            entry = by_category[cat]
            entry["count"] += 1
            entry["domains"].add(p.payload.get("domain", ""))
            ts = p.payload.get("timestamp", 0)
            entry["latest"] = max(entry["latest"], ts)
            entry["earliest"] = min(entry["earliest"], ts)
            ec = p.payload.get("event_count")
            if ec and isinstance(ec, (int, float)):
                entry["total_events"] += int(ec)

        # Convert sets to lists and format
        summaries = []
        for cat, info in sorted(
            by_category.items(), key=lambda kv: kv[1]["count"], reverse=True
        ):
            summaries.append(
                {
                    "category": cat,
                    "data_points": info["count"],
                    "unique_sources": len(info["domains"]),
                    "sources": sorted(info["domains"]),
                    "total_events_tracked": info["total_events"] or None,
                    "latest": datetime.fromtimestamp(
                        info["latest"], tz=timezone.utc
                    ).isoformat()
                    if info["latest"] > 0
                    else None,
                    "earliest": datetime.fromtimestamp(
                        info["earliest"], tz=timezone.utc
                    ).isoformat()
                    if info["earliest"] < float("inf")
                    else None,
                }
            )

        return {
            "hours": hours,
            "total_data_points": len(all_points),
            "categories": len(summaries),
            "summary": summaries,
        }

    # ------------------------------------------------------------------
    # Trend detection (activity anomalies)
    # ------------------------------------------------------------------

    async def trend_detection(
        self,
        category: str | None = None,
        recent_hours: float = 6.0,
        baseline_hours: float = 48.0,
    ) -> dict:
        """Detect activity trends by comparing recent vs baseline periods.

        Compares data point density in the recent window against the baseline
        to identify surges or drops in intelligence activity.
        """
        try:
            return await asyncio.to_thread(
                self._trend_sync, category, recent_hours, baseline_hours
            )
        except Exception as exc:
            return {
                "error": str(exc),
                "recent_window_hours": recent_hours,
                "baseline_window_hours": baseline_hours,
                "categories_analyzed": 0,
                "surges": 0,
                "drops": 0,
                "trends": [],
            }

    def _trend_sync(
        self,
        category: str | None,
        recent_hours: float,
        baseline_hours: float,
    ) -> dict:
        client = _get_qdrant()
        now = time.time()
        recent_cutoff = now - (recent_hours * 3600)
        baseline_cutoff = now - (baseline_hours * 3600)

        base_conditions = [
            FieldCondition(key="has_error", match=MatchValue(value=False)),
        ]
        if category:
            base_conditions.append(
                FieldCondition(key="category", match=MatchValue(value=category))
            )

        def _count_in_window(start: float, end: float) -> dict[str, int]:
            """Count points per category in a time window."""
            conditions = base_conditions + [
                FieldCondition(key="timestamp", range=Range(gte=start, lte=end)),
            ]
            points = []
            offset = None
            while True:
                batch, next_offset = client.scroll(
                    collection_name=COLLECTION_NAME,
                    scroll_filter=Filter(must=conditions),
                    limit=200,
                    offset=offset,
                    with_payload=["category"],
                )
                points.extend(batch)
                if next_offset is None or len(batch) == 0:
                    break
                offset = next_offset
            counts: dict[str, int] = {}
            for p in points:
                cat = p.payload.get("category", "Other")
                counts[cat] = counts.get(cat, 0) + 1
            return counts

        recent_counts = _count_in_window(recent_cutoff, now)
        baseline_counts = _count_in_window(baseline_cutoff, recent_cutoff)

        # Normalize baseline to per-hour rate
        baseline_window = baseline_hours - recent_hours
        if baseline_window <= 0:
            baseline_window = 1.0

        all_cats = set(recent_counts.keys()) | set(baseline_counts.keys())
        trends = []
        for cat in sorted(all_cats):
            recent = recent_counts.get(cat, 0)
            baseline = baseline_counts.get(cat, 0)

            recent_rate = recent / recent_hours if recent_hours > 0 else 0
            baseline_rate = baseline / baseline_window if baseline_window > 0 else 0

            if baseline_rate > 0:
                change_pct = ((recent_rate - baseline_rate) / baseline_rate) * 100
            elif recent_rate > 0:
                change_pct = 100.0  # New activity
            else:
                change_pct = 0.0

            # Classify
            if change_pct > 50:
                trend = "SURGE"
            elif change_pct > 20:
                trend = "ELEVATED"
            elif change_pct < -50:
                trend = "DROP"
            elif change_pct < -20:
                trend = "DECLINING"
            else:
                trend = "NORMAL"

            trends.append(
                {
                    "category": cat,
                    "recent_count": recent,
                    "baseline_count": baseline,
                    "recent_rate_per_hr": round(recent_rate, 2),
                    "baseline_rate_per_hr": round(baseline_rate, 2),
                    "change_pct": round(change_pct, 1),
                    "trend": trend,
                }
            )

        # Sort by absolute change
        trends.sort(key=lambda t: abs(t["change_pct"]), reverse=True)

        surges = [t for t in trends if t["trend"] == "SURGE"]
        drops = [t for t in trends if t["trend"] == "DROP"]

        return {
            "recent_window_hours": recent_hours,
            "baseline_window_hours": baseline_hours,
            "categories_analyzed": len(trends),
            "surges": len(surges),
            "drops": len(drops),
            "trends": trends,
        }
