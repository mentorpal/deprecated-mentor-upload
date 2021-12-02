#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
import json

from os import environ, path, makedirs, listdir, remove, scandir
from datetime import datetime
from dateutil import tz
import uuid

from flask import Blueprint, jsonify, request, send_from_directory

from celery import group, chord

from mentor_upload_api.api import (
    UploadTaskRequest,
    upload_task_update,
)
import mentor_upload_tasks
import mentor_upload_tasks.tasks

answer_blueprint = Blueprint("answer", __name__)


def _to_status_url(root: str, id: str) -> str:
    return f"{request.url_root.replace('http://', 'https://', 1) if (environ.get('STATUS_URL_FORCE_HTTPS') or '').lower() in ('1', 'y', 'true', 'on') and str.startswith(request.url_root,'http://') else request.url_root}upload/answer/status/{id}"


def get_upload_root() -> str:
    return environ.get("UPLOAD_ROOT") or "./uploads"


def begin_tasks_in_parallel(req):
    parallel_group = group(
        mentor_upload_tasks.tasks.transcode_stage.s(req=req).set(
            queue=mentor_upload_tasks.get_queue_transcode_stage()
        ),
        mentor_upload_tasks.tasks.transcribe_stage.s(req=req).set(
            queue=mentor_upload_tasks.get_queue_transcribe_stage()
        ),
    )
    my_chord = chord(
        group(
            [
                chord(
                    group(
                        [
                            mentor_upload_tasks.tasks.trim_upload_stage.s(req=req).set(
                                queue=mentor_upload_tasks.get_queue_trim_upload_stage()
                            )
                        ]
                    ),
                    body=parallel_group,
                )
            ]
        ),
        body=mentor_upload_tasks.tasks.finalization_stage.s(req=req).set(
            queue=mentor_upload_tasks.get_queue_finalization_stage()
        ),
    ).on_error(mentor_upload_tasks.tasks.on_chord_error.s())
    return my_chord.delay()


@answer_blueprint.route("/trim_existing_upload/", methods=["POST"])
@answer_blueprint.route("/trim_existing_upload", methods=["POST"])
def trim_existing_upload():
    body = json.loads(request.form.get("body", "{}"))
    if not body:
        raise Exception("missing required param body")
    mentor = body.get("mentor")
    question = body.get("question")
    trim = body.get("trim")
    req = {
        "mentor": mentor,
        "question": question,
        "trim": trim,
    }
    task = mentor_upload_tasks.tasks.trim_existing_upload.apply_async(
        queue=mentor_upload_tasks.get_queue_trim_upload_stage(), args=[req]
    )
    task_list = [
        {
            "task_name": "trim_upload",
            "task_id": task.id,
            "status": "QUEUED",
        }
    ]
    upload_task_update(
        UploadTaskRequest(
            mentor=mentor,
            question=question,
            task_list=task_list,
        )
    )
    return jsonify(
        {
            "data": {
                "taskList": task_list,
                "statusUrl": _to_status_url(request.url_root, [task.id]),
            }
        }
    )


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
    req = {
        "mentor": mentor,
        "question": question,
        "video_path": file_name,
        "trim": trim,
    }
    my_chord = begin_tasks_in_parallel(req)

    task_ids = []
    for task in my_chord.parent.results:
        task_ids.append(task.id)  # transcode id, transcribe id
    for task in my_chord.parent.parent.results:
        task_ids.append(task.id)  # init_id
    task_ids.append(my_chord.id)  # finalization id
    task_list = [
        {
            "task_name": "trim_upload",
            "task_id": my_chord.parent.parent.results[0].id,
            "status": "QUEUED",
        },
        {
            "task_name": "transcoding",
            "task_id": my_chord.parent.results[0].id,
            "status": "QUEUED",
        },
        {
            "task_name": "transcribing",
            "task_id": my_chord.parent.results[1].id,
            "status": "QUEUED",
        },
        {
            "task_name": "finalization",
            "task_id": my_chord.id,
            "status": "QUEUED",
        },
    ]
    upload_task_update(
        UploadTaskRequest(
            mentor=mentor,
            question=question,
            task_list=task_list,
            transcript="",
            media=[],
        )
    )
    return jsonify(
        {
            "data": {
                "taskList": task_list,
                "statusUrl": _to_status_url(request.url_root, task_ids),
            }
        }
    )


def list_files_from_directory(file_directory: str):
    files = []
    cali_tz = tz.gettz("America/Los_Angeles")
    for entry in scandir(file_directory):
        files.append(
            {
                "fileName": entry.name,
                "size": entry.stat().st_size,
                "uploadDate": datetime.fromtimestamp(
                    entry.stat().st_ctime, tz=cali_tz
                ).strftime("%m/%d/%Y %I:%M:%S %p")
                + " (PST)",
            }
        )
    return files


