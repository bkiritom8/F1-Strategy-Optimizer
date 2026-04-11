"""
HTTPS enforcement and security middleware for FastAPI.
Includes TLS validation, security headers, and request validation.
"""

import logging
from typing import Callable, Dict, FrozenSet, Optional, Tuple

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from fastapi.middleware.cors import CORSMiddleware as FastAPICORSMiddleware
from .iam_simulator import iam_simulator, User

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce HTTPS connections"""

    def __init__(self, app: ASGIApp, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: Callable):
        # WebSocket upgrade requests must pass through — BaseHTTPMiddleware
        # cannot return a real response for them; attempting to do so breaks
        # the protocol handshake silently in production.
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        # Skip HTTPS enforcement for health checks
        if not self.enabled or request.url.path in ["/health", "/metrics"]:
            return await call_next(request)

        # Cloud Run terminates TLS externally; check forwarded proto header
        forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if forwarded_proto != "https":
            logger.warning(
                "Non-HTTPS request rejected: %s %s (x-forwarded-proto=%s)",
                request.method,
                request.url.path,
                forwarded_proto,
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "HTTPS required"},
            )

        response = await call_next(request)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers"""

    async def dispatch(self, request: Request, call_next: Callable):
        # Pass WebSocket upgrades through without touching headers
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        # connect-src must include wss: so browsers allow WebSocket connections
        # from the Vercel frontend to this Cloud Run backend.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com https://www.google-analytics.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' data: https://fonts.gstatic.com https://r2cdn.perplexity.ai; "
            "img-src 'self' data: https:; "
            "connect-src 'self' wss: https:;"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )

        return response


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Middleware for request validation and sanitization"""

    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB

    async def dispatch(self, request: Request, call_next: Callable):
        # WebSocket upgrade — skip HTTP-level validation entirely
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        # Check content length
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_CONTENT_LENGTH:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail": "Request body too large"},
            )

        # Validate request method
        allowed_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
        if request.method not in allowed_methods:
            return JSONResponse(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                content={"detail": f"Method {request.method} not allowed"},
            )

        # Check for common attack patterns in query params
        for key, value in request.query_params.items():
            if self._is_suspicious(value):
                logger.warning(f"Suspicious query parameter detected: {key}={value}")
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Invalid request parameters"},
                )

        response = await call_next(request)
        return response

    def _is_suspicious(self, value: str) -> bool:
        """Check for common attack patterns"""
        suspicious_patterns = [
            "<script",
            "javascript:",
            "onerror=",
            "onclick=",
            "../",
            "..\\",
            "SELECT * FROM",
            "DROP TABLE",
            "UNION SELECT",
            "; DROP",
        ]

        value_lower = value.lower()
        return any(pattern.lower() in value_lower for pattern in suspicious_patterns)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting middleware.

    Only requests whose paths start with one of the entries in ``limited_paths``
    count against the quota.  Pass an empty frozenset to rate-limit all paths.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_requests: int = 100,
        window_seconds: int = 3600,
        limited_paths: Optional[FrozenSet[str]] = None,
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # Paths that count against the quota (prefix match).
        # None / empty means every path is counted.
        self.limited_paths: FrozenSet[str] = limited_paths or frozenset()
        self.request_counts: Dict[str, Tuple[int, float]] = (
            {}
        )  # IP -> (count, window_start)

    def _is_limited(self, path: str) -> bool:
        """Return True if this path should be counted against the rate limit."""
        if not self.limited_paths:
            return True
        return any(path.startswith(prefix) for prefix in self.limited_paths)

    async def dispatch(self, request: Request, call_next: Callable):
        import time

        # WebSocket connections are long-lived — don't rate-limit the upgrade
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        path = request.url.path

        # Skip rate limiting for health checks and non-targeted paths
        if path in ("/health", "/metrics") or not self._is_limited(path):
            return await call_next(request)

        # Get client IP
        client_ip = request.client.host if request.client else "unknown"

        current_time = time.time()

        if client_ip in self.request_counts:
            count, window_start = self.request_counts[client_ip]

            # Reset window if expired
            if current_time - window_start > self.window_seconds:
                self.request_counts[client_ip] = (1, current_time)
            else:
                if count >= self.max_requests:
                    reset_at = int(window_start + self.window_seconds)
                    retry_after = max(0, reset_at - int(current_time))
                    logger.warning("Rate limit exceeded for %s (%s)", client_ip, path)
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={
                            "detail": "Rate limit exceeded. 100 requests per hour allowed."
                        },
                        headers={"Retry-After": str(retry_after)},
                    )
                self.request_counts[client_ip] = (count + 1, window_start)
        else:
            self.request_counts[client_ip] = (1, current_time)

        response = await call_next(request)

        # Add rate limit headers so clients can track their quota
        if client_ip in self.request_counts:
            count, window_start = self.request_counts[client_ip]
            response.headers["X-RateLimit-Limit"] = str(self.max_requests)
            response.headers["X-RateLimit-Remaining"] = str(
                max(0, self.max_requests - count)
            )
            response.headers["X-RateLimit-Reset"] = str(
                int(window_start + self.window_seconds)
            )

        return response


# Export standard CORSMiddleware to maintain interface compatibility
CORSMiddleware = FastAPICORSMiddleware


async def get_current_user(request: Request):
    """Extract and validate user from request.

    If no Bearer token is present, returns an anonymous read-only user so that
    public (unauthenticated) access works while the auth backend is being fixed.
    Authenticated requests are still validated normally so admin sessions work.
    """
    from src.security.iam_simulator import Role

    _ANONYMOUS_USER = User(
        username="anonymous",
        email="",
        full_name="Guest",
        roles=[Role.API_USER],
        disabled=False,
    )

    # No auth header — allow as anonymous
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return _ANONYMOUS_USER

    token = auth_header.split(" ")[1]

    # Verify token
    token_data = iam_simulator.verify_token(token)
    if not token_data or not token_data.username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from IAM simulator first (service accounts/admins)
    user_data = iam_simulator.users.get(token_data.username)

    if not user_data:
        # Fallback: check Firestore user_store for registered users
        from .user_store import user_store

        user_data = user_store.get(token_data.username)

    if not user_data or user_data.get("disabled"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
        )

    return User(**{k: v for k, v in user_data.items() if k != "hashed_password"})
