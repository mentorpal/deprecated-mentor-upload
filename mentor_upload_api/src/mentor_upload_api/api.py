#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
import json
import logging
import requests
from dataclasses import dataclass
from os import environ
from typing import TypedDict, List

from mentor_upload_api.helpers import validate_json, exec_graphql_with_json_validation

log = logging.getLogger()


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
    task_name: str
    task_id: str
    status: str


@dataclass
class UploadTaskRequest:
    mentor: str
    question: str
    trim_upload_task: TaskInfo
    transcode_web_task: TaskInfo
    transcode_mobile_task: TaskInfo
    transcribe_task: TaskInfo
    transcript: str = None
    original_media: Media = None


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
    status["transcodeWebTask"] = req.transcode_web_task
    status["transcodeMobileTask"] = req.transcode_mobile_task
    status["trimUploadTask"] = req.trim_upload_task
    status["transcribeTask"] = req.transcribe_task
    if req.transcript:
        status["transcript"] = req.transcript
    if req.originalMedia:
        status["originalMedia"] = req.original_media

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


def upload_task_update(req: UploadTaskRequest) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = upload_task_req_gql(req)
    log.debug(body)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))


def mentor_thumbnail_update(req: MentorThumbnailUpdateRequest) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = thumbnail_update_gql(req)
    log.debug(body)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))


@dataclass
class FetchUploadTaskReq:
    mentor: str
    question: str


def fetch_upload_task_gql(req: FetchUploadTaskReq) -> GQLQueryBody:
    return {
        "query": """query UploadTask($mentorId: ID!, $questionId: ID!) {
            uploadTask(mentorId: $mentorId, questionId: $questionId){
                transcript
            }
            }""",
        "variables": {"mentorId": req.mentor, "questionId": req.question},
    }


fetch_upload_task_schema = {
    "type": "object",
    "properties": {
        "data": {
            "type": "object",
            "properties": {
                "uploadTask": {
                    "type": ["object", "null"],
                    "properties": {
                        "transcript": {
                            "type": "string",
                        }
                    },
                }
            },
            "required": ["uploadTask"],
        }
    },
    "required": ["data"],
}


def is_upload_in_progress(req: FetchUploadTaskReq) -> bool:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = fetch_upload_task_gql(req)
    log.debug(body)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    validate_json(tdjson, fetch_upload_task_schema)
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))
    return bool(tdjson["data"]["uploadTask"])


@dataclass
class AnswerUpdateRequest:
    mentor: str
    question: str
    transcript: str
    has_edited_transcript: bool = None


def upload_answer_and_task_req_gql(
    answer_req: AnswerUpdateRequest, task_req: UploadTaskRequest
) -> GQLQueryBody:
    variables = {}
    variables["mentorId"] = answer_req.mentor
    variables["questionId"] = answer_req.question

    variables["answer"] = {}
    if answer_req.transcript:
        variables["answer"]["transcript"] = answer_req.transcript
    if answer_req.has_edited_transcript is not None:
        variables["answer"]["hasEditedTranscript"] = answer_req.has_edited_transcript

    variables["status"] = {
        "transcodeWebTask": task_req.transcode_web_task,
        "transcodeMobileTask": task_req.transcode_mobile_task,
        "transcribeTask": task_req.transcribe_task,
        "trimUploadTask": task_req.trim_upload_task,
    }
    if task_req.transcript:
        variables["status"]["transcript"] = task_req.transcript
    return {
        "query": """mutation UpdateUploadAnswerAndTaskStatus($mentorId: ID!, $questionId: ID!, $answer: UploadAnswerType!, $status: UploadTaskInputType!) {
            api {
                uploadAnswer(mentorId: $mentorId, questionId: $questionId, answer: $answer)
                uploadTaskUpdate(mentorId: $mentorId, questionId: $questionId, status: $status)
            }
        }""",
        "variables": variables,
    }


def upload_answer_and_task_update(
    answer_req: AnswerUpdateRequest, task_req: UploadTaskRequest
) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = upload_answer_and_task_req_gql(answer_req, task_req)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))


def fetch_answer_transcript_and_media_gql(mentor: str, question: str) -> GQLQueryBody:
    return {
        "query": """query Answer($mentor: ID!, $question: ID!) {
            answer(mentor: $mentor, question: $question){
                transcript
                webMedia {
                    type
                    tag
                    url
                }
                mobileMedia {
                    type
                    tag
                    url
                }
                vttMedia {
                    type
                    tag
                    url
                }
            }
        }""",
        "variables": {"mentor": mentor, "question": question},
    }


fetch_answer_transcript_media_json_schema = {
    "type": "object",
    "properties": {
        "data": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "object",
                    "properties": {
                        "transcript": {"type": "string"},
                        "webMedia": {
                            "type": ["object", "null"],
                            "properties": {
                                "type": {"type": "string"},
                                "tag": {"type": "string"},
                                "url": {"type": "string"},
                            },
                        },
                        "mobileMedia": {
                            "type": ["object", "null"],
                            "properties": {
                                "type": {"type": "string"},
                                "tag": {"type": "string"},
                                "url": {"type": "string"},
                            },
                        },
                        "vttMedia": {
                            "type": ["object", "null"],
                            "properties": {
                                "type": {"type": "string"},
                                "tag": {"type": "string"},
                                "url": {"type": "string"},
                            },
                        },
                    },
                    "required": ["transcript", "webMedia", "mobileMedia", "vttMedia"],
                }
            },
            "required": ["answer"],
        },
    },
    "required": ["data"],
}


def fetch_answer_transcript_and_media(mentor: str, question: str):
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    gql_query = fetch_answer_transcript_and_media_gql(mentor, question)
    json_res = exec_graphql_with_json_validation(
        gql_query, fetch_answer_transcript_media_json_schema, headers=headers
    )
    answer_data = json_res["data"]["answer"]
    media = []
    if answer_data["webMedia"] is not None:
        media.append(answer_data["webMedia"])
    if answer_data["mobileMedia"] is not None:
        media.append(answer_data["mobileMedia"])
    if answer_data["vttMedia"] is not None:
        media.append(answer_data["vttMedia"])
    return (answer_data["transcript"], media)


@dataclass
class ImportTaskCreateGraphQLUpdate:
    status: str
    errorMessage: str = ""  # noqa


@dataclass
class AnswerMediaMigrationTask:
    question: str
    status: str
    errorMessage: str = ""  # noqa


@dataclass
class ImportTaskCreateS3VideoMigration:
    status: str
    answerMediaMigrations: List[AnswerMediaMigrationTask]  # noqa


@dataclass
class ImportTaskGQLRequest:
    mentor: str
    graphql_update: ImportTaskCreateGraphQLUpdate
    s3_video_migration: ImportTaskCreateS3VideoMigration


def import_task_create_gql_query(req: ImportTaskGQLRequest) -> GQLQueryBody:
    return {
        "query": """mutation ImportTaskCreate($mentor: ID!,
        $graphQLUpdate: GraphQLUpdateInputType!,
        $s3VideoMigrate: S3VideoMigrationInputType!) {
            api {
                importTaskCreate(graphQLUpdate: $graphQLUpdate, mentor: $mentor, s3VideoMigrate: $s3VideoMigrate)
            }
        }""",
        "variables": {
            "mentor": req.mentor,
            "graphQLUpdate": req.graphql_update,
            "s3VideoMigrate": req.s3_video_migration,
        },
    }


def import_task_create_gql(req: ImportTaskGQLRequest) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = import_task_create_gql_query(req)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))
