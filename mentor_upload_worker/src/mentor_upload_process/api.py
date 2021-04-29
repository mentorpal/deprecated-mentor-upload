#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from dataclasses import dataclass
import json
from os import environ
from typing import TypedDict

import requests


def get_graphql_endpoint() -> str:
    return environ.get("GRAPHQL_ENDPOINT") or "http://graphql/graphql"


@dataclass
class AnswerUpdateRequest:
    mentor: str
    question: str
    transcript: str


@dataclass
class AnswerUpdateResponse:
    mentor: str
    question: str
    transcript: str


class GQLQueryBody(TypedDict):
    query: str


def answer_update_gql(req: AnswerUpdateRequest) -> GQLQueryBody:
    return {
        "query": f"""mutation {{
            uploadAnswer(
                mentorId: {req.mentor},
                questionId: {req.question},
                answer: {{ transcript: {req.transcript} }}
            }})
        }}"""
    }


def update_answer(req: AnswerUpdateRequest) -> None:
    res = requests.post(get_graphql_endpoint(), json=answer_update_gql(req))
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))
