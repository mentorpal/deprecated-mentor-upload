#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from os import environ

from flask import Blueprint, jsonify, request

import mentor_upload_tasks
import mentor_upload_tasks.tasks


from mentor_upload_api.helpers import validate_json_payload_decorator
from mentor_upload_api.api import import_task_create_gql, ImportTaskGQLRequest


transfer_blueprint = Blueprint("transfer", __name__)


def _to_status_url(root: str, id: str) -> str:
    return f"{request.url_root.replace('http://', 'https://', 1) if (environ.get('STATUS_URL_FORCE_HTTPS') or '').lower() in ('1', 'y', 'true', 'on') and str.startswith(request.url_root,'http://') else request.url_root}upload/transfer/status/{id}"


def get_upload_root() -> str:
    return environ.get("UPLOAD_ROOT") or "./uploads"


transfer_media_json_schema = {
    "type": "object",
    "properties": {"mentor": {"type": "string"}, "question": {"type": "string"}},
    "required": ["mentor", "question"],
    "additionalProperties": False,
}


@transfer_blueprint.route("/", methods=["POST"])
@transfer_blueprint.route("", methods=["POST"])
@validate_json_payload_decorator(json_schema=transfer_media_json_schema)
def transfer(body):
    mentor = body.get("mentor")
    question = body.get("question")
    req = {
        "mentor": mentor,
        "question": question,
    }
    t = mentor_upload_tasks.tasks.process_transfer_video.apply_async(
        queue=mentor_upload_tasks.get_queue_finalization_stage(), args=[req]
    )
    return jsonify(
        {
            "data": {
                "id": t.id,
                "statusUrl": _to_status_url(request.url_root, t.id),
            }
        }
    )


# TODO: Most objects that could possibly be null here need to be fixed by updating GQL schema with a default value and then running an update script
transfer_mentor_json_schema = {
    "type": "object",
    "properties": {
        "mentor": {"type": "string"},
        "mentorExportJson": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "mentorInfo": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "firstName": {"type": "string"},
                        "title": {"type": "string"},
                        "email": {"type": "string"},
                        "thumbnail": {"type": "string"},
                        "allowContact": {"type": ["boolean", "null"]},
                        "defaultSubject": {"type": ["string", "null"]},
                        "mentorType": {"type": "string"},
                    },
                },
                "subjects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "_id": {"type": "string"},
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "type": {"type": "string"},
                            "isRequired": {"type": "boolean"},
                            "categories": {
                                "type": "array",
                                "items": {"$ref": "#/$defs/Category"},
                            },
                            "topics": {
                                "type": "array",
                                "items": {"$ref": "#/$defs/Topic"},
                            },
                            "questions": {
                                "type": "array",
                                "items": {"$ref": "#/$defs/SubjectQuestionGQL"},
                            },
                        },
                    },
                },
                "questions": {"type": "array", "items": {"$ref": "#/$defs/Question"}},
                "answers": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/AnswerGQL"},
                },
                "userQuestions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "_id": {"type": "string"},
                            "question": {"type": "string"},
                            "confidence": {"type": "number"},
                            "classifierAnswerType": {"type": "string"},
                            "feedback": {"type": "string"},
                            "mentor": {
                                "type": "object",
                                "properties": {
                                    "_id": {"type": "string"},
                                    "name": {"type": "string"},
                                },
                            },
                            "classifierAnswer": {
                                "type": "object",
                                "properties": {
                                    "_id": {"type": "string"},
                                    "question": {
                                        "type": "object",
                                        "properties": {
                                            "_id": {"type": "string"},
                                            "question": {"type": "string"},
                                        },
                                    },
                                    "transcript": {"type": "string"},
                                },
                            },
                            "graderAnswer": {
                                "type": ["object", "null"],
                                "properties": {
                                    "_id": {"type": "string"},
                                    "question": {
                                        "type": "object",
                                        "properties": {
                                            "_id": {"type": "string"},
                                            "question": {"type": "string"},
                                        },
                                    },
                                    "transcript": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
            "required": [
                "id",
                "mentorInfo",
                "subjects",
                "questions",
                "answers",
                "userQuestions",
            ],
        },
        "replacedMentorDataChanges": {
            "type": "object",
            "properties": {
                "questionChanges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "editType": {"type": "string"},
                            "data": {"$ref": "#/$defs/Question"},
                        },
                    },
                },
                "answerChanges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "editType": {"type": "string"},
                            "data": {"$ref": "#/$defs/AnswerGQL"},
                        },
                    },
                },
            },
            "required": ["questionChanges", "answerChanges"],
        },
    },
    "required": ["mentor", "mentorExportJson", "replacedMentorDataChanges"],
    "$defs": {
        "Category": {
            "type": ["object", "null"],
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
            },
        },
        "Topic": {
            "type": ["object", "null"],
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
            },
        },
        "Question": {
            "type": "object",
            "properties": {
                "_id": {"type": "string"},
                "question": {"type": "string"},
                "type": {"type": "string"},
                "name": {"type": "string"},
                "clientId": {"type": "string"},
                "paraphrases": {"type": "array", "items": {"type": "string"}},
                "mentor": {"type": ["string", "null"]},
                "mentorType": {"type": ["string", "null"]},
                "minVideoLength": {"type": ["number", "null"]},
            },
        },
        "SubjectQuestionGQL": {
            "type": "object",
            "properties": {
                "question": {"$ref": "#/$defs/Question"},
                "category": {"$ref": "#/$defs/Category"},
                "topics": {"type": "array", "items": {"$ref": "#/$defs/Topic"}},
            },
        },
        "AnswerGQL": {
            "type": "object",
            "properties": {
                "_id": {"type": "string"},
                "question": {"$ref": "#/$defs/Question"},
                "hasEditedTranscript": {"type": "boolean"},
                "transcript": {"type": "string"},
                "status": {"type": "string"},
                "media": {
                    "type": ["array", "null"],
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "tag": {"type": "string"},
                            "url": {"type": "string"},
                            "needsTransfer": {"type": "boolean"},
                        },
                    },
                },
                "hasUntransferredMedia": {"type": "boolean"},
            },
        },
    },
    "additionalProperties": False,
}


