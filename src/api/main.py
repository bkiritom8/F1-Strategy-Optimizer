"""
F1 Strategy Optimizer API
FastAPI application with security, monitoring, and operational guarantees.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest
from prometheus_client import CONTENT_TYPE_LATEST

# Import security components
import sys

sys.path.insert(0, "/app")

from src.common.security.iam_simulator import iam_simulator, Token, User, Permission
from src.common.security.https_middleware import (
    HTTPSRedirectMiddleware,
    SecurityHeadersMiddleware,
    RequestValidationMiddleware,
    RateLimitMiddleware,
    CORSMiddleware,
    get_current_user,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter(
    "api_requests_total", "Total API requests", ["method", "endpoint", "status"]
)
REQUEST_DURATION = Histogram(
    "api_request_duration_seconds", "API request duration", ["method", "endpoint"]
)
PREDICTION_COUNT = Counter("api_predictions_total", "Total predictions made", ["model"])

# Initialize FastAPI
app = FastAPI(
    title="F1 Strategy Optimizer API",
    description="Real-time race strategy recommendations with <500ms P99 latency",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Get configuration from environment
ENABLE_HTTPS = os.getenv("ENABLE_HTTPS", "false").lower() == "true"
ENABLE_IAM = os.getenv("ENABLE_IAM", "true").lower() == "true"
ENV = os.getenv("ENV", "local")

# ML model state — loaded once at startup
_strategy_model = None
_models_loaded_from_gcs = False

# Add middleware
if ENABLE_HTTPS:
    app.add_middleware(HTTPSRedirectMiddleware, enabled=True)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestValidationMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080", "*"],
    allow_credentials=True,
)

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# Pydantic models
class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    timestamp: str
    version: str
    environment: str


class StrategyRequest(BaseModel):
    """Strategy recommendation request"""

    race_id: str
    driver_id: str
    current_lap: int
    current_compound: str
    fuel_level: float
    track_temp: float
    air_temp: float


class StrategyRecommendation(BaseModel):
    """Strategy recommendation response"""

    recommended_action: str
    pit_window_start: Optional[int] = None
    pit_window_end: Optional[int] = None
    target_compound: Optional[str] = None
    driving_mode: str
    brake_bias: float
    confidence: float
    model_source: str  # "ml_model" or "rule_based_fallback"


# Routes
@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint"""
    return {
        "service": "F1 Strategy Optimizer API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0",
        environment=ENV,
    )


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return JSONResponse(
        content=generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST
    )


@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login endpoint to get JWT token"""
    user = iam_simulator.authenticate_user(form_data.username, form_data.password)

    if not user:
        REQUEST_COUNT.labels(method="POST", endpoint="/token", status="401").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token = iam_simulator.create_access_token(
        data={"sub": user.username, "roles": [r.value for r in user.roles]},
        expires_delta=timedelta(minutes=30),
    )

    REQUEST_COUNT.labels(method="POST", endpoint="/token", status="200").inc()

    logger.info(f"User {user.username} logged in successfully")

    return Token(access_token=access_token, token_type="bearer")


@app.get("/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Get current user info"""
    REQUEST_COUNT.labels(method="GET", endpoint="/users/me", status="200").inc()

    return current_user


