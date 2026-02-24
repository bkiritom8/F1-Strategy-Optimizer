"""
Pytest configuration and fixtures for F1 Strategy Optimizer tests
"""

import pytest
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def test_data_dir():
    """Test data directory fixture"""
    return Path(__file__).parent / "data"


@pytest.fixture
def sample_race_data():
    """Sample race data for testing"""
    return {
        "race_id": 1,
        "year": 2024,
        "round": 1,
        "circuit_id": "bahrain",
        "name": "Bahrain Grand Prix",
        "date": "2024-03-02",
        "time": "15:00:00",
        "url": "http://example.com",
    }


@pytest.fixture
def sample_driver_data():
    """Sample driver data for testing"""
    return {
        "driver_id": "max_verstappen",
        "driver_number": 1,
        "code": "VER",
        "givenName": "Max",
        "familyName": "Verstappen",
        "dateOfBirth": "1997-09-30",
        "nationality": "Dutch",
        "url": "http://example.com",
    }


@pytest.fixture
def mock_pubsub_client():
    """Mock Pub/Sub client for testing"""
    from unittest.mock import MagicMock

    client = MagicMock()
    return client


@pytest.fixture
def iam_simulator():
    """IAM simulator instance for testing"""
    from src.common.security.iam_simulator import IAMSimulator

    return IAMSimulator()


@pytest.fixture
def test_user(iam_simulator):
    """Test user with data viewer role"""
    from src.common.security.iam_simulator import User, Role

    return User(
        username="test_user",
        email="test@example.com",
        full_name="Test User",
        roles=[Role.DATA_VIEWER],
    )


@pytest.fixture
def admin_user(iam_simulator):
    """Test admin user"""
    from src.common.security.iam_simulator import User, Role

    return User(
        username="admin",
        email="admin@example.com",
        full_name="Admin User",
        roles=[Role.ADMIN],
    )


@pytest.fixture
def auth_token(iam_simulator, test_user):
    """Valid authentication token"""
    return iam_simulator.create_access_token(
        data={"sub": test_user.username, "roles": [r.value for r in test_user.roles]}
    )


# Pytest configuration
def pytest_configure(config):
    """Configure pytest"""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires Docker)"
    )
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "unit: mark test as unit test")
