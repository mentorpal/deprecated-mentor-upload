#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from functools import wraps
from flask import request, abort
import requests
from os import environ
from typing import TypedDict
import json


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


def authorize_to_manage_content(f):
    @wraps(f)
    def authorized_endpoint(*args, **kws):
        bearer_token = request.headers.get("Authorization", "")
        token_authentication = bool(bearer_token.split(" ")[0].lower() == "bearer")
        headers = {"Authorization": bearer_token} if token_authentication else {}
        cookies = request.cookies if not token_authentication else {}
        body = get_authorization_gql()
        res = requests.post(
            get_graphql_endpoint(), json=body, cookies=cookies, headers=headers
        )
        res.raise_for_status()
        tdjson = res.json()
        if "errors" in tdjson:
            raise Exception(json.dumps(tdjson.get("errors")))
        if (
            "data" not in tdjson
            or "me" not in tdjson["data"]
            or "canManageContent" not in tdjson["data"]["me"]
        ):
            raise Exception(f"query: {body} did not return proper data format")
        is_authorized = tdjson["data"]["me"]["canManageContent"]
        if not is_authorized:
            abort(403)
        return f(*args, **kws)

    return authorized_endpoint