@answer_blueprint.route("/mounted_files/", methods=["GET"])
@answer_blueprint.route("/mounted_files", methods=["GET"])
def mounted_files():
    try:
        file_directory = get_upload_root()
        files = list_files_from_directory(file_directory)
        return {
            "data": {
                "mountedFiles": files,
            }
        }
    except Exception as x:
        import logging

        logging.error("failed to fetch files from upload directory")
        logging.exception(x)


@answer_blueprint.route("/remove_mounted_file/<file_name>/", methods=["POST"])
@answer_blueprint.route("/remove_mounted_file/<file_name>", methods=["POST"])
def remove_mounted_file(file_name: str):
    try:
        file_path = path.join(get_upload_root(), file_name)
        remove(file_path)
        return {"data": {"fileRemoved": True}}
    except Exception as x:
        import logging

        logging.error(f"failed to remove file {file_name} from uploads directory")
        logging.exception(x)
        return {"data": {"fileRemoved": False}}


@answer_blueprint.route("/download_mounted_file/<file_name>/", methods=["GET"])
@answer_blueprint.route("/download_mounted_file/<file_name>", methods=["GET"])
def download_mounted_file(file_name: str):
    try:
        file_directory = get_upload_root()
        return send_from_directory(file_directory, file_name, as_attachment=True)
    except Exception as x:
        import logging

        logging.error(
            f"failed to find video file {file_name} in folder {file_directory}"
        )
        logging.exception(x)


def full_video_file_name_from_directory(
    mentor: str, question: str, file_directory: str
):
    files = listdir(file_directory)
    for file_name in files:
        # video file name format: uuid1-mentorID-questionID.mp4
        file_name_split = file_name.split("-")
        file_mentor = file_name_split[-2]
        file_question = file_name_split[-1].split(".")[0]
        if file_mentor == mentor and file_question == question:
            return file_name
    raise Exception(
        f"Failed to find video file for mentor: {mentor} and question: {question}"
    )


@answer_blueprint.route("/download_video/<mentor>/<question>/", methods=["GET"])
@answer_blueprint.route("/download_video/<mentor>/<question>", methods=["GET"])
def download_video(mentor: str, question: str):
    try:
        file_directory = get_upload_root()
        file_name = full_video_file_name_from_directory(
            mentor, question, file_directory
        )
        return send_from_directory(file_directory, file_name, as_attachment=True)
    except Exception as x:
        import logging

        logging.error(
            f"failed to find video file for mentor: {mentor} and question: {question} in folder {file_directory}"
        )
        logging.exception(x)


@answer_blueprint.route("/cancel/", methods=["POST"])
@answer_blueprint.route("/cancel", methods=["POST"])
def cancel():
    body = request.json
    if not body:
        raise Exception("missing required param body")
    mentor = body.get("mentor")
    question = body.get("question")
    task_id_list = body.get("task_ids_to_cancel")

    task_list = []

    for task_id in task_id_list:
        req = {"mentor": mentor, "question": question, "task_id": task_id}
        task_list.append(
            mentor_upload_tasks.tasks.cancel_task.si(req=req).set(
                queue=mentor_upload_tasks.get_queue_cancel_task()
            )
        )

    t = group(task_list).apply_async()
    return jsonify({"data": {"id": t.id, "cancelledIds": task_id_list}})


@answer_blueprint.route("/status/<task_name>/<task_id>/", methods=["GET"])
@answer_blueprint.route("/status/<task_name>/<task_id>", methods=["GET"])
def task_status(task_name: str, task_id: str):
    if task_name == "transcribe":
        t = mentor_upload_tasks.tasks.transcribe_stage.AsyncResult(task_id)
    elif task_name == "transcode":
        t = mentor_upload_tasks.tasks.transcode_stage.AsyncResult(task_id)
    elif task_name == "trim_upload":
        t = mentor_upload_tasks.tasks.trim_upload_stage.AsyncResult(task_id)
    elif task_name == "finalization":
        t = mentor_upload_tasks.tasks.finalization_stage.AsyncResult(task_id)
    else:
        import logging

        logging.exception("unrecognized task_name")

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


@answer_blueprint.route("/regen_vtt/", methods=["POST"])
@answer_blueprint.route("/regen_vtt", methods=["POST"])
def regen_vtt():
    body = json.loads(request.form.get("body", "{}"))
    if not body:
        raise Exception("missing required param body")
    mentor = body.get("mentor")
    question = body.get("question")
    req = {
        "mentor": mentor,
        "question": question,
    }
    task = mentor_upload_tasks.tasks.regen_vtt.apply_async(
        queue=mentor_upload_tasks.get_queue_trim_upload_stage(), args=[req]
    )
    result = task.wait(timeout=None, interval=0.5)

    return jsonify({"data": result})
