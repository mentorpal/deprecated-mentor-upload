#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env.

import os  # NOQA
import logging  # NOQA
from celery import Celery  # NOQA
from kombu import Exchange, Queue  # NOQA

from mentor_upload_process import (  # NOQA
    CancelTaskRequest,
    CancelTaskResponse,
    ProcessAnswerRequest,
    ProcessAnswerResponse,
    ProcessTransferRequest,
    TrimExistingUploadRequest,
    process,
    RegenVTTRequest,
)

log = logging.getLogger("upload-worker-tasks")

if os.environ.get("IS_SENTRY_ENABLED", "") == "true":
    log.info("SENTRY enabled, calling init")
    import sentry_sdk  # NOQA E402
    from sentry_sdk.integrations.celery import CeleryIntegration  # NOQA E402

    sentry_sdk.init(
        dsn=os.environ.get("SENTRY_DSN_MENTOR_UPLOAD"),
        # include project so issues can be filtered in sentry:
        environment=os.environ.get("PYTHON_ENV", "careerfair-qa"),
        integrations=[CeleryIntegration()],
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=0.20,
        debug=os.environ.get("SENTRY_DEBUG_UPLOADER", "") == "true",
    )


def get_queue_trim_upload_stage() -> str:
    return os.environ.get("TRIM_UPLOAD_QUEUE_NAME") or "trim_upload"


def get_queue_transcribe_stage() -> str:
    return os.environ.get("TRANSCRIBE_QUEUE_NAME") or "transcribe"


def get_queue_transcode_stage() -> str:
    return os.environ.get("TRANSCODE_QUEUE_NAME") or "transcode"


def get_queue_finalization_stage() -> str:
    return os.environ.get("FINALIZATION_QUEUE_NAME") or "finalization"


def get_queue_cancel_task() -> str:
    return os.environ.get("CANCEL_TASK_QUEUE_NAME") or "cancel"


broker_url = (
    os.environ.get("UPLOAD_CELERY_BROKER_URL")
    or os.environ.get("CELERY_BROKER_URL")
    or "redis://redis:6379/0"
)
log.info("%s", {"broker_url": broker_url})
celery = Celery("mentor_upload_tasks", broker=broker_url)

celery_config = {
    "accept_content": ["json"],
    "broker_url": broker_url,
    "event_serializer": os.environ.get("CELERY_EVENT_SERIALIZER", "json"),
    "result_backend": (
        os.environ.get("UPLOAD_CELERY_RESULT_BACKEND")
        or os.environ.get("CELERY_RESULT_BACKEND")
        or "redis://redis:6379/0"
    ),
    "result_serializer": os.environ.get("CELERY_RESULT_SERIALIZER", "json"),
    "task_default_queue": get_queue_finalization_stage(),
    "task_default_exchange": get_queue_finalization_stage(),
    # for debugging:
    "worker_concurrency":1,  "worker_prefetch_multiplier": 1,
    "task_default_routing_key": get_queue_finalization_stage(),
    "task_queues": [
        Queue(
            get_queue_trim_upload_stage(),
            exchange=Exchange(
                get_queue_trim_upload_stage(),
                "direct",
                durable=True,
            ),
            routing_key=get_queue_trim_upload_stage(),
        ),
        Queue(
            get_queue_transcode_stage(),
            exchange=Exchange(
                get_queue_transcode_stage(),
                "direct",
                durable=True,
            ),
            routing_key=get_queue_transcode_stage(),
        ),
        Queue(
            get_queue_transcribe_stage(),
            exchange=Exchange(
                get_queue_transcribe_stage(),
                "direct",
                durable=True,
            ),
            routing_key=get_queue_transcribe_stage(),
        ),
        Queue(
            get_queue_finalization_stage(),
            exchange=Exchange(get_queue_finalization_stage(), "direct", durable=True),
            routing_key=get_queue_finalization_stage(),
        ),
        Queue(
            get_queue_cancel_task(),
            exchange=Exchange(get_queue_cancel_task(), "direct", durable=True),
            routing_key=get_queue_cancel_task(),
        ),
    ],
    "task_routes": {
        "mentor_upload_tasks.tasks.trim_upload_stage": {
            "queue": get_queue_trim_upload_stage()
        },
        "mentor_upload_tasks.tasks.transcribe_stage": {
            "queue": get_queue_transcribe_stage()
        },
        "mentor_upload_tasks.tasks.transcode_stage": {
            "queue": get_queue_transcode_stage()
        },
        "mentor_upload_tasks.tasks.finalization_stage": {
            "queue": get_queue_finalization_stage()
        },
        "mentor_upload_tasks.tasks.cancel_task": {"queue": get_queue_cancel_task()},
    },
    "task_serializer": os.environ.get("CELERY_TASK_SERIALIZER", "json"),
}

log.info("%s", {"celery_config": celery_config})
celery.conf.update(celery_config)


@celery.task()
def trim_upload_stage(
    req: ProcessAnswerRequest,
) -> ProcessAnswerResponse:
    log.info(req)
    task_id = trim_upload_stage.request.id
    log.debug(trim_upload_stage.request)
    return process.trim_upload_stage(req, task_id)


@celery.task()
def transcode_stage(
    dict_tuple: dict,
    req: ProcessAnswerRequest,
) -> ProcessAnswerResponse:
    log.info("transcode stage: %s, %s", dict_tuple, req)
    task_id = transcode_stage.request.id
    log.debug(transcode_stage.request)
    return process.transcode_stage(dict_tuple, req, task_id)


@celery.task()
def transcribe_stage(
    dict_tuple: dict,
    req: ProcessAnswerRequest,
) -> ProcessAnswerResponse:
    log.info("transcribe stage: %s, %s", dict_tuple, req)
    task_id = transcribe_stage.request.id
    log.debug(transcribe_stage.request)
    return process.transcribe_stage(dict_tuple, req, task_id)


@celery.task()
def finalization_stage(
    dict_tuple: dict, req: ProcessAnswerRequest
) -> ProcessAnswerResponse:
    log.info("finalization stage: %s, %s", dict_tuple, req)
    task_id = finalization_stage.request.id
    log.debug(finalization_stage.request)
    return process.finalization_stage(dict_tuple, req=req, task_id=task_id)


@celery.task()
def process_transfer_video(req: ProcessTransferRequest):
    log.info("process_transfer_video: %s", req)
    task_id = process_transfer_video.request.id
    log.debug(process_transfer_video.request)
    return process.process_transfer_video(req, task_id)


@celery.task()
def trim_existing_upload(req: TrimExistingUploadRequest):
    log.info("trim_existing_upload stage: %s", req)
    task_id = trim_existing_upload.request.id
    log.debug(trim_existing_upload.request)
    return process.trim_existing_upload(req, task_id)


@celery.task()
def regen_vtt(req: RegenVTTRequest):
    log.info(req)
    return process.regen_vtt(req)


@celery.task()
def cancel_task(req: CancelTaskRequest) -> CancelTaskResponse:
    log.info("cancel_task: %s", req)
    t = process.cancel_task(req)
    celery.control.revoke(req.get("task_id"), terminate=True)
    return t


@celery.task()
def on_chord_error(request, exc, traceback):
    log.error("Task {0!r} raised error: {1!r}".format(request.id, exc))
    log.error(exc)
    # TODO report to sentry
