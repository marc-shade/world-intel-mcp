"""Tests for the vector store module — uses mocks for Qdrant and FastEmbed."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from world_intel_mcp import vector_store as vs
from world_intel_mcp.vector_store import (
    COLLECTION_NAME,
    DOMAIN_CATEGORIES,
    EMBEDDING_DIM,
    MAX_EMBED_CHARS,
    VectorStore,
    _content_hash,
    _data_to_text,
)

# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------

FAKE_VECTOR = [0.01] * EMBEDDING_DIM


def _make_scored_point(
    point_id: int,
    score: float,
    domain: str = "markets",
    category: str = "Financial Markets",
    text: str = "S&P 500 up 0.4%",
    timestamp: float | None = None,
    event_count: int | None = None,
    country: str | None = None,
    has_error: bool = False,
) -> SimpleNamespace:
    """Simulate a qdrant_client ScoredPoint / Record."""
    payload = {
        "domain": domain,
        "category": category,
        "text": text,
        "timestamp": timestamp or time.time(),
        "datetime": "2026-03-08T12:00:00+00:00",
        "has_error": has_error,
    }
    if event_count is not None:
        payload["event_count"] = event_count
    if country is not None:
        payload["country"] = country
    return SimpleNamespace(id=point_id, score=score, payload=payload)


def _make_record(
    point_id: int,
    domain: str = "markets",
    category: str = "Financial Markets",
    timestamp: float | None = None,
    event_count: int | None = None,
) -> SimpleNamespace:
    """Simulate a qdrant_client Record (scroll results)."""
    payload = {
        "domain": domain,
        "category": category,
        "timestamp": timestamp or time.time(),
        "has_error": False,
    }
    if event_count is not None:
        payload["event_count"] = event_count
    return SimpleNamespace(id=point_id, payload=payload)


@pytest.fixture(autouse=True)
def _reset_globals():
    """Reset module-level singletons between tests."""
    vs._embed_model = None
    vs._qdrant_client = None
    yield
    vs._embed_model = None
    vs._qdrant_client = None


@pytest.fixture
def mock_embed():
    """Patch _embed_text to return a fixed vector (avoids fastembed import)."""
    with patch.object(vs, "_embed_text", return_value=FAKE_VECTOR):
        yield


@pytest.fixture
def mock_qdrant():
    """Patch _get_qdrant to return a mock Qdrant client."""
    client = MagicMock()
    # Default: search returns empty
    client.search.return_value = []
    # Default: scroll returns ([], None) meaning no results, no next offset
    client.scroll.return_value = ([], None)
    # Default: get_collection returns a stats-like object
    coll_info = SimpleNamespace(
        points_count=42,
        vectors_count=42,
        indexed_vectors_count=40,
        status=SimpleNamespace(value="green"),
    )
    client.get_collection.return_value = coll_info
    with patch.object(vs, "_get_qdrant", return_value=client):
        yield client


@pytest.fixture
def store():
    """Return a VectorStore instance (not started)."""
    return VectorStore(enabled=True)


# ===================================================================
# Pure-function tests (no async, no mocks needed)
# ===================================================================


class TestDataToText:
    """Test _data_to_text with various domain data shapes."""

    def test_string_passthrough(self):
        assert _data_to_text("news", "Breaking headline") == "Breaking headline"

    def test_non_dict_non_string(self):
        result = _data_to_text("other", [1, 2, 3])
        assert result == "[1, 2, 3]"

    def test_dict_with_events_list(self):
        data = {
            "events": [
                {
                    "title": "Earthquake in Turkey",
                    "country": "Turkey",
                    "description": "M7.2",
                },
                {"title": "Flood warning", "location": "Germany"},
            ],
            "count": 2,
        }
        text = _data_to_text("seismology", data)
        assert "Domain: seismology" in text
        assert "Earthquake in Turkey" in text
        assert "Turkey" in text
        assert "M7.2" in text
        assert "Flood warning" in text
        assert "count: 2" in text

    def test_dict_with_articles(self):
        data = {
            "articles": [{"headline": "AI advance", "summary": "New model released"}]
        }
        text = _data_to_text("news", data)
        assert "AI advance" in text
        assert "New model released" in text

    def test_dict_with_items_string_entries(self):
        data = {"items": ["alert one", "alert two"]}
        text = _data_to_text("cyber", data)
        assert "alert one" in text
        assert "alert two" in text

    def test_top_level_summary_fields(self):
        data = {"summary": "All clear", "status": "nominal"}
        text = _data_to_text("infrastructure", data)
        assert "summary: All clear" in text
        assert "status: nominal" in text

    def test_geographic_context(self):
        data = {"country": "France", "region": "Europe"}
        text = _data_to_text("conflict", data)
        assert "country: France" in text
        assert "region: Europe" in text

    def test_truncation_at_max_chars(self):
        data = {"summary": "x" * 5000}
        text = _data_to_text("test", data)
        assert len(text) <= MAX_EMBED_CHARS

    def test_items_cap_at_20(self):
        data = {"events": [{"title": f"event-{i}"} for i in range(30)]}
        text = _data_to_text("news", data)
        # event-19 should appear (index 19 = 20th item), event-20 should not
        assert "event-19" in text
        assert "event-20" not in text


class TestContentHash:
    """Test _content_hash deduplication."""

    def test_same_input_same_hash(self):
        h1 = _content_hash("markets", {"price": 100})
        h2 = _content_hash("markets", {"price": 100})
        assert h1 == h2

    def test_different_domain_different_hash(self):
        h1 = _content_hash("markets", {"price": 100})
        h2 = _content_hash("crypto", {"price": 100})
        assert h1 != h2

    def test_different_data_different_hash(self):
        h1 = _content_hash("markets", {"price": 100})
        h2 = _content_hash("markets", {"price": 200})
        assert h1 != h2

    def test_hash_length(self):
        h = _content_hash("x", {"a": 1})
        assert len(h) == 16

    def test_deterministic_sort_keys(self):
        h1 = _content_hash("x", {"b": 2, "a": 1})
        h2 = _content_hash("x", {"a": 1, "b": 2})
        assert h1 == h2


class TestDomainCategories:
    """Test the DOMAIN_CATEGORIES mapping."""

    def test_known_domains(self):
        assert DOMAIN_CATEGORIES["markets"] == "Financial Markets"
        assert DOMAIN_CATEGORIES["seismology"] == "Natural Disasters"
        assert DOMAIN_CATEGORIES["cyber"] == "Cyber Threats"
        assert DOMAIN_CATEGORIES["adsblol"] == "Military & Defense"
        assert DOMAIN_CATEGORIES["acled"] == "Conflict & Security"

    def test_granular_source_names(self):
        assert DOMAIN_CATEGORIES["sans-dshield"] == "Cyber Threats"
        assert DOMAIN_CATEGORIES["mempool"] == "Cryptocurrency"
        assert DOMAIN_CATEGORIES["who-don"] == "Health"
        assert DOMAIN_CATEGORIES["noaa-swpc"] == "Space Weather"

    def test_all_values_are_strings(self):
        for k, v in DOMAIN_CATEGORIES.items():
            assert isinstance(k, str)
            assert isinstance(v, str)


class TestExtractGeo:
    """Test VectorStore._extract_geo static method."""

    def test_direct_lat_lon(self):
        data = {"latitude": 35.6, "longitude": 139.7}
        geo = VectorStore._extract_geo(data)
        assert geo == {"lat": 35.6, "lon": 139.7}

    def test_short_lat_lon(self):
        data = {"lat": 40.7, "lon": -74.0}
        geo = VectorStore._extract_geo(data)
        assert geo == {"lat": 40.7, "lon": -74.0}

    def test_country_only(self):
        data = {"country": "Japan"}
        geo = VectorStore._extract_geo(data)
        assert geo == {"country": "Japan"}

    def test_geo_from_events_list(self):
        data = {"events": [{"latitude": 10.0, "longitude": 20.0, "country": "SY"}]}
        geo = VectorStore._extract_geo(data)
        assert geo["lat"] == 10.0
        assert geo["lon"] == 20.0

    def test_none_for_non_dict(self):
        assert VectorStore._extract_geo("text") is None
        assert VectorStore._extract_geo(42) is None

    def test_none_for_empty_dict(self):
        assert VectorStore._extract_geo({}) is None


# ===================================================================
# VectorStore lifecycle tests
# ===================================================================


class TestVectorStoreLifecycle:
    """Test start/stop and the fire-and-forget queue."""

    async def test_start_creates_queue_and_worker(self):
        s = VectorStore(enabled=True)
        await s.start()
        assert s._store_queue is not None
        assert s._worker_task is not None
        assert not s._worker_task.done()
        await s.stop()

    async def test_stop_cancels_worker(self):
        s = VectorStore(enabled=True)
        await s.start()
        task = s._worker_task
        await s.stop()
        assert task.cancelled() or task.done()
        assert s._worker_task is None

    async def test_disabled_store_skips_start(self):
        s = VectorStore(enabled=False)
        await s.start()
        assert s._store_queue is None
        assert s._worker_task is None

    async def test_stop_without_start_is_safe(self):
        s = VectorStore(enabled=True)
        await s.stop()  # Should not raise


# ===================================================================
# store() method tests
# ===================================================================


class TestStoreMethod:
    """Test the async store (queue) method."""

    async def test_store_enqueues(self):
        s = VectorStore(enabled=True)
        await s.start()
        # Don't actually process — just check the queue
        await s.store("markets", {"quotes": [{"symbol": "AAPL", "name": "Apple"}]})
        assert s._store_queue.qsize() == 1
        await s.stop()

    async def test_store_skips_error_data(self):
        s = VectorStore(enabled=True)
        await s.start()
        await s.store("markets", {"error": "API timeout"})
        assert s._store_queue.qsize() == 0
        await s.stop()

    async def test_store_skips_when_disabled(self):
        s = VectorStore(enabled=False)
        await s.start()
        await s.store("markets", {"price": 100})
        # Queue was never created
        assert s._store_queue is None

    async def test_store_drops_on_full_queue(self):
        s = VectorStore(enabled=True)
        await s.start()
        # Manually fill queue to maxsize without processing
        s._worker_task.cancel()
        try:
            await s._worker_task
        except asyncio.CancelledError:
            pass
        for i in range(500):
            await s.store("test", {"n": i})
        # 501st should be silently dropped
        await s.store("test", {"n": 500})
        assert s._store_queue.qsize() == 500
        await s.stop()


# ===================================================================
# _store_sync tests (synchronous path, mocked)
# ===================================================================


class TestStoreSync:
    """Test _store_sync writes to Qdrant correctly."""

    def test_store_sync_upserts_point(self, mock_qdrant, mock_embed):
        s = VectorStore(enabled=True)
        data = {
            "events": [{"title": "Major earthquake in Chile", "country": "Chile"}],
            "count": 3,
        }
        s._store_sync("seismology", data, time.time())

        mock_qdrant.upsert.assert_called_once()
        call_kwargs = mock_qdrant.upsert.call_args
        assert call_kwargs.kwargs["collection_name"] == COLLECTION_NAME
        points = call_kwargs.kwargs["points"]
        assert len(points) == 1
        payload = points[0].payload
        assert payload["domain"] == "seismology"
        assert payload["category"] == "Natural Disasters"
        assert payload["event_count"] == 3
        assert payload["has_error"] is False

    def test_store_sync_skips_short_text(self, mock_qdrant, mock_embed):
        s = VectorStore(enabled=True)
        # _data_to_text for a string returns it directly; "tiny" is 4 chars < 20
        s._store_sync("test", "tiny", time.time())
        mock_qdrant.upsert.assert_not_called()

    def test_store_sync_prefix_category_fallback(self, mock_qdrant, mock_embed):
        """Domains with colon separators fall back to prefix match."""
        s = VectorStore(enabled=True)
        data = {"events": [{"title": "BBC headline about conflict in Sudan"}]}
        s._store_sync("rss:bbc_world", data, time.time())

        mock_qdrant.upsert.assert_called_once()
        payload = mock_qdrant.upsert.call_args.kwargs["points"][0].payload
        assert payload["category"] == "News & Media"

    def test_store_sync_unknown_domain_gets_other(self, mock_qdrant, mock_embed):
        s = VectorStore(enabled=True)
        data = {"summary": "Something from an unknown source domain entirely"}
        s._store_sync("totally_unknown_domain", data, time.time())

        mock_qdrant.upsert.assert_called_once()
        payload = mock_qdrant.upsert.call_args.kwargs["points"][0].payload
        assert payload["category"] == "Other"

    def test_store_sync_includes_geo(self, mock_qdrant, mock_embed):
        s = VectorStore(enabled=True)
        data = {
            "events": [{"title": "Test event with location data"}],
            "latitude": 35.0,
            "longitude": 139.0,
        }
        s._store_sync("seismology", data, time.time())

        payload = mock_qdrant.upsert.call_args.kwargs["points"][0].payload
        assert payload["lat"] == 35.0
        assert payload["lon"] == 139.0


# ===================================================================
# semantic_search tests
# ===================================================================


class TestSemanticSearch:
    """Test semantic_search with mocked Qdrant."""

    async def test_basic_search(self, store, mock_qdrant, mock_embed):
        mock_qdrant.search.return_value = [
            _make_scored_point(1, 0.95, domain="markets", text="S&P 500 rallied"),
            _make_scored_point(
                2, 0.80, domain="crypto", category="Cryptocurrency", text="BTC up 5%"
            ),
        ]

        result = await store.semantic_search("stock market gains")

        assert result["query"] == "stock market gains"
        assert result["count"] == 2
        assert result["results"][0]["score"] == 0.95
        assert result["results"][0]["domain"] == "markets"
        assert result["results"][1]["domain"] == "crypto"
        mock_qdrant.search.assert_called_once()

    async def test_search_with_domain_filter(self, store, mock_qdrant, mock_embed):
        mock_qdrant.search.return_value = []
        await store.semantic_search("test", domain="cyber")

        call_kwargs = mock_qdrant.search.call_args.kwargs
        query_filter = call_kwargs["query_filter"]
        # Should have domain condition + has_error condition
        assert query_filter is not None

    async def test_search_with_hours_filter(self, store, mock_qdrant, mock_embed):
        mock_qdrant.search.return_value = []
        result = await store.semantic_search("test", hours=12.0)

        assert result["filters"]["hours"] == 12.0

    async def test_search_returns_country(self, store, mock_qdrant, mock_embed):
        mock_qdrant.search.return_value = [
            _make_scored_point(1, 0.9, country="Ukraine"),
        ]
        result = await store.semantic_search("conflict events")
        assert result["results"][0]["country"] == "Ukraine"


# ===================================================================
# find_similar tests
# ===================================================================


class TestFindSimilar:
    """Test find_similar with mocked Qdrant."""

    async def test_basic_similar(self, store, mock_qdrant, mock_embed):
        mock_qdrant.search.return_value = [
            _make_scored_point(
                10, 0.88, domain="seismology", text="M6.1 quake near Tokyo"
            ),
        ]

        result = await store.find_similar("seismology", "earthquake Japan")

        assert result["reference_domain"] == "seismology"
        assert result["reference_text"] == "earthquake Japan"
        assert result["count"] == 1
        assert result["similar"][0]["score"] == 0.88

    async def test_similar_with_hours(self, store, mock_qdrant, mock_embed):
        mock_qdrant.search.return_value = []
        result = await store.find_similar("markets", "crash", hours=48.0)
        assert result["count"] == 0

    async def test_similar_truncates_reference_text(
        self, store, mock_qdrant, mock_embed
    ):
        mock_qdrant.search.return_value = []
        long_text = "x" * 500
        result = await store.find_similar("markets", long_text)
        assert len(result["reference_text"]) == 200


# ===================================================================
# timeline tests
# ===================================================================


class TestTimeline:
    """Test timeline with mocked Qdrant scroll."""

    async def test_basic_timeline(self, store, mock_qdrant, mock_embed):
        now = time.time()
        mock_qdrant.scroll.return_value = (
            [
                _make_record(
                    1, domain="cyber", category="Cyber Threats", timestamp=now - 100
                ),
                _make_record(2, domain="markets", timestamp=now - 50),
            ],
            None,
        )

        result = await store.timeline(hours=24.0)

        assert result["hours"] == 24.0
        assert result["count"] == 2
        # Should be sorted most-recent first
        assert result["entries"][0]["timestamp"] > result["entries"][1]["timestamp"]

    async def test_timeline_with_domain_filter(self, store, mock_qdrant, mock_embed):
        mock_qdrant.scroll.return_value = ([], None)
        result = await store.timeline(domain="cyber")

        assert result["filters"]["domain"] == "cyber"

    async def test_timeline_with_category_filter(self, store, mock_qdrant, mock_embed):
        mock_qdrant.scroll.return_value = ([], None)
        result = await store.timeline(category="Cyber Threats")

        assert result["filters"]["category"] == "Cyber Threats"


# ===================================================================
# collection_stats tests
# ===================================================================


class TestCollectionStats:
    """Test collection_stats."""

    async def test_stats_returns_info(self, store, mock_qdrant):
        result = await store.collection_stats()

        assert result["enabled"] is True
        assert result["collection"] == COLLECTION_NAME
        assert result["points_count"] == 42
        assert result["vectors_count"] == 42
        assert result["status"] == "green"
        assert result["embedding_dim"] == EMBEDDING_DIM

    async def test_stats_handles_exception(self):
        s = VectorStore(enabled=True)
        with patch.object(vs, "_get_qdrant", side_effect=ConnectionError("refused")):
            result = await s.collection_stats()
            assert "error" in result
            assert result["enabled"] is True


# ===================================================================
# cross_domain_correlate tests (Phase 17)
# ===================================================================


class TestCrossDomainCorrelate:
    """Test cross_domain_correlate groups by category and sorts by score."""

    async def test_groups_by_category(self, store, mock_qdrant, mock_embed):
        mock_qdrant.search.return_value = [
            _make_scored_point(
                1,
                0.95,
                domain="markets",
                category="Financial Markets",
                text="Stocks drop",
            ),
            _make_scored_point(
                2,
                0.90,
                domain="cyber",
                category="Cyber Threats",
                text="Ransomware spike",
            ),
            _make_scored_point(
                3, 0.85, domain="crypto", category="Cryptocurrency", text="BTC crash"
            ),
            _make_scored_point(
                4,
                0.80,
                domain="bonds",
                category="Financial Markets",
                text="Yields surge",
            ),
        ]

        result = await store.cross_domain_correlate("global instability")

        assert result["query"] == "global instability"
        assert (
            result["domains_found"] == 3
        )  # Financial Markets, Cyber Threats, Cryptocurrency
        assert result["total_signals"] == 4

        # First correlation should be Financial Markets (best score 0.95)
        corrs = result["correlations"]
        assert corrs[0]["category"] == "Financial Markets"
        assert corrs[0]["signal_count"] == 2
        assert corrs[0]["best_score"] == 0.95

    async def test_respects_limit_per_domain(self, store, mock_qdrant, mock_embed):
        # All same category, but limit_per_domain=2
        mock_qdrant.search.return_value = [
            _make_scored_point(i, 0.9 - i * 0.01, category="Financial Markets")
            for i in range(10)
        ]

        result = await store.cross_domain_correlate("test", limit_per_domain=2)

        fm = [c for c in result["correlations"] if c["category"] == "Financial Markets"]
        assert len(fm) == 1
        assert fm[0]["signal_count"] == 2

    async def test_empty_results(self, store, mock_qdrant, mock_embed):
        mock_qdrant.search.return_value = []
        result = await store.cross_domain_correlate("nothing matches")

        assert result["domains_found"] == 0
        assert result["correlations"] == []
        assert result["total_signals"] == 0

    async def test_hours_filter_applied(self, store, mock_qdrant, mock_embed):
        mock_qdrant.search.return_value = []
        await store.cross_domain_correlate("test", hours=12.0)

        call_kwargs = mock_qdrant.search.call_args.kwargs
        assert call_kwargs["limit"] == 100  # Fetches 100 for cross-domain spread


# ===================================================================
# domain_summary tests (Phase 17)
# ===================================================================


class TestDomainSummary:
    """Test domain_summary aggregation."""

    async def test_aggregates_by_category(self, store, mock_qdrant, mock_embed):
        now = time.time()
        mock_qdrant.scroll.return_value = (
            [
                _make_record(
                    1,
                    domain="markets",
                    category="Financial Markets",
                    timestamp=now - 100,
                    event_count=5,
                ),
                _make_record(
                    2, domain="crypto", category="Cryptocurrency", timestamp=now - 200
                ),
                _make_record(
                    3,
                    domain="bonds",
                    category="Financial Markets",
                    timestamp=now - 50,
                    event_count=3,
                ),
            ],
            None,
        )

        result = await store.domain_summary(hours=24.0)

        assert result["hours"] == 24.0
        assert result["total_data_points"] == 3
        assert result["categories"] == 2

        # Financial Markets should be first (count=2 > count=1)
        fm = result["summary"][0]
        assert fm["category"] == "Financial Markets"
        assert fm["data_points"] == 2
        assert fm["unique_sources"] == 2
        assert set(fm["sources"]) == {"markets", "bonds"}
        assert fm["total_events_tracked"] == 8  # 5 + 3

    async def test_pagination(self, store, mock_qdrant, mock_embed):
        """Test that domain_summary paginates via scroll offset."""
        batch1 = [_make_record(i, domain="markets") for i in range(200)]
        batch2 = [
            _make_record(200 + i, domain="cyber", category="Cyber Threats")
            for i in range(3)
        ]

        mock_qdrant.scroll.side_effect = [
            (batch1, "offset_abc"),  # First page, has next
            (batch2, None),  # Second page, done
        ]

        result = await store.domain_summary(hours=48.0)

        assert result["total_data_points"] == 203
        assert mock_qdrant.scroll.call_count == 2

    async def test_empty_summary(self, store, mock_qdrant, mock_embed):
        mock_qdrant.scroll.return_value = ([], None)
        result = await store.domain_summary()

        assert result["total_data_points"] == 0
        assert result["categories"] == 0
        assert result["summary"] == []

    async def test_event_count_none_when_zero(self, store, mock_qdrant, mock_embed):
        """When no event_count fields present, total_events_tracked should be None."""
        mock_qdrant.scroll.return_value = (
            [_make_record(1, domain="news", category="News & Media")],
            None,
        )
        result = await store.domain_summary()
        assert result["summary"][0]["total_events_tracked"] is None


# ===================================================================
# trend_detection tests (Phase 17)
# ===================================================================


class TestTrendDetection:
    """Test trend_detection comparing recent vs baseline windows."""

    async def test_surge_detection(self, store, mock_qdrant, mock_embed):
        """Recent activity >> baseline rate should yield SURGE."""
        now = time.time()

        def scroll_side_effect(**kwargs):
            filt = kwargs.get("scroll_filter")
            # Inspect timestamp range to determine which window this is
            # We rely on call order: recent window first, then baseline
            return ([], None)

        # First call = recent window, second call = baseline window
        recent_records = [_make_record(i, category="Cyber Threats") for i in range(10)]
        baseline_records = [
            _make_record(100 + i, category="Cyber Threats") for i in range(2)
        ]

        mock_qdrant.scroll.side_effect = [
            (recent_records, None),  # recent: 10 points in 6h
            (baseline_records, None),  # baseline: 2 points in 42h
        ]

        result = await store.trend_detection(recent_hours=6.0, baseline_hours=48.0)

        assert result["recent_window_hours"] == 6.0
        assert result["baseline_window_hours"] == 48.0
        assert result["categories_analyzed"] == 1
        assert result["surges"] == 1

        trend = result["trends"][0]
        assert trend["category"] == "Cyber Threats"
        assert trend["recent_count"] == 10
        assert trend["baseline_count"] == 2
        assert trend["trend"] == "SURGE"

    async def test_drop_detection(self, store, mock_qdrant, mock_embed):
        """Low recent activity vs high baseline should yield DROP."""
        recent_records = [_make_record(1, category="Financial Markets")]
        baseline_records = [
            _make_record(100 + i, category="Financial Markets") for i in range(50)
        ]

        mock_qdrant.scroll.side_effect = [
            (recent_records, None),  # recent: 1 in 6h
            (baseline_records, None),  # baseline: 50 in 42h
        ]

        result = await store.trend_detection(recent_hours=6.0, baseline_hours=48.0)
        trend = result["trends"][0]
        assert trend["trend"] == "DROP"
        assert result["drops"] == 1

    async def test_normal_trend(self, store, mock_qdrant, mock_embed):
        """Similar rates should yield NORMAL."""
        # 6 points in 6h recent = 1/hr, baseline: 42 in 42h = 1/hr
        recent_records = [_make_record(i, category="News & Media") for i in range(6)]
        baseline_records = [
            _make_record(100 + i, category="News & Media") for i in range(42)
        ]

        mock_qdrant.scroll.side_effect = [
            (recent_records, None),
            (baseline_records, None),
        ]

        result = await store.trend_detection(recent_hours=6.0, baseline_hours=48.0)
        trend = result["trends"][0]
        assert trend["trend"] == "NORMAL"

    async def test_new_activity_is_100pct(self, store, mock_qdrant, mock_embed):
        """Activity only in recent window (none in baseline) = 100% change."""
        recent_records = [_make_record(1, category="Space Weather")]

        mock_qdrant.scroll.side_effect = [
            (recent_records, None),
            ([], None),  # No baseline
        ]

        result = await store.trend_detection(recent_hours=6.0, baseline_hours=48.0)
        trend = result["trends"][0]
        assert trend["change_pct"] == 100.0
        assert trend["trend"] == "SURGE"

    async def test_category_filter(self, store, mock_qdrant, mock_embed):
        """When category is specified, it should be passed in the filter."""
        mock_qdrant.scroll.side_effect = [([], None), ([], None)]

        result = await store.trend_detection(category="Cyber Threats")
        assert result["categories_analyzed"] == 0

    async def test_multiple_categories(self, store, mock_qdrant, mock_embed):
        """Multiple categories should each get their own trend entry."""
        recent = [
            _make_record(1, category="Cyber Threats"),
            _make_record(2, category="Financial Markets"),
            _make_record(3, category="Cyber Threats"),
        ]
        baseline = [_make_record(10, category="Financial Markets")]

        mock_qdrant.scroll.side_effect = [
            (recent, None),
            (baseline, None),
        ]

        result = await store.trend_detection(recent_hours=6.0, baseline_hours=48.0)
        assert result["categories_analyzed"] == 2
        cats = {t["category"] for t in result["trends"]}
        assert "Cyber Threats" in cats
        assert "Financial Markets" in cats

    async def test_sorted_by_absolute_change(self, store, mock_qdrant, mock_embed):
        """Trends should be sorted by absolute change_pct descending."""
        recent = [
            _make_record(1, category="A"),
            _make_record(2, category="B"),
            _make_record(3, category="B"),
            _make_record(4, category="B"),
        ]
        baseline = [
            _make_record(10, category="A"),
            _make_record(11, category="A"),
            _make_record(12, category="A"),
        ]

        mock_qdrant.scroll.side_effect = [
            (recent, None),
            (baseline, None),
        ]

        result = await store.trend_detection(recent_hours=6.0, baseline_hours=48.0)
        changes = [abs(t["change_pct"]) for t in result["trends"]]
        assert changes == sorted(changes, reverse=True)
