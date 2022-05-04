#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
# flake8: noqa
from dataclasses import dataclass
import json
from os import environ
from typing import List, TypedDict

import requests

from mentor_upload_process.helpers import exec_graphql_with_json_validation

from . import MentorExportJson, ReplacedMentorDataChanges


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
class UploadTaskRequest:
    mentor: str
    question: str
    task_list: List[TaskInfo]
    transcript: str = None
    media: List[Media] = None


@dataclass
class UpdateTaskStatusRequest:
    mentor: str
    question: str
    task_id: str
    new_status: str
    transcript: str = None
    media: Media = None


@dataclass
class MediaUpdateRequest:
    mentor: str
    question: str
    web_media: Media = None
    mobile_media: Media = None
    vtt_media: Media = None


class GQLQueryBody(TypedDict):
    query: str


def answer_upload_update_gql(req: AnswerUpdateRequest) -> GQLQueryBody:
    variables = {}
    variables["mentorId"] = req.mentor
    variables["questionId"] = req.question
    variables["answer"] = {"transcript": req.transcript, "media": req.media}
    if req.has_edited_transcript is not None:
        variables["answer"]["hasEditedTranscript"] = req.has_edited_transcript
    return {
        "query": """mutation UploadAnswer($mentorId: ID!, $questionId: ID!, $answer: UploadAnswerType!) {
            api {
                uploadAnswer(mentorId: $mentorId, questionId: $questionId, answer: $answer)
            }
        }""",
        "variables": variables,
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


fetch_answer_json_schema = {
    "type": "object",
    "properties": {
        "data": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "object",
                    "properties": {
                        "hasUntransferredMedia": {"type": "boolean"},
                        "transcript": {"type": "string"},
                        "media": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string"},
                                    "tag": {"type": "string"},
                                    "url": {"type": "string"},
                                    "needsTransfer": {"type": "boolean"},
                                },
                                "required": ["type", "tag", "url", "needsTransfer"],
                            },
                        },
                    },
                    "required": ["transcript", "media", "hasUntransferredMedia"],
                }
            },
            "required": ["answer"],
        },
    },
    "required": ["data"],
}


def fetch_answer(mentor: str, question: str) -> dict:
    body = answer_query_gql(mentor, question)
    json_res = exec_graphql_with_json_validation(body, fetch_answer_json_schema)
    data = json_res["data"]["answer"]
    return data


def upload_update_answer(req: AnswerUpdateRequest) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = answer_upload_update_gql(req)
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


def upload_task_status_update(req: UpdateTaskStatusRequest) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = upload_task_status_req_gql(req)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))


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


fetch_question_name_schema = {
    "type": "object",
    "properties": {
        "data": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
            "required": ["question"],
        }
    },
    "required": ["data"],
}


def fetch_question_name(question_id: str) -> str:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    gql_query = fetch_question_name_gql(question_id)
    json_res = exec_graphql_with_json_validation(
        gql_query, fetch_question_name_schema, headers=headers
    )
    return json_res["data"]["question"]["name"]


