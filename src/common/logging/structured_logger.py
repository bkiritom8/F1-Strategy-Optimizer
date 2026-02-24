"""
Structured logging utility for F1 Strategy Optimizer.
Provides JSON-formatted logs with context and correlation IDs.
"""

import logging
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pythonjsonlogger import jsonlogger


class StructuredLogger:
    """Structured JSON logger with correlation tracking"""

    def __init__(
        self, name: str, level: str = "INFO", correlation_id: Optional[str] = None
    ):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        self.correlation_id = correlation_id or str(uuid.uuid4())

        # Remove existing handlers
        self.logger.handlers = []

        # Create JSON formatter
        formatter = jsonlogger.JsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(correlation_id)s %(message)s"
        )

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def _add_context(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Add standard context to log entries"""
        context = {
            "timestamp": datetime.utcnow().isoformat(),
            "correlation_id": self.correlation_id,
        }
        if extra:
            context.update(extra)
        return context

    def info(self, message: str, **kwargs):
        """Log info message"""
        self.logger.info(message, extra=self._add_context(kwargs))

    def warning(self, message: str, **kwargs):
        """Log warning message"""
        self.logger.warning(message, extra=self._add_context(kwargs))

    def error(self, message: str, **kwargs):
        """Log error message"""
        self.logger.error(message, extra=self._add_context(kwargs))

    def debug(self, message: str, **kwargs):
        """Log debug message"""
        self.logger.debug(message, extra=self._add_context(kwargs))

    def critical(self, message: str, **kwargs):
        """Log critical message"""
        self.logger.critical(message, extra=self._add_context(kwargs))
