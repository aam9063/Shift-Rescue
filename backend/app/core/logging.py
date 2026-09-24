"""structlog JSON logging configuration (spec §9.1)."""

import logging

import structlog


def configure_logging(service_name: str) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
    structlog.get_logger("startup").info("logging configured", service_name=service_name)
