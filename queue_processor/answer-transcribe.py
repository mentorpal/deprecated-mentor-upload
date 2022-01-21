#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved. 
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
import json
import boto3
import tempfile
import os
import logger
import transcribe
from media_tools import video_to_audio
from api import (
    AnswerUpdateRequest,
    UpdateTaskStatusRequest,
    fetch_question_name,
    upload_task_status_update,
    upload_answer_and_task_status_update,
    fetch_task,
)


log = logger.get_logger("answer-transcribe-handler")

if os.environ.get("IS_SENTRY_ENABLED", "") == "true":
    log.info("SENTRY enabled, calling init")
    import sentry_sdk  # NOQA E402
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration  # NOQA E402

    sentry_sdk.init(
        dsn=os.environ.get("SENTRY_DSN_MENTOR_UPLOAD"),
        # include project so issues can be filtered in sentry:
        environment=os.environ.get("PYTHON_ENV", "careerfair-qa"),
        integrations=[AwsLambdaIntegration(timeout_warning=True)],
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        traces_sample_rate=0.20,
        debug=os.environ.get("SENTRY_DEBUG_UPLOADER", "") == "true",
    )


def _require_env(n: str) -> str:
    env_val = os.environ.get(n, "")
    if not env_val:
        raise EnvironmentError(f"missing required env var {n}")
    return env_val


s3_bucket = _require_env("S3_STATIC_ARN").split(":")[-1]
log.info("using s3 bucket %s", s3_bucket)
s3 = boto3.client("s3")


def is_idle_question(question_id: str) -> bool:
    name = fetch_question_name(question_id)
    return name == "_IDLE_"


def transcribe_video(mentor, question, task_id, video_file, s3_path):
    transcript = ""
    subtitles = ""
    audio_file = video_to_audio(video_file)
    log.info("transcribing %s", audio_file)
    transcription_service = transcribe.init_transcription_service()
    transcribe_result = transcription_service.transcribe(
        [transcribe.TranscribeJobRequest(sourceFile=audio_file, generateSubtitles=True)]
    )
    job_result = transcribe_result.first()
    log.info("%s transcribed", audio_file)
    log.debug("%s", job_result)
    transcript = job_result.transcript if job_result else ""
    subtitles = job_result.subtitles if job_result else ""
    media = []
    if subtitles:
        vtt_file = os.path.join(os.path.dirname(video_file), "en.vtt")
        with open(vtt_file, "w") as f:
            f.write(subtitles)
            s3.upload_file(
                vtt_file,
                s3_bucket,
                f"{s3_path}/en.vtt",
                ExtraArgs={"ContentType": "text/vtt"},
            )
        media = [
            {
                "type": "subtitles",
                "tag": "en",
                "url": f"{s3_path}/en.vtt",
            }
        ]

    upload_answer_and_task_status_update(
        AnswerUpdateRequest(
            mentor=mentor,
            question=question,
            transcript=transcript,
            media=media,
            has_edited_transcript=False,
        ),
        UpdateTaskStatusRequest(
            mentor=mentor,
            question=question,
            task_id=task_id,
            new_status="DONE",
            media=media,
        ),
    )


def fetch_from_graphql(request, task):
    upload_task = fetch_task(request["mentor"], request["question"])
    stored_task = next(
        (x for x in upload_task["taskList"] if x["task_id"] == task["task_id"]),
        None,
    )
    if stored_task is None:
        log.error("task it doesnt match %s %s", task, upload_task["taskList"])
        raise Exception(
            "task it doesnt match %s %s",
            task["task_id"],
            [t["task_id"] for t in upload_task["taskList"]],
        )
    return stored_task


def process_task(request, task):
    stored_task = fetch_from_graphql(request, task)
    if stored_task["status"].startswith("CANCEL"):
        log.info("task cancelled, skipping transcription")
        return

    is_idle = is_idle_question(request["question"])
    if is_idle:
        log.info("question is idle, nothing to transcribe")
        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=request["mentor"],
                question=request["question"],
                task_id=task["task_id"],
                new_status="DONE",
            )
        )
        return

    upload_task_status_update(
        UpdateTaskStatusRequest(
            mentor=request["mentor"],
            question=request["question"],
            task_id=task["task_id"],
            new_status="IN_PROGRESS",
        )
    )

    log.info("video to process %s", request["video"])
    with tempfile.TemporaryDirectory() as work_dir:
        work_file = os.path.join(work_dir, "original.mp4")
        s3.download_file(s3_bucket, request["video"], work_file)
        s3_path = os.path.dirname(request["video"])  # same 'folder' as original file
        log.info("%s downloaded to %s", request["video"], work_dir)

        transcribe_video(
            request["mentor"],
            request["question"],
            task["task_id"],
            work_file,
            s3_path,
        )


def handler(event, context):
    log.info(json.dumps(event))
    for record in event["Records"]:
        body = json.loads(str(record["body"]))
        request = json.loads(str(body["Message"]))["request"]
        task_list = request["task_list"]
        task = next(filter(lambda t: t["task_name"] == "transcribing", task_list))
        if not task:
            log.warning("transcribe task not requested")
            return

        try:
            process_task(request, task)
        except Exception as x:
            upload_task_status_update(
                UpdateTaskStatusRequest(
                    mentor=request["mentor"],
                    question=request["question"],
                    task_id=task["task_id"],
                    new_status="FAILED",
                )
            )
            raise x
