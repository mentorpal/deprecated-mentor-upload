#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from dataclasses import dataclass
import json
from os import environ
from typing import List, TypedDict

import requests


def get_graphql_endpoint() -> str:
    return environ.get("GRAPHQL_ENDPOINT") or "http://graphql/graphql"


def get_api_key() -> str:
    return environ.get("API_SECRET") or ""


@dataclass
class Media:
    type: str
    tag: str
    url: str
    needsTransfer: bool  # noqa: N815


@dataclass
class AnswerUpdateRequest:
    mentor: str
    question: str
    transcript: str
    media: List[Media]


@dataclass
class AnswerUpdateResponse:
    mentor: str
    question: str
    transcript: str
    media: List[Media]


@dataclass
class StatusUpdateRequest:
    mentor: str
    question: str
    task_id: str
    status: str = None
    upload_flag: str = None
    transcribing_flag: str = None
    transcoding_flag: str = None
    finalization_flag: str = None
    transcript: str = None
    media: List[Media] = None


@dataclass
class StatusUpdateResponse:
    mentor: str
    question: str
    task_id: str
    status: str = None
    upload_flag: str = None
    transcribing_flag: str = None
    transcoding_flag: str = None
    finalization_flag: str = None
    transcript: str = None
    media: List[Media] = None


@dataclass
class MediaUpdateRequest:
    mentor: str
    question: str
    media: Media


class GQLQueryBody(TypedDict):
    query: str


def answer_query_gql(mentor: str, question: str) -> GQLQueryBody:
    return {
        "query": """query Answer($mentor: ID!, $question: ID!) {
            answer(mentor: $mentor, question: $question) {
                _id
                transcript
                hasUntransferredMedia
                media {
                    type
                    tag
                    url
                    needsTransfer
                }
            }
        }""",
        "variables": {
            "mentor": mentor,
            "question": question,
        },
    }


def answer_update_gql(req: AnswerUpdateRequest) -> GQLQueryBody:
    return {
        "query": """mutation UploadAnswer($mentorId: ID!, $questionId: ID!, $answer: UploadAnswerType!) {
            api {
                uploadAnswer(mentorId: $mentorId, questionId: $questionId, answer: $answer)
            }
        }""",
        "variables": {
            "mentorId": req.mentor,
            "questionId": req.question,
            "answer": {"transcript": req.transcript, "media": req.media},
        },
    }


def status_update_gql(req: StatusUpdateRequest) -> GQLQueryBody:
    status = {}
    status["taskId"] = req.task_id
    if req.status:
        status["uploadStatus"] = req.status
    if req.upload_flag:
        status["uploadFlag"] = req.upload_flag
    if req.transcribing_flag:
        status["transcribingFlag"] = req.transcribing_flag
    if req.transcoding_flag:
        status["transcodingFlag"] = req.transcoding_flag
    if req.finalization_flag:
        status["finalizationFlag"] = req.finalization_flag
    if req.transcript:
        status["transcript"] = req.transcript
    if req.media:
        status["media"] = req.media

    return {
        "query": """mutation UploadStatus($mentorId: ID!, $questionId: ID!, $status: UploadTaskInputType!) {
            api {
                uploadTaskUpdate(mentorId: $mentorId, questionId: $questionId, status: $status)
            }
        }""",
        "variables": {
            "mentorId": req.mentor,
            "questionId": req.question,
            "status": status,
        },
    }


def fetch_question_name_gql(question_id: str) -> GQLQueryBody:
    return {
        "query": """query Question($id: ID!) {
            question(id: $id){
                name
            }
        }""",
        "variables": {
            "id": question_id,
        },
    }


def media_update_gql(req: MediaUpdateRequest) -> GQLQueryBody:
    return {
        "query": """mutation MediaUpdate($mentorId: ID!, $questionId: ID!, $media: AnswerMediaInputType!) {
            api {
                mediaUpdate(mentorId: $mentorId, questionId: $questionId, media: $media)
            }
        }""",
        "variables": {
            "mentorId": req.mentor,
            "questionId": req.question,
            "media": req.media,
        },
    }


def fetch_answer(mentor: str, question: str) -> dict:
    body = answer_query_gql(mentor, question)
    res = requests.post(get_graphql_endpoint(), json=body)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))
    data = tdjson["data"]["answer"]
    return data


def update_answer(req: AnswerUpdateRequest) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = answer_update_gql(req)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))


def update_status(req: StatusUpdateRequest) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = status_update_gql(req)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))


def fetch_question_name(question_id: str) -> str:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = fetch_question_name_gql(question_id)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))
    if (
        "data" not in tdjson
        or "question" not in tdjson["data"]
        or "name" not in tdjson["data"]["question"]
    ):
        raise Exception(f"query: {body} did not return proper data format")
    return tdjson["data"]["question"]["name"]


def update_media(req: MediaUpdateRequest) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = media_update_gql(req)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))
