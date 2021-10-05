#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from dataclasses import dataclass
import json
from os import environ
from typing import TypedDict, List

import requests


def get_graphql_endpoint() -> str:
    return environ.get("GRAPHQL_ENDPOINT") or "http://graphql:3001/graphql"


def get_api_key() -> str:
    return environ.get("API_SECRET") or ""


@dataclass
class MentorThumbnailUpdateRequest:
    mentor: str
    thumbnail: str


class GQLQueryBody(TypedDict):
    query: str


@dataclass
class Media:
    type: str
    tag: str
    url: str


@dataclass
class TaskInfo:
    task_id: str
    status: str


@dataclass
class UploadTaskRequest:
    mentor: str
    question: str
    task_list: List[TaskInfo]
    transcript: str = None
    media: List[Media] = None


def thumbnail_update_gql(req: MentorThumbnailUpdateRequest) -> GQLQueryBody:
    return {
        "query": """mutation MentorThumbnailUpdate($mentorId: ID!, $thumbnail: String!) {
            api {
                mentorThumbnailUpdate(mentorId: $mentorId, thumbnail: $thumbnail)
            }
        }""",
        "variables": {"mentorId": req.mentor, "thumbnail": req.thumbnail},
    }


def upload_task_req_gql(req: UploadTaskRequest) -> GQLQueryBody:
    status = {}
    status["taskList"] = req.task_list
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


@dataclass
class UpdateTaskStatusRequest:
    mentor: str
    question: str
    task_id: str
    new_status: str


def upload_task_status_req_gql(req: UpdateTaskStatusRequest) -> GQLQueryBody:
    return {
        "query": """mutation UpdateUploadTaskStatus($mentorId: ID!, $questionId: ID!, $taskId: String!, $newStatus: String!) {
            api {
                uploadTaskStatusUpdate(mentorId: $mentorId, questionId: $questionId, taskId: $taskId, newStatus: $newStatus)
            }
        }""",
        "variables": {
            "mentorId": req.mentor,
            "questionId": req.question,
            "taskId": req.task_id,
            "newStatus": req.new_status,
        },
    }


def upload_task_status_update(req: UpdateTaskStatusRequest) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = upload_task_status_req_gql(req)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))


def upload_task_update(req: UploadTaskRequest) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = upload_task_req_gql(req)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))


def mentor_thumbnail_update(req: MentorThumbnailUpdateRequest) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = thumbnail_update_gql(req)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))
