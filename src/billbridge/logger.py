import logging
import os
import sys

import structlog

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt='iso'),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, os.environ.get('LOG_LEVEL', 'INFO').upper(), logging.INFO)
    ),
    logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
)


def get_logger():
    return structlog.get_logger()