@transfer_blueprint.route("/mentor/", methods=["POST"])
@transfer_blueprint.route("/mentor", methods=["POST"])
@validate_json_payload_decorator(json_schema=transfer_mentor_json_schema)
def transfer_mentor(body):
    mentor = body.get("mentor")
    mentor_export_json = body.get("mentorExportJson")
    replace_mentor_data_changes = body.get("replacedMentorDataChanges")

    graphql_update = {"status": "QUEUED"}
    s3_video_migration = {"status": "QUEUED", "answerMediaMigrations": []}
    import_task_create_gql(
        ImportTaskGQLRequest(mentor, graphql_update, s3_video_migration)
    )

    req = {
        "mentor": mentor,
        "mentorExportJson": mentor_export_json,
        "replacedMentorDataChanges": replace_mentor_data_changes,
    }

    t = mentor_upload_tasks.tasks.process_transfer_mentor.apply_async(
        queue=mentor_upload_tasks.get_queue_finalization_stage(), args=[req]
    )
    return jsonify(
        {
            "data": {
                "statusUrl": _to_status_url(request.url_root, t.id),
            }
        }
    )


cancel_transfer_media_json_schema = {
    "type": "object",
    "properties": {
        "mentor": {"type": "string", "maxLength": 60, "minLength": 5},
        "question": {"type": "string", "maxLength": 60, "minLength": 5},
        "task": {"type": "string"},
    },
    "required": ["mentor", "question", "task"],
    "additionalProperties": False,
}


@transfer_blueprint.route("/cancel/", methods=["POST"])
@transfer_blueprint.route("/cancel", methods=["POST"])
@validate_json_payload_decorator(json_schema=cancel_transfer_media_json_schema)
def cancel(body):
    mentor = body.get("mentor")
    question = body.get("question")
    task_id = body.get("task")
    req = {"mentor": mentor, "question": question, "task_id": task_id}
    t = mentor_upload_tasks.tasks.cancel_task.apply_async(
        queue=mentor_upload_tasks.get_queue_cancel_task(), args=[req]
    )
    return jsonify({"data": {"id": t.id, "cancelledId": task_id}})


@transfer_blueprint.route("/status/<task_id>/", methods=["GET"])
@transfer_blueprint.route("/status/<task_id>", methods=["GET"])
def transfer_status(task_id: str):
    t = mentor_upload_tasks.tasks.process_transfer_video.AsyncResult(task_id)
    return jsonify(
        {
            "data": {
                "id": task_id,
                "state": t.state or "NONE",
                "status": t.status,
                "info": None
                if not t.info
                else t.info
                if isinstance(t.info, dict) or isinstance(t.info, list)
                else str(t.info),
            }
        }
    )
