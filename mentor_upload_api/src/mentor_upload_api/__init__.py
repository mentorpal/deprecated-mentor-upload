#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env.

import os
import logging
import json
from logging.config import dictConfig  # NOQA E402
from flask import Flask, request, g, has_request_context  # NOQA E402
from flask_cors import CORS  # NOQA E402

class JSONFormatter(logging.Formatter):
    RECORD_ATTRS = [
        'request_id', 'name', 'levelname', 'filename', 'module',
        'lineno', 'funcName', 'thread', 'threadName', 'process', 
        'endpoint', 'method', 'url', 'remote_addr', 'headers'
    ]
    def to_payload(self, record):
        payload = {
            attr: getattr(record, attr) for attr in self.RECORD_ATTRS if hasattr(record, attr)
        }
        # make sure log messages are consistent across services:
        payload['level'] = payload['levelname'].lower()
        del payload['levelname']
        payload['logger'] = payload['name']
        del payload['name']
        payload['message'] = record.getMessage()
        return payload

    def to_json(self, payload):
        # do not assume there's a Flask request context here so must use FLASK_ENV env var not app.debug
        indent = 2 if os.environ.get('FLASK_ENV', '') == 'development' else None
        return json.dumps(payload, indent=indent)

    def format(self, record):
        payload = self.to_payload(record)
        return self.to_json(payload)
        

class RequestJSONFormatter(JSONFormatter):
    def format(self, record):
        if has_request_context():
            record.request_id = g.request_id if hasattr(g, 'request_id') else '-'
            record.endpoint = request.endpoint
            record.method = request.method
            record.url = request.url
            # make sure to redact sensitive info: cookies, auth...
            record.headers = {k: v for k, v in request.headers.items() if 'auth' not in k.lower()}
            record.remote_addr = request.remote_addr
        
        return super().format(record)

class RequestFilter(logging.Filter):

    # def __init__(self, methods=None):
    #     self.methods = methods or []
    #     super().__init__()

    def filter(self, record):
        # TODO redact sensitive data
        return True
        # if hasattr(record, 'method'):
        #     if record.method in self.methods:
        #         return True
        # else:
        #     return True


def create_app():
    log_level = os.environ.get('LOG_LEVEL_UPLOAD_API', 'INFO')
    log_format = os.environ.get('LOG_FORMAT_UPLOAD_API', 'json')

    dictConfig(
        {
            "version": 1,
            "formatters": {
                "default": {
                    '()': 'mentor_upload_api.JSONFormatter'
                },
                'simple': {
                    'format': '%(levelname)s %(message)s'
                },
                'verbose': {
                    'format': '[%(asctime)s] - %(name)s: %(levelname)s - %(message)s [in %(pathname)s:%(lineno)d]'
                },
                'json': {
                    '()': 'mentor_upload_api.JSONFormatter'
                },
                'request_json': {
                    '()': 'mentor_upload_api.RequestJSONFormatter'
                }
            },
            'filters': {
                'requests': {
                    '()': 'mentor_upload_api.RequestFilter'
                }
            },
            "handlers": {
                'console': {
                    'class': 'logging.StreamHandler',
                    'formatter': log_format,
                    'level': log_level,
                    'stream': 'ext://sys.stdout'
                },
                "wsgi": {
                    "class": "logging.StreamHandler",
                    "formatter": log_format,
                    "stream": "ext://flask.logging.wsgi_errors_stream",
                },
                "request": {
                    "class": "logging.StreamHandler",
                    "formatter": 'request_json',
                    'filters': ['requests'],
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {"level": log_level, "handlers": ["wsgi"]},
            # stop propagation otherwise root logger will also run
            "loggers": {"request":{"level": log_level, "propagate": 0, "handlers": ["request"]}},
        }
    )
    app = Flask(__name__)
    CORS(app)
    from mentor_upload_api.blueprints.ping import ping_blueprint

    app.register_blueprint(ping_blueprint, url_prefix="/upload/ping")
    from mentor_upload_api.blueprints.upload.answer import answer_blueprint

    app.register_blueprint(answer_blueprint, url_prefix="/upload/answer")
    from mentor_upload_api.blueprints.upload.transfer import transfer_blueprint

    app.register_blueprint(transfer_blueprint, url_prefix="/upload/transfer")
    from mentor_upload_api.blueprints.upload.thumbnail import thumbnail_blueprint

    app.register_blueprint(thumbnail_blueprint, url_prefix="/upload/thumbnail")
    return app
