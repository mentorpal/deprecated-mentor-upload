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
                answerUpdate(input: {{
                    mentor: {req.mentor},
                    question: {req.question},
                    transcript: {req.transcript}
                }}) {{
                }}
            }}"""
    }


def update_answer(req: AnswerUpdateRequest) -> None:
    res = requests.post(get_graphql_endpoint(), json=answer_update_gql(req))
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))
