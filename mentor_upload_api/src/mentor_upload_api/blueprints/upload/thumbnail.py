#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from datetime import datetime
from os import environ
from urllib.parse import urljoin

import boto3
from boto3_type_annotations.s3 import Client as S3Client
from flask import Blueprint, jsonify, request

from mentor_upload_api.api import (
    MentorThumbnailUpdateRequest,
    mentor_thumbnail_update,
)

from mentor_upload_api.helpers import validate_payload_json_decorator

thumbnail_blueprint = Blueprint("thumbnail", __name__)


def _require_env(n: str) -> str:
    env_val = environ.get(n, "")
    if not env_val:
        raise EnvironmentError(f"missing required env var {n}")
    return env_val


def _create_s3_client() -> S3Client:
    return boto3.client(
        "s3",
        region_name=_require_env("STATIC_AWS_REGION"),
        aws_access_key_id=_require_env("STATIC_AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=_require_env("STATIC_AWS_SECRET_ACCESS_KEY"),
    )


thumbnail_upload_json_schema = {
    "type": "object",
    "properties": {
        # Mongoose ObjectID == 24 characters
        "mentor": {"type": "string", "maxLength": 24, "minLength": 24},
    },
    "required": ["mentor"],
}


# TODO: probably want to force the size and quality of this image
# ...make sure it's a PNG, etc. When we do all of that,
# will probably move the processing out of the HTTP request handler
# and to an async worker, like video upload
@thumbnail_blueprint.route("/", methods=["POST"])
@thumbnail_blueprint.route("", methods=["POST"])
@validate_payload_json_decorator(json_schema=thumbnail_upload_json_schema)
def upload(body):
    mentor = body.get("mentor")
    upload_file = request.files["thumbnail"]
    thumbnail_path = f"mentor/thumbnails/{mentor}/{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}/thumbnail.png"
    s3 = _create_s3_client()
    s3_bucket = _require_env("STATIC_AWS_S3_BUCKET")
    s3.upload_fileobj(
        upload_file,
        s3_bucket,
        thumbnail_path,
        ExtraArgs={"ContentType": "image/png"},
    )
    mentor_thumbnail_update(
        MentorThumbnailUpdateRequest(mentor=mentor, thumbnail=thumbnail_path)
    )
    static_url_base = environ.get("STATIC_URL_BASE", "")
    return jsonify({"data": {"thumbnail": urljoin(static_url_base, thumbnail_path)}})
