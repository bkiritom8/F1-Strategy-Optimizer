"""Tests for src/security/https_middleware.py"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.security.https_middleware import (
    CORSMiddleware,
    HTTPSRedirectMiddleware,
    RateLimitMiddleware,
    RequestValidationMiddleware,
    SecurityHeadersMiddleware,
)


def _make_app(*middlewares):
    app = FastAPI()
    for mw, kwargs in reversed(middlewares):
        app.add_middleware(mw, **kwargs)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "healthy"}

    return app


class TestSecurityHeadersMiddleware:
    @pytest.fixture
    def client(self):
        app = _make_app((SecurityHeadersMiddleware, {}))
        return TestClient(app)

    def test_x_content_type_options(self, client):
        r = client.get("/ping")
        assert r.headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options(self, client):
        r = client.get("/ping")
        assert r.headers["X-Frame-Options"] == "DENY"

    def test_hsts_header(self, client):
        r = client.get("/ping")
        assert "max-age=31536000" in r.headers["Strict-Transport-Security"]

    def test_csp_header(self, client):
        r = client.get("/ping")
        expected_csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com https://www.google-analytics.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' data: https://fonts.gstatic.com https://r2cdn.perplexity.ai; "
            "img-src 'self' data: https:; "
            "connect-src 'self' wss: https:;"
        )
        assert r.headers["Content-Security-Policy"] == expected_csp

    def test_referrer_policy(self, client):
        r = client.get("/ping")
        assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_permissions_policy(self, client):
        r = client.get("/ping")
        assert "geolocation=()" in r.headers["Permissions-Policy"]


class TestRequestValidationMiddleware:
    @pytest.fixture
    def client(self):
        app = _make_app((RequestValidationMiddleware, {}))
        return TestClient(app)

    def test_normal_request_passes(self, client):
        r = client.get("/ping")
        assert r.status_code == 200

    def test_large_content_length_rejected(self, client):
        r = client.get("/ping", headers={"content-length": str(11 * 1024 * 1024)})
        assert r.status_code == 413

    def test_sql_injection_in_query_rejected(self, client):
        r = client.get("/ping", params={"q": "SELECT * FROM users"})
        assert r.status_code == 400

    def test_xss_in_query_rejected(self, client):
        r = client.get("/ping", params={"q": "<script>alert(1)</script>"})
        assert r.status_code == 400

    def test_path_traversal_rejected(self, client):
        r = client.get("/ping", params={"file": "../../../etc/passwd"})
        assert r.status_code == 400

    def test_drop_table_rejected(self, client):
        r = client.get("/ping", params={"q": "DROP TABLE users"})
        assert r.status_code == 400

    def test_clean_query_params_allowed(self, client):
        r = client.get("/ping", params={"driver": "max_verstappen"})
        assert r.status_code == 200


class TestRateLimitMiddleware:
    def test_requests_within_limit_succeed(self):
        app = _make_app((RateLimitMiddleware, {"max_requests": 10, "window_seconds": 60}))
        client = TestClient(app)
        for _ in range(5):
            r = client.get("/ping")
            assert r.status_code == 200

    def test_exceeding_limit_returns_429(self):
        app = _make_app((RateLimitMiddleware, {"max_requests": 3, "window_seconds": 60}))
        client = TestClient(app)
        for _ in range(3):
            client.get("/ping")
        r = client.get("/ping")
        assert r.status_code == 429

    def test_health_endpoint_bypasses_rate_limit(self):
        app = _make_app((RateLimitMiddleware, {"max_requests": 1, "window_seconds": 60}))
        client = TestClient(app)
        client.get("/ping")  # consume the 1 allowed request
        for _ in range(5):
            r = client.get("/health")
            assert r.status_code == 200

    def test_rate_limit_headers_present(self):
        app = _make_app((RateLimitMiddleware, {"max_requests": 10, "window_seconds": 60}))
        client = TestClient(app)
        r = client.get("/ping")
        assert "X-RateLimit-Limit" in r.headers
        assert "X-RateLimit-Remaining" in r.headers

    def test_retry_after_header_on_429(self):
        app = _make_app((RateLimitMiddleware, {"max_requests": 1, "window_seconds": 30}))
        client = TestClient(app)
        client.get("/ping")
        r = client.get("/ping")
        assert r.status_code == 429
        assert r.headers.get("Retry-After") == "30"


class TestCORSMiddleware:
    def test_allowed_origin_gets_cors_headers(self):
        app = _make_app((CORSMiddleware, {"allow_origins": ["http://localhost:3000"]}))
        client = TestClient(app)
        r = client.get("/ping", headers={"Origin": "http://localhost:3000"})
        assert r.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"

    def test_disallowed_origin_no_cors_header(self):
        app = _make_app((CORSMiddleware, {"allow_origins": ["http://localhost:3000"]}))
        client = TestClient(app)
        r = client.get("/ping", headers={"Origin": "http://evil.com"})
        assert "Access-Control-Allow-Origin" not in r.headers

    def test_preflight_options_returns_200(self):
        app = _make_app((CORSMiddleware, {"allow_origins": ["http://localhost:3000"], "allow_methods": ["*"]}))
        client = TestClient(app)
        r = client.options("/ping", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        })
        assert r.status_code == 200

    def test_wildcard_origin_allows_all(self):
        app = _make_app((CORSMiddleware, {"allow_origins": ["*"]}))
        client = TestClient(app)
        r = client.get("/ping", headers={"Origin": "http://anything.com"})
        assert r.headers.get("Access-Control-Allow-Origin") == "*"

    def test_cors_allow_methods_header(self):
        app = _make_app((CORSMiddleware, {"allow_origins": ["http://localhost:3000"], "allow_methods": ["*"]}))
        client = TestClient(app)
        r = client.options("/ping", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        })
        assert "GET" in r.headers.get("Access-Control-Allow-Methods", "")


class TestHTTPSRedirectMiddleware:
    def test_disabled_allows_http(self):
        app = _make_app((HTTPSRedirectMiddleware, {"enabled": False}))
        client = TestClient(app)
        r = client.get("/ping")
        assert r.status_code == 200

    def test_health_bypasses_https_check(self):
        app = _make_app((HTTPSRedirectMiddleware, {"enabled": True}))
        client = TestClient(app)
        r = client.get("/health")
        assert r.status_code == 200

    def test_enabled_blocks_http_without_forwarded_proto(self):
        app = _make_app((HTTPSRedirectMiddleware, {"enabled": True}))
        client = TestClient(app)
        r = client.get("/ping")
        # HTTPS enforcement: plain HTTP (no x-forwarded-proto) returns 403
        assert r.status_code == 403
        assert r.json() == {"detail": "HTTPS required"}

    def test_enabled_allows_https_via_forwarded_proto(self):
        app = _make_app((HTTPSRedirectMiddleware, {"enabled": True}))
        client = TestClient(app)
        r = client.get("/ping", headers={"x-forwarded-proto": "https"})
        assert r.status_code == 200
