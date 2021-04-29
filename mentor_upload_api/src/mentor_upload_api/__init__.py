#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from logging.config import dictConfig

from flask import Flask
from flask_cors import CORS


def create_app():
    dictConfig(
        {
            "version": 1,
            "formatters": {
                "default": {
                    "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
                }
            },
            "handlers": {
                "wsgi": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://flask.logging.wsgi_errors_stream",
                    "formatter": "default",
                }
            },
            "root": {"level": "INFO", "handlers": ["wsgi"]},
        }
    )
    app = Flask(__name__)
    CORS(app)
    from mentor_upload_api.blueprints.ping import ping_blueprint

    app.register_blueprint(ping_blueprint, url_prefix="/upload/ping")
    from mentor_upload_api.blueprints.upload import upload_blueprint

    app.register_blueprint(upload_blueprint, url_prefix="/upload/answer")
    # from mentor_upload_api.blueprints.trim import trim_blueprint
    # app.register_blueprint(trim_blueprint, url_prefix="/upload/trim")
    return app