@app.post("/strategy/recommend", response_model=StrategyRecommendation)
async def recommend_strategy(
    request: StrategyRequest, current_user: User = Depends(get_current_user)
):
    """
    Get race strategy recommendation

    Requires: API_USER role or higher
    """
    # Check permission
    if not iam_simulator.check_permission(current_user, Permission.ML_MODEL_READ):
        REQUEST_COUNT.labels(
            method="POST", endpoint="/strategy/recommend", status="403"
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    # Track request
    import time

    start_time = time.time()

    try:
        if _strategy_model is not None:
            import numpy as np

            features = np.array(
                [
                    [
                        request.current_lap,
                        request.fuel_level,
                        request.track_temp,
                        request.air_temp,
                    ]
                ]
            )
            pred = _strategy_model.predict(features)[0]
            recommended_action = "PIT_SOON" if pred > 0.5 else "CONTINUE"
            recommendation = StrategyRecommendation(
                recommended_action=recommended_action,
                pit_window_start=(
                    request.current_lap + 1
                    if recommended_action == "PIT_SOON"
                    else None
                ),
                pit_window_end=(
                    request.current_lap + 5
                    if recommended_action == "PIT_SOON"
                    else None
                ),
                target_compound=(
                    "HARD" if request.current_compound == "MEDIUM" else "SOFT"
                ),
                driving_mode="BALANCED",
                brake_bias=52.5,
                confidence=float(abs(pred - 0.5) * 2),
                model_source="ml_model",
            )
        else:
            recommendation = StrategyRecommendation(
                recommended_action=(
                    "CONTINUE" if request.current_lap < 30 else "PIT_SOON"
                ),
                pit_window_start=30 if request.current_lap < 30 else None,
                pit_window_end=35 if request.current_lap < 30 else None,
                target_compound=(
                    "HARD" if request.current_compound == "MEDIUM" else "SOFT"
                ),
                driving_mode="BALANCED",
                brake_bias=52.5,
                confidence=0.87,
                model_source="rule_based_fallback",
            )

        # Track metrics
        duration = time.time() - start_time
        REQUEST_DURATION.labels(method="POST", endpoint="/strategy/recommend").observe(
            duration
        )

        REQUEST_COUNT.labels(
            method="POST", endpoint="/strategy/recommend", status="200"
        ).inc()

        PREDICTION_COUNT.labels(model="strategy_v1").inc()

        logger.info(
            f"Strategy recommendation for {request.driver_id} at lap {request.current_lap}: "
            f"{recommendation.recommended_action} (latency: {duration*1000:.2f}ms)"
        )

        return recommendation

    except Exception as e:
        REQUEST_COUNT.labels(
            method="POST", endpoint="/strategy/recommend", status="500"
        ).inc()
        logger.error(f"Strategy recommendation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error generating recommendation",
        )


@app.get("/data/drivers", response_model=List[Dict])
async def get_drivers(
    current_user: User = Depends(get_current_user), year: Optional[int] = 2024
):
    """
    Get driver list

    Requires: DATA_READ permission
    """
    if not iam_simulator.check_permission(current_user, Permission.DATA_READ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    drivers = [
        {
            "driver_id": "max_verstappen",
            "name": "Max Verstappen",
            "nationality": "Dutch",
        },
        {
            "driver_id": "lewis_hamilton",
            "name": "Lewis Hamilton",
            "nationality": "British",
        },
    ]

    REQUEST_COUNT.labels(method="GET", endpoint="/data/drivers", status="200").inc()

    return drivers


@app.get("/models/status")
async def get_models_status(current_user: User = Depends(get_current_user)):
    """
    Get ML models status

    Requires: ML_MODEL_READ permission
    """
    if not iam_simulator.check_permission(current_user, Permission.ML_MODEL_READ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    # Placeholder - would query model registry
    models = [
        {
            "name": "tire_degradation",
            "version": "1.2.0",
            "status": "active",
            "accuracy": 0.92,
            "last_updated": "2024-01-15T10:30:00Z",
        },
        {
            "name": "fuel_consumption",
            "version": "1.1.0",
            "status": "active",
            "accuracy": 0.89,
            "last_updated": "2024-01-10T14:20:00Z",
        },
    ]

    REQUEST_COUNT.labels(method="GET", endpoint="/models/status", status="200").inc()

    return {"models": models}


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions"""
    REQUEST_COUNT.labels(
        method=request.method, endpoint=request.url.path, status=exc.status_code
    ).inc()

    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions"""
    REQUEST_COUNT.labels(
        method=request.method, endpoint=request.url.path, status="500"
    ).inc()

    logger.error(f"Unhandled exception: {exc}")

    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize on startup — load ML models from GCS if available."""
    global _strategy_model, _models_loaded_from_gcs
    logger.info(f"F1 Strategy Optimizer API starting in {ENV} environment")
    logger.info(f"HTTPS enabled: {ENABLE_HTTPS}")
    logger.info(f"IAM enabled: {ENABLE_IAM}")

    try:
        from google.cloud import storage
        import io
        import joblib

        gcs_client = storage.Client()
        bucket = gcs_client.bucket("f1optimizer-models")
        blob = bucket.blob("strategy_predictor/latest/model.pkl")
        if blob.exists():
            buf = io.BytesIO()
            blob.download_to_file(buf)
            buf.seek(0)
            _strategy_model = joblib.load(buf)
            _models_loaded_from_gcs = True
            logger.info("ML model loaded from GCS: strategy_predictor/latest/model.pkl")
        else:
            logger.warning(
                "No ML model found at strategy_predictor/latest/model.pkl — using rule-based fallback"
            )
    except Exception as e:
        logger.warning("Model load failed, using rule-based fallback: %s", e)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
