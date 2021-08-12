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
from typing import List, Tuple
from urllib.parse import urljoin
import urllib.request


import boto3
from boto3_type_annotations.s3 import Client as S3Client
import transcribe
import uuid

from . import (
    CancelTaskRequest,
    CancelTaskResponse,
    ProcessAnswerRequest,
    ProcessAnswerResponse,
    ProcessTransferRequest,
)
from .media_tools import (
    video_trim,
    video_encode_for_mobile,
    video_encode_for_web,
    video_to_audio,
    transcript_to_vtt,
)
from .api import (
    fetch_answer,
    fetch_question_name,
    update_answer,
    update_status,
    update_media,
    AnswerUpdateRequest,
    StatusUpdateRequest,
    MediaUpdateRequest,
)


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


def is_idle_question(question_id: str) -> bool:
    name = fetch_question_name(question_id)
    return name == "_IDLE_"


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
            is_idle = is_idle_question(question)
            video_file, work_dir = context
            if trim:
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
                video_trim(video_file, trim_file, trim.get("start"), trim.get("end"))
                from shutil import copyfile

                copyfile(trim_file, video_file)
            MediaUpload = Tuple[  # noqa: N806
                str, str, str, str, str
            ]  # media_type, tag, file_name, content_type, file
            media_uploads: List[MediaUpload] = []
            audio_file = video_to_audio(video_file)
            video_mobile_file = work_dir / "mobile.mp4"
            video_encode_for_mobile(video_file, video_mobile_file)
            media_uploads.append(
                ("video", "mobile", "mobile.mp4", "video/mp4", video_mobile_file)
            )
            video_web_file = work_dir / "web.mp4"
            video_encode_for_web(video_file, video_web_file)
            media_uploads.append(
                ("video", "web", "web.mp4", "video/mp4", video_web_file)
            )
            transcript = ""
            if not is_idle:
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
                transcription_service = transcribe.init_transcription_service()
                transcribe_result = transcription_service.transcribe(
                    [transcribe.TranscribeJobRequest(sourceFile=audio_file)]
                )
                job_result = transcribe_result.first()
                transcript = job_result.transcript if job_result else ""
                if transcript:
                    try:
                        vtt_file = work_dir / "subtitles.vtt"
                        transcript_to_vtt(audio_file, vtt_file, transcript)
                        media_uploads.append(
                            ("subtitles", "en", "en.vtt", "text/vtt", vtt_file)
                        )
                    except Exception as vtt_err:
                        import logging

                        logging.error(f"Failed to create vtt file at {vtt_file}")
                        logging.exception(vtt_err)
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
            for media_type, tag, file_name, content_type, file in media_uploads:
                if path.isfile(file):
                    item_path = f"{video_path_base}{file_name}"
                    media.append(
                        {
                            "type": media_type,
                            "tag": tag,
                            "url": item_path,
                        }
                    )
                    s3.upload_file(
                        str(file),
                        s3_bucket,
                        item_path,
                        ExtraArgs={"ContentType": content_type},
                    )
                else:
                    import logging

                    logging.error(f"Failed to find file at {file}")
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
        except Exception as x:
            import logging

            logging.exception(x)
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


def process_transfer_video(req: ProcessTransferRequest, task_id: str):
    mentor = req.get("mentor")
    question = req.get("question")
    answer = fetch_answer(mentor, question)
    transcript = answer.get("transcript", "")
    media = answer.get("media", [])
    if not answer.get("hasUntransferredMedia", False):
        return
    update_status(
        StatusUpdateRequest(
            mentor=mentor,
            question=question,
            task_id=task_id,
            status="TRANSFER_IN_PROGRESS",
            transcript=transcript,
            media=media,
        )
    )
    for m in media:
        if m.get("needsTransfer", False):
            typ = m.get("type", "")
            tag = m.get("tag", "")
            root_ext = "vtt" if typ == "subtitles" else "mp4"
            file_path, headers = urllib.request.urlretrieve(m.get("url", ""))
            try:
                item_path = f"videos/{mentor}/{question}/{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}/{tag}.{root_ext}"
                s3 = _create_s3_client()
                s3_bucket = _require_env("STATIC_AWS_S3_BUCKET")
                content_type = "text/vtt" if typ == "subtitles" else "video/mp4"
                s3.upload_file(
                    file_path,
                    s3_bucket,
                    item_path,
                    ExtraArgs={"ContentType": content_type},
                )
                m["needsTransfer"] = False
                m["url"] = item_path
                update_status(
                    StatusUpdateRequest(
                        mentor=mentor,
                        question=question,
                        task_id=task_id,
                        status="TRANSFER_IN_PROGRESS",
                        transcript=transcript,
                        media=media,
                    )
                )
                update_media(
                    MediaUpdateRequest(mentor=mentor, question=question, media=m)
                )
            except Exception as x:
                import logging

                logging.exception(x)
                update_status(
                    StatusUpdateRequest(
                        mentor=mentor,
                        question=question,
                        task_id=task_id,
                        status="TRANSFER_FAILED",
                        transcript=transcript,
                        media=media,
                    )
                )
            finally:
                try:
                    remove(file_path)
                except Exception as x:
                    import logging

                    logging.error(f"failed to delete file '{file_path}'")
                    logging.exception(x)
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
