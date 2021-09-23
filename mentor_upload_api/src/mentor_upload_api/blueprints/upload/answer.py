#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
import json

from os import environ, path, makedirs
import uuid

from flask import Blueprint, jsonify, request

from celery import group, chord, chain

from mentor_upload_api.api import (
    StatusUpdateRequest,
    update_status,
)
import mentor_upload_tasks
import mentor_upload_tasks.tasks

answer_blueprint = Blueprint("answer", __name__)


def _to_status_url(root: str, id: str) -> str:
    return f"{request.url_root.replace('http://', 'https://', 1) if (environ.get('STATUS_URL_FORCE_HTTPS') or '').lower() in ('1', 'y', 'true', 'on') and str.startswith(request.url_root,'http://') else request.url_root}upload/answer/status/{id}"


def get_upload_root() -> str:
    return environ.get("UPLOAD_ROOT") or "./uploads"


def begin_tasks_in_parallel(req):
    print("begin tasks in parallel")
    parallel_group = group(
        mentor_upload_tasks.tasks.transcode_stage.si(req=req).set(
            queue=mentor_upload_tasks.get_queue_transcode_stage()
        ),
        mentor_upload_tasks.tasks.transcribe_stage.si(req=req).set(
            queue=mentor_upload_tasks.get_queue_transcribe_stage()
        ),
    )
    # try 1
    # my_chord= chord( chord(
    #                 [mentor_upload_tasks.tasks.init_stage.s(
    #                 req=req
    #                 ).set(queue=mentor_upload_tasks.get_queue_init_stage())]
    #             )(
    #                 parallel_group
    #             )
    # )(
    #     mentor_upload_tasks.tasks.finalization_stage.s(req=req).set(queue=mentor_upload_tasks.get_queue_finalization_stage())
    # )

    my_chord = chord(
        group(
            [
                chord(
                    group(
                        [
                            mentor_upload_tasks.tasks.init_stage.s(req=req).set(
                                queue=mentor_upload_tasks.get_queue_init_stage()
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
    )
    my_chord.delay()

    # my_chord= chord( group([chord(
    #                 group([mentor_upload_tasks.tasks.init_stage.s(
    #                 req=req
    #                 ).set(queue=mentor_upload_tasks.get_queue_init_stage())])
    #             )(
    #                 parallel_group
    #             )])
    # )(
    #     mentor_upload_tasks.tasks.finalization_stage.s(req=req).set(queue=mentor_upload_tasks.get_queue_finalization_stage())
    # )

    # final_task = mentor_upload_tasks.tasks.finalization_stage.s(req=req).set(queue=mentor_upload_tasks.get_queue_finalization_stage())

    # try 2
    # chain(chord(
    #         [mentor_upload_tasks.tasks.init_stage.s(
    #         req=req
    #         ).set(queue=mentor_upload_tasks.get_queue_init_stage())]
    #     )(
    #         parallel_group
    #     ), mentor_upload_tasks.tasks.finalization_stage.s(req=req).set(queue=mentor_upload_tasks.get_queue_finalization_stage()))

    # chord_2 = chord(
    #     chord_1
    # )(
    #     mentor_upload_tasks.tasks.finalization_stage.s(req=req).set(
    #         queue=mentor_upload_tasks.get_queue_finalization_stage()
    #     )
    # )

    # my_chord.delay()

    # c = chord(
    #         group([chord(group([chord(group([first_task.s('foo')]),

    #                                 body=first_body.s())]),

    #                     body=second_body.s())]),

    #         body=third_body.s())
    return my_chord


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

    # because I moved this to its own function, will have to test
    my_chord = begin_tasks_in_parallel(req)
    task_ids = []
    for task in my_chord.parent.children:
        task_ids.append(task.id)
    task_ids.append(my_chord.id)
    # raise Exception(my_chord.id)
    update_status(
        StatusUpdateRequest(
            mentor=mentor,
            question=question,
            task_id=task_ids,
            status="QUEUING",
            upload_flag="QUEUED",
            transcoding_flag="QUEUED",
            finalization_flag="QUEUED",
            transcribing_flag="QUEUED",
            transcript="",
            media=[],
        )
    )
    return jsonify(
        {
            "data": {
                "id": task_ids,
                "statusUrl": _to_status_url(request.url_root, task_ids),
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
    t = mentor_upload_tasks.tasks.cancel_task.apply_async(
        queue=mentor_upload_tasks.get_queue_transcribe_stage(),
        args=[req],
    )
    return jsonify({"data": {"id": t.id, "cancelledId": task_id}})


@answer_blueprint.route("/status/<task_id>/", methods=["GET"])
@answer_blueprint.route("/status/<task_id>", methods=["GET"])
def upload_status(task_id: str):
    t = mentor_upload_tasks.tasks.upload_transcribe_transcode_answer_video.AsyncResult(
        task_id
    )
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
