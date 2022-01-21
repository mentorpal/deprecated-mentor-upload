#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from functools import wraps
from flask import request, abort
from os import environ
from typing import TypedDict
from mentor_upload_api.helpers import exec_graphql_with_json_validation
import logging

log = logging.getLogger("authorization")


class GQLQueryBody(TypedDict):
    query: str


def get_graphql_endpoint() -> str:
    return environ.get("GRAPHQL_ENDPOINT") or "http://graphql:3001/graphql"


def get_authorization_gql() -> GQLQueryBody:
    return {
        "query": """query {
            me {
              canManageContent
            }
          }"""
    }


authorize_gql_json_schema = {
    "type": "object",
    "properties": {
        "data": {
            "type": "object",
            "properties": {
                "me": {
                    "type": "object",
                    "properties": {"canManageContent": {"type": "boolean"}},
                    "required": ["canManageContent"],
                }
            },
            "required": ["me"],
        },
    },
    "required": ["data"],
}


def authorize_to_manage_content(f):
    @wraps(f)
    def authorized_endpoint(*args, **kws):
        bearer_token = request.headers.get("Authorization", "")
        token_authentication = bool(bearer_token.split(" ")[0].lower() == "bearer")
        if not token_authentication and not request.cookies.get("refreshToken", ""):
            log.debug("no authentication token provided")
            abort(401)
        headers = {"Authorization": bearer_token} if token_authentication else {}
        cookies = request.cookies if not token_authentication else {}
        gql_query = get_authorization_gql()
        res_json = exec_graphql_with_json_validation(
            gql_query, authorize_gql_json_schema, cookies=cookies, headers=headers
        )

        is_authorized = res_json["data"]["me"]["canManageContent"]
        if not is_authorized:
            abort(403)
        return f(*args, **kws)

    return authorized_endpoint
