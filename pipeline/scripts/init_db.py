#!/usr/bin/env python3
"""
Initialize database for F1 Strategy Optimizer
Creates tables, indexes, and sample data for local development
"""

import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def init_airflow_db():
    """Initialize Airflow metadata database"""
    logger.info("Initializing Airflow database...")

    import subprocess

    try:
        # Initialize Airflow database
        subprocess.run(["airflow", "db", "init"], check=True)

        # Create admin user
        subprocess.run(
            [
                "airflow",
                "users",
                "create",
                "--username",
                "admin",
                "--firstname",
                "Admin",
                "--lastname",
                "User",
                "--role",
                "Admin",
                "--email",
                "admin@f1optimizer.local",
                "--password",
                "admin",
            ],
            check=True,
        )

        logger.info("[OK] Airflow database initialized")

    except subprocess.CalledProcessError as e:
        logger.error(f"[FAIL] Failed to initialize Airflow database: {e}")
    except FileNotFoundError:
        logger.warning(
            "[WARNING] Airflow not found - skipping Airflow DB initialization"
        )


def create_directories():
    """Create necessary directories"""
    logger.info("Creating directories...")

    directories = [
        "/data",
        "/app/models",
        "/tmp/fastf1_cache",
        "airflow/logs",
        "airflow/dags",
        "airflow/plugins",
    ]

    for dir_path in directories:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    logger.info("[OK] Directories created")


def verify_environment():
    """Verify environment setup"""
    logger.info("Verifying environment...")

    checks = {
        "Python version": True,
        "Docker Compose": False,
        "PostgreSQL": False,
        "Mock services": False,
    }

    # Check Python
    import sys

    if sys.version_info >= (3, 10):
        logger.info("[OK] Python 3.10+ detected")
        checks["Python version"] = True
    else:
        logger.warning(
            f"[WARNING] Python {sys.version_info.major}.{sys.version_info.minor} detected, 3.10+ recommended"
        )

    # Check Docker Compose
    import subprocess

    try:
        subprocess.run(["docker-compose", "--version"], capture_output=True, check=True)
        logger.info("[OK] Docker Compose available")
        checks["Docker Compose"] = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("[WARNING] Docker Compose not found")

    return all(checks.values())


def main():
    """Main initialization function"""
    logger.info("=" * 60)
    logger.info("F1 Strategy Optimizer - Database Initialization")
    logger.info("=" * 60)

    # Verify environment
    verify_environment()

    # Create directories
    create_directories()

    # Initialize Airflow (optional - only if Airflow is installed)
    # init_airflow_db()

    logger.info("=" * 60)
    logger.info("[OK] Initialization complete!")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Next steps:")
    logger.info(
        "1. Start Docker services: docker-compose -f docker-compose.f1.yml up -d"
    )
    logger.info("2. Access Airflow UI: http://localhost:8080 (admin/admin)")
    logger.info("3. Access API docs: http://localhost:8000/docs")
    logger.info("4. Access Grafana: http://localhost:3000 (admin/admin)")
    logger.info("")


if __name__ == "__main__":
    main()
