"""Structured daily intelligence summary.

Aggregates strategic posture, focal points, news clusters, temporal anomalies,
and keyword spikes into a structured briefing document. Pure data aggregation
with no LLM dependency.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger("world-intel-mcp.analysis.world_brief")


async def _safe(coro, label: str) -> dict:
    try:
        return await coro
    except Exception as exc:
        logger.warning("World brief: %s failed: %s", label, exc)
        return {}


async def fetch_world_brief(fetcher) -> dict:
    """Generate a structured daily intelligence summary.

    Calls 5 analysis functions in parallel and assembles a comprehensive
    briefing with sections: risk overview, focal areas, top stories,
    anomalies, and trending threats.
    """
    from .posture import fetch_strategic_posture
    from ..sources import intelligence
    from .clustering import fetch_news_clusters
    from .spikes import fetch_keyword_spikes

    (
        posture_data,
        focal_data,
        cluster_data,
        anomaly_data,
        spike_data,
    ) = await asyncio.gather(
        _safe(fetch_strategic_posture(fetcher), "strategic_posture"),
        _safe(intelligence.fetch_focal_points(fetcher), "focal_points"),
        _safe(fetch_news_clusters(fetcher), "news_clusters"),
        _safe(intelligence.fetch_temporal_anomalies(fetcher), "temporal_anomalies"),
        _safe(fetch_keyword_spikes(fetcher), "keyword_spikes"),
    )

    now = datetime.now(timezone.utc)

    # Section 1: Risk Overview (from strategic posture)
    risk_overview = {
        "composite_score": posture_data.get("composite_score", 0),
        "risk_level": posture_data.get("risk_level", "UNKNOWN"),
        "domain_summary": {},
    }
    for domain, info in posture_data.get("domain_scores", {}).items():
        risk_overview["domain_summary"][domain] = {
            "score": info.get("score", 0),
            "level": info.get("level", "UNKNOWN"),
        }

    # Section 2: Focal Areas (where attention should be)
    focal_areas = []
    for fp in (focal_data.get("focal_points") or [])[:8]:
        focal_areas.append({
            "entity": fp.get("entity", "unknown"),
            "entity_type": fp.get("entity_type", "unknown"),
            "signal_count": fp.get("signal_count", 0),
            "domains": fp.get("domains", []),
        })

    # Section 3: Top Stories (from news clusters)
    top_stories = []
    for cluster in (cluster_data.get("clusters") or [])[:6]:
        top_stories.append({
            "topic_keywords": cluster.get("keywords", [])[:5],
            "article_count": cluster.get("article_count", 0),
            "sources": cluster.get("sources", [])[:3],
            "headline": (cluster.get("items") or [{}])[0].get("title", "") if cluster.get("items") else "",
        })

    # Section 4: Anomalies (what's unusual today)
    anomalies = []
    for a in (anomaly_data.get("anomalies") or [])[:6]:
        anomalies.append({
            "metric": a.get("key", "unknown"),
            "z_score": a.get("z_score", 0),
            "current_value": a.get("current_value", 0),
            "baseline_mean": a.get("baseline_mean", 0),
            "description": a.get("description", ""),
        })

    # Section 5: Trending Threats (from keyword spikes + CVE/APT extraction)
    trending = {
        "spikes": (spike_data.get("spikes") or [])[:8],
        "spike_count": spike_data.get("spike_count", 0),
        "cve_mentions": spike_data.get("cve_mentions", []),
        "apt_mentions": spike_data.get("apt_mentions", []),
    }

    # Top threats from posture
    top_threats = posture_data.get("top_threats", [])[:5]

    return {
        "date": now.strftime("%Y-%m-%d"),
        "generated_at": now.isoformat(),
        "risk_overview": risk_overview,
        "top_threats": top_threats,
        "focal_areas": focal_areas,
        "focal_area_count": len(focal_areas),
        "top_stories": top_stories,
        "top_story_count": len(top_stories),
        "anomalies": anomalies,
        "anomaly_count": len(anomalies),
        "trending": trending,
        "source": "world-intelligence-brief",
    }