def fetch_answer_transcript_and_media_gql(mentor: str, question: str) -> GQLQueryBody:
    return {
        "query": """query Answer($mentor: ID!, $question: ID!) {
            answer(mentor: $mentor, question: $question){
                hasEditedTranscript
                transcript
                media {
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
                        "hasEditedTranscript": {"type": "boolean"},
                        "transcript": {"type": "string"},
                        "media": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string"},
                                    "tag": {"type": "string"},
                                    "url": {"type": "string"},
                                },
                                "required": ["type", "tag", "url"],
                            },
                        },
                    },
                    "required": ["hasEditedTranscript", "transcript", "media"],
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
    return (
        json_res["data"]["answer"]["transcript"],
        json_res["data"]["answer"]["media"],
        json_res["data"]["answer"]["hasEditedTranscript"],
    )


def media_update_gql(req: MediaUpdateRequest) -> GQLQueryBody:
    variables = {"mentorId": req.mentor, "questionId": req.question}
    if req.web_media:
        variables["webMedia"] = req.web_media
    if req.mobile_media:
        variables["mobileMedia"] = req.mobile_media
    if req.vtt_media:
        variables["vttMedia"] = req.vtt_media

    return {
        "query": """mutation MediaUpdate($mentorId: ID!, $questionId: ID!, $webMedia: AnswerMediaInputType, $mobileMedia: AnswerMediaInputType, $vttMedia: AnswerMediaInputType) {
            api {
                mediaUpdate(mentorId: $mentorId, questionId: $questionId, webMedia: $webMedia, mobileMedia: $mobileMedia, vttMedia: $vttMedia)
            }
        }""",
        "variables": variables,
    }


def update_media(req: MediaUpdateRequest) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = media_update_gql(req)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))


def fetch_text_from_url(url: str) -> str:
    res = requests.get(url)
    res.raise_for_status()
    return res.text


@dataclass
class ImportTaskCreateGraphQLUpdate:
    status: str
    errorMessage: str = ""


@dataclass
class AnswerMediaMigrationTask:
    question: str
    status: str
    errorMessage: str = ""


@dataclass
class ImportTaskCreateS3VideoMigration:
    status: str
    answerMediaMigrations: List[AnswerMediaMigrationTask]


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


@dataclass
class ImportMentorGQLRequest:
    mentor: str
    json: MentorExportJson
    replacedMentorDataChanges: ReplacedMentorDataChanges


def import_mentor_gql_query(req: ImportMentorGQLRequest) -> GQLQueryBody:
    return {
        "query": """mutation MentorImport($mentor: ID!,$json:MentorImportJsonType!, $replacedMentorDataChanges: ReplacedMentorDataChangesType!){
            api{
                mentorImport(mentor: $mentor,json:$json, replacedMentorDataChanges: $replacedMentorDataChanges){
                    answers{
                        hasUntransferredMedia
                        question{
                            _id
                        }
                        webMedia{
                            url
                            type
                            tag
                            needsTransfer
                        }
                        mobileMedia{
                            url
                            type
                            tag
                            needsTransfer
                        }
                        vttMedia{
                            url
                            type
                            tag
                            needsTransfer
                        }
                    }
                }
            }
            }""",
        "variables": {
            "mentor": req.mentor,
            "json": req.json,
            "replacedMentorDataChanges": req.replacedMentorDataChanges,
        },
    }


import_mentor_gql_response_schema = {
    "type": "object",
    "properties": {
        "data": {
            "type": "object",
            "properties": {
                "api": {
                    "type": "object",
                    "properties": {
                        "mentorImport": {
                            "type": "object",
                            "properties": {
                                "answers": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "hasUntransferredMedia": {
                                                "type": ["boolean", "null"]
                                            },
                                            "question": {
                                                "type": "object",
                                                "properties": {
                                                    "_id": {"type": "string"},
                                                },
                                                "required": ["_id"],
                                            },
                                            "webMedia": {
                                                "type": ["object", "null"],
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "url": {"type": "string"},
                                                        "type": {"type": "string"},
                                                        "tag": {"type": "string"},
                                                        "needsTransfer": {
                                                            "type": "boolean"
                                                        },
                                                    },
                                                },
                                            },
                                            "mobileMedia": {
                                                "type": ["object", "null"],
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "url": {"type": "string"},
                                                        "type": {"type": "string"},
                                                        "tag": {"type": "string"},
                                                        "needsTransfer": {
                                                            "type": "boolean"
                                                        },
                                                    },
                                                },
                                            },
                                            "vttMedia": {
                                                "type": ["object", "null"],
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "url": {"type": "string"},
                                                        "type": {"type": "string"},
                                                        "tag": {"type": "string"},
                                                        "needsTransfer": {
                                                            "type": "boolean"
                                                        },
                                                    },
                                                },
                                            },
                                        },
                                        "required": [
                                            "hasUntransferredMedia",
                                            "question",
                                            "webMedia",
                                            "mobileMedia",
                                            "vttMedia",
                                        ],
                                    },
                                }
                            },
                            "required": ["answers"],
                        }
                    },
                    "required": ["mentorImport"],
                }
            },
            "required": ["api"],
        }
    },
    "required": ["data"],
}


class MentorImportMediaResponse:
    url: str
    type: str
    tag: str
    needsTransfer: bool


class MentorImportQuestionResponse:
    _id: str


class MentorImportAnswersResponse:
    hasUntransferredMedia: bool
    question: MentorImportQuestionResponse
    media: List[MentorImportMediaResponse]


class MentorImportGQLResponse:
    answers: List[MentorImportAnswersResponse]


def get_media_list_from_answer_gql(answer_gql):
    media_list = []
    if answer_gql["webMedia"]:
        media_list.append(answer_gql["webMedia"])
    if answer_gql["mobileMedia"]:
        media_list.append(answer_gql["mobileMedia"])
    if answer_gql["vttMedia"]:
        media_list.append(answer_gql["vttMedia"])
    return media_list


def import_mentor_gql(req: ImportMentorGQLRequest) -> MentorImportGQLResponse:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    query = import_mentor_gql_query(req)
    res = exec_graphql_with_json_validation(
        query, import_mentor_gql_response_schema, headers=headers
    )
    res_data = res["data"]["api"]["mentorImport"]
    import_response_data = {
        "answers": list(
            map(
                lambda answer: {
                    **answer,
                    "media": get_media_list_from_answer_gql(answer),
                },
                res_data["answers"],
            )
        )
    }
    return import_response_data


@dataclass
class AnswerMediaMigrateUpdate:
    question: str
    status: str
    errorMessage: str


@dataclass
class ImportTaskUpdateGQLRequest:
    mentor: str
    graphql_update: ImportTaskCreateGraphQLUpdate = None
    s3_video_migration: ImportTaskCreateS3VideoMigration = None
    answerMediaMigrateUpdate: AnswerMediaMigrateUpdate = None


def import_task_update_gql_query(req: ImportTaskUpdateGQLRequest) -> GQLQueryBody:
    variables = {}
    variables["mentor"] = req.mentor
    if req.graphql_update:
        variables["graphQLUpdate"] = req.graphql_update
    if req.s3_video_migration:
        variables["s3VideoMigrateUpdate"] = req.s3_video_migration
    if req.answerMediaMigrateUpdate:
        variables["answerMediaMigrateUpdate"] = req.answerMediaMigrateUpdate

    return {
        "query": """mutation ImportTaskUpdate($mentor: ID!, $graphQLUpdate: GraphQLUpdateInputType, $s3VideoMigrateUpdate: S3VideoMigrationInputType, $answerMediaMigrateUpdate: AnswerMediaMigrationInputType){
                        api{
                            importTaskUpdate(mentor: $mentor, graphQLUpdate: $graphQLUpdate, s3VideoMigrateUpdate: $s3VideoMigrateUpdate, answerMediaMigrateUpdate:$answerMediaMigrateUpdate)
                        }
                    }""",
        "variables": variables,
    }


def import_task_update_gql(req: ImportTaskGQLRequest) -> None:
    headers = {"mentor-graphql-req": "true", "Authorization": f"bearer {get_api_key()}"}
    body = import_task_update_gql_query(req)
    res = requests.post(get_graphql_endpoint(), json=body, headers=headers)
    res.raise_for_status()
    tdjson = res.json()
    import logging

    logging.error("")
    if "errors" in tdjson:
        raise Exception(json.dumps(tdjson.get("errors")))
