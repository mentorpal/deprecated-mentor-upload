#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from contextlib import contextmanager
from datetime import datetime
from os import environ, path, makedirs, remove
from pathlib import Path
from tempfile import mkdtemp
from shutil import copyfile, rmtree
from urllib.parse import urljoin


import boto3
from boto3_type_annotations.s3 import Client as S3Client
import transcribe
import uuid

from . import (
    CancelTaskRequest,
    CancelTaskResponse,
    ProcessAnswerRequest,
    ProcessAnswerResponse,
)
from .media_tools import (
    trim_video,
    video_encode_for_mobile,
    video_encode_for_web,
    video_to_audio,
)
from .api import update_answer, update_status, AnswerUpdateRequest, StatusUpdateRequest


def upload_path(p: str) -> str:
    return path.join(environ.get("UPLOADS") or "./uploads", p)


def _require_env(n: str) -> str:
    env_val = environ.get(n, "")
    if not env_val:
        raise EnvironmentError(f"missing required env var {n}")
    return env_val


def _create_s3_client() -> S3Client:
    return boto3.client(
        "s3",
        region_name=_require_env("STATIC_AWS_REGION"),
        aws_access_key_id=_require_env("STATIC_AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=_require_env("STATIC_AWS_SECRET_ACCESS_KEY"),
    )


def _new_work_dir_name() -> str:
    return str(uuid.uuid1())  # can use uuid1 here cos private to server


@contextmanager
def _video_work_dir(source_path: str):
    media_work_dir = (
        Path(environ.get("TRANSCODE_WORK_DIR") or mkdtemp()) / _new_work_dir_name()
    )
    try:
        makedirs(media_work_dir)
        video_file = media_work_dir / path.basename(source_path)
        copyfile(source_path, video_file)
        yield (video_file, media_work_dir)
    finally:
        try:
            rmtree(str(media_work_dir))
        except Exception as x:
            import logging

            logging.error(f"failed to delete media work dir {media_work_dir}")
            logging.exception(x)


def cancel_task(req: CancelTaskRequest) -> CancelTaskResponse:
    update_status(
        StatusUpdateRequest(
            mentor=req.get("mentor"),
            question=req.get("question"),
            task_id=req.get("task_id"),
            status="CANCEL_IN_PROGRESS",
            transcript="",
            media=[],
        )
    )
    # TODO: potentially need to cancel s3 upload and aws transcribe if they have already started?
    update_status(
        StatusUpdateRequest(
            mentor=req.get("mentor"),
            question=req.get("question"),
            task_id=req.get("task_id"),
            status="CANCELLED",
            transcript="",
            media=[],
        )
    )


def process_answer_video(
    req: ProcessAnswerRequest, task_id: str
) -> ProcessAnswerResponse:
    video_path = req.get("video_path", "")
    if not video_path:
        raise Exception("missing required param 'video_path'")
    video_path_full = upload_path(video_path)
    if not path.isfile(video_path_full):
        raise Exception(f"video not found for path '{video_path}'")
    with _video_work_dir(video_path_full) as context:
        try:
            mentor = req.get("mentor")
            question = req.get("question")
            trim = req.get("trim", None)
            video_file, work_dir = context
            # TODO: should also be able to trim existing video (get from s3)
            if trim is not None:
                update_status(
                    StatusUpdateRequest(
                        mentor=mentor,
                        question=question,
                        task_id=task_id,
                        status="TRIM_IN_PROGRESS",
                        transcript="",
                        media=[],
                    )
                )
                trim_file = work_dir / "trim.mp4"
                trim_video(video_file, trim_file, trim.get("start"), trim.get("end"))
                video_file = trim_file
            # TODO: should skip the transcribe step if video is an idle
            update_status(
                StatusUpdateRequest(
                    mentor=mentor,
                    question=question,
                    task_id=task_id,
                    status="TRANSCRIBE_IN_PROGRESS",
                    transcript="",
                    media=[],
                )
            )
            audio_file = video_to_audio(video_file)
            video_mobile_file = work_dir / "mobile.mp4"
            video_web_file = work_dir / "web.mp4"
            video_encode_for_mobile(video_file, video_mobile_file)
            video_encode_for_web(video_file, video_web_file)
            transcription_service = transcribe.init_transcription_service()
            transcribe_result = transcription_service.transcribe(
                [transcribe.TranscribeJobRequest(sourceFile=audio_file)]
            )
            job_result = transcribe_result.first()
            transcript = job_result.transcript if job_result else ""
            update_status(
                StatusUpdateRequest(
                    mentor=mentor,
                    question=question,
                    task_id=task_id,
                    status="UPLOAD_IN_PROGRESS",
                    transcript=transcript,
                    media=[],
                )
            )
            video_path_base = f"videos/{mentor}/{question}/{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}/"
            media = []
            s3 = _create_s3_client()
            s3_bucket = _require_env("STATIC_AWS_S3_BUCKET")
            for tag, file in [("mobile", video_mobile_file), ("web", video_web_file)]:
                item_path = f"{video_path_base}{tag}.mp4"
                media.append(
                    {
                        "type": "video",
                        "tag": tag,
                        "url": item_path,
                    }
                )
                s3.upload_file(
                    str(file),
                    s3_bucket,
                    item_path,
                    ExtraArgs={"ContentType": "video/mp4"},
                )
            update_status(
                StatusUpdateRequest(
                    mentor=mentor,
                    question=question,
                    task_id=task_id,
                    status="DONE",
                    transcript=transcript,
                    media=media,
                )
            )
            update_answer(
                AnswerUpdateRequest(
                    mentor=mentor, question=question, transcript=transcript, media=media
                )
            )
            static_url_base = environ.get("STATIC_URL_BASE", "")
            return ProcessAnswerResponse(
                **req,
                transcript=transcript,
                media=list(
                    map(
                        lambda m: {
                            k: (v if k != "url" else urljoin(static_url_base, v))
                            for k, v in m.items()
                        },
                        media,
                    )
                ),
            )
        except Exception:
            update_status(
                StatusUpdateRequest(
                    mentor=mentor,
                    question=question,
                    task_id=task_id,
                    status="UPLOAD_FAILED",
                    transcript="",
                    media=[],
                )
            )
        finally:
            try:
                #  We are deleting the uploaded video file from a shared network mount here
                #  We generally do want to clean these up, but maybe should have a flag
                # in the job request like "disable_delete_file_on_complete" (default False)
                remove(video_path_full)
            except Exception as x:
                import logging

                logging.error(
                    f"failed to delete uploaded video file '{video_path_full}'"
                )
                logging.exception(x)
