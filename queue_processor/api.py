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
    has_edited_transcript: bool = None


@dataclass
class AnswerUpdateResponse:
    mentor: str
    question: str
    transcript: str
    media: List[Media]


@dataclass
class TaskInfo:
    flag: str
    id: str


@dataclass
class UpdateTaskStatusRequest:
    mentor: str
    question: str
    task_id: str
    new_status: str
    transcript: str = None
    media: Media = None


class GQLQueryBody(TypedDict):
    query: str


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


def fetch_task_gql(mentor_id: str, question_id) -> GQLQueryBody:
    return {
        "query": """query UploadTask($mentorId: ID!, $questionId: ID!) {
            uploadTask(mentorId: $mentorId, questionId: $questionId){
                taskList {
                    task_id
                    status
                }
            }
        }""",
        "variables": {
            "mentorId": mentor_id,
            "questionId": question_id,
        },
    }


def fetch_task(mentor_id: str, question_id) -> dict:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = fetch_task_gql(mentor_id, question_id)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))
    return tdjson["data"]["uploadTask"]


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


def upload_task_status_req_gql(req: UpdateTaskStatusRequest) -> GQLQueryBody:
    variables = {}
    variables["mentorId"] = req.mentor
    variables["questionId"] = req.question
    variables["taskId"] = req.task_id
    variables["newStatus"] = req.new_status
    if req.transcript:
        variables["transcript"] = req.transcript
    if req.media:
        variables["media"] = req.media
    return {
        "query": """mutation UpdateUploadTaskStatus($mentorId: ID!, $questionId: ID!, $taskId: String!, $newStatus: String!, $transcript: String, $media: [AnswerMediaInputType]) {
            api {
                uploadTaskStatusUpdate(mentorId: $mentorId, questionId: $questionId, taskId: $taskId, newStatus: $newStatus, transcript: $transcript, media: $media)
            }
        }""",
        "variables": variables,
    }


def upload_answer_and_task_status_req_gql(
    answer_req: AnswerUpdateRequest, status_req: UpdateTaskStatusRequest
) -> GQLQueryBody:
    variables = {}
    variables["mentorId"] = answer_req.mentor
    variables["questionId"] = answer_req.question

    variables["answer"] = {
        "transcript": answer_req.transcript,
        "media": answer_req.media,
    }
    if answer_req.has_edited_transcript is not None:
        variables["answer"]["hasEditedTranscript"] = answer_req.has_edited_transcript

    variables["taskId"] = status_req.task_id
    variables["newStatus"] = status_req.new_status
    if status_req.transcript:
        variables["transcript"] = status_req.transcript
    if status_req.media:
        variables["media"] = status_req.media
    return {
        "query": """mutation UpdateUploadAnswerAndTaskStatus($mentorId: ID!, $questionId: ID!, $answer: UploadAnswerType!, $taskId: String!, $newStatus: String!, $transcript: String, $media: [AnswerMediaInputType]) {
            api {
                uploadAnswer(mentorId: $mentorId, questionId: $questionId, answer: $answer)
                uploadTaskStatusUpdate(mentorId: $mentorId, questionId: $questionId, taskId: $taskId, newStatus: $newStatus, transcript: $transcript, media: $media)
            }
        }""",
        "variables": variables,
    }


def upload_answer_and_task_status_update(
    answer_req: AnswerUpdateRequest, status_req: UpdateTaskStatusRequest
) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = upload_answer_and_task_status_req_gql(answer_req, status_req)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))


def upload_task_status_update(req: UpdateTaskStatusRequest) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = upload_task_status_req_gql(req)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))
