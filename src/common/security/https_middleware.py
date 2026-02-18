"""
HTTPS enforcement and security middleware for FastAPI.
Includes TLS validation, security headers, and request validation.
"""

import logging
from typing import Callable, Dict, Tuple

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .iam_simulator import iam_simulator, Permission

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce HTTPS connections"""

    def __init__(self, app: ASGIApp, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip HTTPS enforcement for health checks and local dev
        if not self.enabled or request.url.path in ["/health", "/metrics"]:
            return await call_next(request)

        # Check if request is over HTTPS
        if request.url.scheme != "https":
            # In production, redirect to HTTPS
            # For local dev, log warning but allow
            logger.warning(
                f"Non-HTTPS request detected: {request.method} {request.url.path}"
            )

            # Uncomment for production:
            # return JSONResponse(
            #     status_code=status.HTTP_403_FORBIDDEN,
            #     content={"detail": "HTTPS required"}
            # )

        response = await call_next(request)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers"""

    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )

        return response


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Middleware for request validation and sanitization"""

    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB

    async def dispatch(self, request: Request, call_next: Callable):
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
    """Simple rate limiting middleware"""

    def __init__(self, app: ASGIApp, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.request_counts: Dict[str, Tuple[int, float]] = (
            {}
        )  # IP -> (count, window_start)

    async def dispatch(self, request: Request, call_next: Callable):
        import time

        # Get client IP
        client_ip = request.client.host if request.client else "unknown"

        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/metrics"]:
            return await call_next(request)

        # Check rate limit
        current_time = time.time()

        if client_ip in self.request_counts:
            count, window_start = self.request_counts[client_ip]

            # Reset window if expired
            if current_time - window_start > self.window_seconds:
                self.request_counts[client_ip] = (1, current_time)
            else:
                # Increment count
                if count >= self.max_requests:
                    logger.warning(f"Rate limit exceeded for {client_ip}")
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={"detail": "Rate limit exceeded"},
                        headers={"Retry-After": str(self.window_seconds)},
                    )

                self.request_counts[client_ip] = (count + 1, window_start)
        else:
            self.request_counts[client_ip] = (1, current_time)

        response = await call_next(request)

        # Add rate limit headers
        if client_ip in self.request_counts:
            count, _ = self.request_counts[client_ip]
            response.headers["X-RateLimit-Limit"] = str(self.max_requests)
            response.headers["X-RateLimit-Remaining"] = str(
                max(0, self.max_requests - count)
            )
            response.headers["X-RateLimit-Reset"] = str(
                int(current_time + self.window_seconds)
            )

        return response


class CORSMiddleware(BaseHTTPMiddleware):
    """CORS middleware with configurable origins"""

    def __init__(
        self, app: ASGIApp, allow_origins: list = None, allow_credentials: bool = True
    ):
        super().__init__(app)
        self.allow_origins = allow_origins or [
            "http://localhost:3000",
            "http://localhost:8080",
        ]
        self.allow_credentials = allow_credentials

    async def dispatch(self, request: Request, call_next: Callable):
        # Handle preflight requests
        if request.method == "OPTIONS":
            response = JSONResponse(content={}, status_code=200)
        else:
            response = await call_next(request)

        # Add CORS headers
        origin = request.headers.get("origin")
        if origin and (origin in self.allow_origins or "*" in self.allow_origins):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = str(
                self.allow_credentials
            ).lower()
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, DELETE, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, Authorization"
            )
            response.headers["Access-Control-Max-Age"] = "3600"

        return response


def verify_api_key(api_key: str) -> bool:
    """Verify API key (simple implementation for demo)"""
    valid_keys = {"dev-key-12345": "development", "prod-key-67890": "production"}
    return api_key in valid_keys


async def get_current_user(request: Request):
    """Extract and validate user from request"""

    # Check for Bearer token
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.split(" ")[1]

    # Verify token
    token_data = iam_simulator.verify_token(token)
    if not token_data or not token_data.username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from IAM simulator
    user_data = iam_simulator.users.get(token_data.username)
    if not user_data or user_data.get("disabled"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
        )

    from .iam_simulator import User

    return User(**{k: v for k, v in user_data.items() if k != "hashed_password"})


def require_permission(required_permission: Permission):
    """Decorator to require specific permission"""

    async def permission_checker(request: Request):
        user = await get_current_user(request)

        if not iam_simulator.check_permission(user, required_permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {required_permission.value} required",
            )

        return user

    return permission_checker
