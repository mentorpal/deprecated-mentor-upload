#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from functools import wraps
from xml.dom import ValidationErr
from flask import request, abort
from os import environ
import logging
import jwt
import json
from json import JSONDecodeError

from mentor_upload_api.helpers import validate_json

log = logging.getLogger()


jwt_payload_schema = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "maxLength": 60, "minLength": 5},
        "role": {"type": "string"},
        "mentorIds": {
            "type": "array",
            "items": {"type": "string", "maxLength": 60, "minLength": 5},
        },
    },
    "required": ["id", "role", "mentorIds"],
}


def parse_payload_from_auth_header_jwt(request):
    bearer_token = request.headers.get("Authorization", "")
    token_authentication = bearer_token.lower().startswith("bearer")
    token_split = bearer_token.split(" ")
    if not token_authentication or len(token_split) == 1:
        log.debug("no authentication token provided")
        abort(401)
    token = token_split[1]
    jwt_secret = environ.get("JWT_SECRET")
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        abort(401, "access token has expired")

    try:
        validate_json(payload, jwt_payload_schema)
    except ValidationErr as err:
        raise err
    return payload


def authorize_to_manage_content(f):
    """Confirms the issuer is an admin or content manager via JWT"""

    @wraps(f)
    def authorized_endpoint(*args, **kws):
        payload = parse_payload_from_auth_header_jwt(request)
        is_authorized = (
            payload["role"] == "CONTENT_MANAGER" or payload["role"] == "ADMIN"
        )
        if not is_authorized:
            abort(401)
        return f(*args, **kws)

    return authorized_endpoint


authorize_edit_mentor_payload_schema = {
    "type": "object",
    "properties": {"mentor": {"type": "string", "minLength": 5, "maxLength": 60}},
    "required": ["mentor"],
}


def authorize_to_edit_mentor(f):
    """Crosschecks JWTs mentorId with the mentor being edited, or validates that the editor is an admin/content manager"""

    @wraps(f)
    def authorized_endpoint(*args, **kws):
        # Get the mentor being edited from the request body
        body = request.form.get("body", {})
        if body:
            try:
                json_body = json.loads(body)
            except JSONDecodeError as err:
                raise err
        else:
            json_body = request.json
        if not json_body:
            raise Exception("missing required param body")

        validate_json(json_body, authorize_edit_mentor_payload_schema)
        mentor_being_edited = json_body["mentor"]

        jwt_payload = parse_payload_from_auth_header_jwt(request)

        # Check if the requester is either editing their own mentor, or has permissions to edit other mentors
        requester_mentorids = jwt_payload["mentorIds"]
        requester_can_manage_content = (
            jwt_payload["role"] == "CONTENT_MANAGER" or jwt_payload["role"] == "ADMIN"
        )

        if (
            mentor_being_edited not in requester_mentorids
            and not requester_can_manage_content
        ):
            abort(401)
        return f(*args, **kws)

    return authorized_endpoint
