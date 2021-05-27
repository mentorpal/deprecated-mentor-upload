#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from os import environ, path

import boto3
from boto3_type_annotations.s3 import Client as S3Client
import transcribe

from . import ProcessAnswerRequest, ProcessAnswerResponse
from .media_tools import video_encode_for_mobile, video_encode_for_web, video_to_audio
from .api import update_answer, AnswerUpdateRequest


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


def process_answer_video(req: ProcessAnswerRequest) -> ProcessAnswerResponse:
    video_path = req.get("video_path", "")
    if not video_path:
        raise Exception("missing required param 'video_path'")
    video_path_full = upload_path(video_path)
    if not path.isfile(video_path_full):
        raise Exception(f"video not found for path '{video_path}'")
    audio_file = video_to_audio(video_path_full)
    video_mobile_file = path.join(path.split(video_path_full)[0], "mobile.mp4")
    video_web_file = path.join(path.split(video_path_full)[0], "web.mp4")
    video_encode_for_mobile(video_path_full, video_mobile_file)
    video_encode_for_web(video_path_full, video_web_file)
    transcription_service = transcribe.init_transcription_service()
    mentor = req.get("mentor")
    question = req.get("question")
    transcribe_result = transcription_service.transcribe(
        [transcribe.TranscribeJobRequest(sourceFile=audio_file)]
    )
    job_result = transcribe_result.first()
    transcript = job_result.transcript if job_result else ""
    video_path_base = f"videos/{mentor}/{question}/"
    media = []
    s3 = _create_s3_client()
    s3_bucket = _require_env("STATIC_UPLOAD_AWS_S3_BUCKET")
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
            file,
            s3_bucket,
            item_path,
        )
    update_answer(
        AnswerUpdateRequest(
            mentor=mentor, question=question, transcript=transcript, media=media
        )
    )
    return ProcessAnswerResponse(**req, transcript=transcript, media=media)
