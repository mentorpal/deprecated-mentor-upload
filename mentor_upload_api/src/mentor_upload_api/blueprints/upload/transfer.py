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

transfer_blueprint = Blueprint("transfer", __name__)


def _to_status_url(root: str, id: str) -> str:
    return f"{request.url_root.replace('http://', 'https://', 1) if (environ.get('STATUS_URL_FORCE_HTTPS') or '').lower() in ('1', 'y', 'true', 'on') and str.startswith(request.url_root,'http://') else request.url_root}upload/transfer/status/{id}"


def get_upload_root() -> str:
    return environ.get("UPLOAD_ROOT") or "./uploads"


@transfer_blueprint.route("/", methods=["POST"])
@transfer_blueprint.route("", methods=["POST"])
def transfer():
    body = request.json
    if not body:
        raise Exception("missing required param body")
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


@transfer_blueprint.route("/cancel/", methods=["POST"])
@transfer_blueprint.route("/cancel", methods=["POST"])
def cancel():
    body = request.json
    if not body:
        raise Exception("missing required param body")
    mentor = body.get("mentor")
    question = body.get("question")
    task_id = body.get("task")
    req = {"mentor": mentor, "question": question, "task_id": task_id}
    t = mentor_upload_tasks.tasks.cancel_task.apply_async(
        queue=mentor_upload_tasks.get_queue_finalization_stage(), args=[req]
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
