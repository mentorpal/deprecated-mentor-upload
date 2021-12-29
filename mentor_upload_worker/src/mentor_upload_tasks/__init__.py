import logging
from logging.config import dictConfig
import os
import json


class JSONFormatter(logging.Formatter):
    RECORD_ATTRS = [
        "name",
        "levelname",
        "filename",
        "module",
        "path",
        "lineno",
        "funcName",
    ]

    def to_payload(self, record):
        payload = {
            attr: getattr(record, attr)
            for attr in self.RECORD_ATTRS
            if hasattr(record, attr)
        }
        # make sure log messages are consistent across services:
        payload["level"] = payload["levelname"].lower()
        del payload["levelname"]
        payload["logger"] = payload["name"]
        del payload["name"]
        payload["message"] = record.getMessage()
        return payload

    def format(self, record):
        payload = self.to_payload(record)
        return json.dumps(payload)


log_level = os.environ.get("LOG_LEVEL_UPLOAD_API", "INFO")
log_format = os.environ.get("LOG_FORMAT_UPLOAD_API", "json")

dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {"()": "mentor_upload_tasks.JSONFormatter"},
            "simple": {"format": "%(levelname)s %(message)s"},
            "verbose": {
                "format": "[%(asctime)s] - %(name)s: %(levelname)s - %(message)s [in %(pathname)s:%(lineno)d]"
            },
            "json": {"()": "mentor_upload_tasks.JSONFormatter"},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": log_format,
                "level": log_level,
                "stream": "ext://sys.stdout",
            }
        },
        "root": {"level": log_level, "handlers": ["console"]},
    }
)
