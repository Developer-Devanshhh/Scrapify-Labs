"""
Tests for Scrapify Labs API endpoints.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def client():
    """Async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "ScrapifyLabs"
        assert "configured_platforms" in data

    @pytest.mark.asyncio
    async def test_health_has_uptime(self, client):
        resp = await client.get("/health")
        data = resp.json()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], (int, float))


class TestPlatformsEndpoint:
    @pytest.mark.asyncio
    async def test_list_platforms(self, client):
        resp = await client.get("/api/platforms")
        assert resp.status_code == 200
        data = resp.json()
        assert "platforms" in data
        platform_names = [p["name"] for p in data["platforms"]]
        assert "reddit" in platform_names
        assert "youtube" in platform_names
        assert "twitter" in platform_names


class TestResultsEndpoint:
    @pytest.mark.asyncio
    async def test_empty_results(self, client):
        resp = await client.get("/api/results")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["results"] == []
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_results_with_platform_filter(self, client):
        resp = await client.get("/api/results?platform=reddit")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_results_by_platform_path(self, client):
        resp = await client.get("/api/results/reddit")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data


class TestJobsEndpoint:
    @pytest.mark.asyncio
    async def test_empty_jobs(self, client):
        resp = await client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestDeleteEndpoint:
    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, client):
        resp = await client.delete("/api/results/nonexistent-id")
        assert resp.status_code == 404
