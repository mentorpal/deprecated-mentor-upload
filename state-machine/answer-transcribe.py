import json
import boto3
import tempfile
import os
import logger
import transcribe
from media_tools import video_to_audio
from api import (
    fetch_question_name,
    upload_task_status_update,
    upload_update_answer,
    AnswerUpdateRequest,
    UpdateTaskStatusRequest,
)


log = logger.get_logger("answer-transcribe-handler")


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
        media = []

    upload_update_answer(
        AnswerUpdateRequest(
            mentor=mentor,
            question=question,
            transcript=transcript,
            media=media,
            has_edited_transcript=False,
        )
    )
    upload_task_status_update(
        UpdateTaskStatusRequest(
            mentor=mentor,
            question=question,
            task_id=task_id,
            new_status="DONE",
            media=media,
        )
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
            s3_path = os.path.dirname(
                request["video"]
            )  # same 'folder' as original file
            log.info("%s downloaded to %s", request["video"], work_dir)

            transcribe_video(
                request["mentor"],
                request["question"],
                task["task_id"],
                work_file,
                s3_path,
            )
