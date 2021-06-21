#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
import datetime
import json
import subprocess
from os import environ, path, makedirs
import uuid

from flask import Blueprint, jsonify, request
import imageio_ffmpeg

import mentor_upload_tasks
import mentor_upload_tasks.tasks

answer_blueprint = Blueprint("answer", __name__)


def _to_status_url(root: str, id: str) -> str:
    return f"{request.url_root.replace('http://', 'https://', 1) if (environ.get('STATUS_URL_FORCE_HTTPS') or '').lower() in ('1', 'y', 'true', 'on') and str.startswith(request.url_root,'http://') else request.url_root}upload/answer/status/{id}"


def get_upload_root() -> str:
    return environ.get("UPLOAD_ROOT") or "./uploads"


@answer_blueprint.route("/", methods=["POST"])
@answer_blueprint.route("", methods=["POST"])
def upload():
    body = json.loads(request.form.get("body", "{}"))
    if not body:
        raise Exception("missing required param body")
    mentor = body.get("mentor")
    question = body.get("question")
    trim = body.get("trim")
    upload_file = request.files["video"]
    root_ext = path.splitext(upload_file.filename)
    file_name = f"{uuid.uuid4()}-{mentor}-{question}{root_ext[1]}"
    file_path = path.join(get_upload_root(), file_name)
    makedirs(get_upload_root(), exist_ok=True)
    upload_file.save(file_path)
    if trim is not None:
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        file_name_trimmed = f"trim-{file_name}"
        file_path_trimmed = path.join(get_upload_root(), file_name_trimmed)
        subprocess.run(
            [
                ffmpeg,
                "-i",
                file_path,
                "-ss",
                str(datetime.timedelta(seconds=trim.get("start"))),
                "-to",
                str(datetime.timedelta(seconds=trim.get("end"))),
                "-c:v",
                "libx264",
                "-crf",
                "30",
                file_path_trimmed,
            ]
        )
        file_name = file_name_trimmed
    req = {"mentor": mentor, "question": question, "video_path": file_name}
    t = mentor_upload_tasks.tasks.process_answer_video.apply_async(args=[req])
    return jsonify(
        {
            "data": {
                "id": t.id,
                "statusUrl": _to_status_url(request.url_root, t.id),
            }
        }
    )


@answer_blueprint.route("/cancel/", methods=["POST"])
@answer_blueprint.route("/cancel", methods=["POST"])
def cancel():
    body = request.json
    if not body:
        raise Exception("missing required param body")
    mentor = body.get("mentor")
    question = body.get("question")
    task_id = body.get("task")
    req = {"mentor": mentor, "question": question, "task_id": task_id}
    t = mentor_upload_tasks.tasks.cancel_task.apply_async(args=[req])
    return jsonify({"data": {"id": t.id, "cancelledId": task_id}})


@answer_blueprint.route("/status/<task_id>/", methods=["GET"])
@answer_blueprint.route("/status/<task_id>", methods=["GET"])
def upload_status(task_id: str):
    t = mentor_upload_tasks.tasks.process_answer_video.AsyncResult(task_id)
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
