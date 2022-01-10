import json
import boto3
import tempfile
import os
import logger
import transcribe
from media_tools import video_to_audio
from api import fetch_question_name


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


def transcribe_video(video_file, s3_path):
    transcript = ""
    subtitles = ""
    audio_file = video_to_audio(video_file)
    log.info("transcribing %s", audio_file)
    transcription_service = transcribe.init_transcription_service(
        os.environ["TRANSCRIBE_MODULE_PATH"],
        {
            # must provide these explicitly because lambdas have AWS_ACCESS_KEY_ID from their own account
            "AWS_REGION": os.environ["TRANSCRIBE_AWS_REGION"],
            "AWS_ACCESS_KEY_ID": os.environ["TRANSCRIBE_AWS_ACCESS_KEY_ID"],
            "AWS_SECRET_ACCESS_KEY": os.environ["TRANSCRIBE_AWS_SECRET_ACCESS_KEY"],
        },
    )
    transcribe_result = transcription_service.transcribe(
        [transcribe.TranscribeJobRequest(sourceFile=audio_file, generateSubtitles=True)]
    )
    job_result = transcribe_result.first()
    log.info("%s transcribed", audio_file)
    log.debug("%s", job_result)
    transcript = job_result.transcript if job_result else ""
    subtitles = job_result.subtitles if job_result else ""

    if subtitles:
        vtt_file = os.path.join(os.path.dirname(video_file), "en.vtt")
        with open(vtt_file, "w") as f:
            f.write(subtitles)
            # ("subtitles", "en", "en.vtt", "text/vtt", vtt_file)
            s3.upload_file(
                vtt_file,
                s3_bucket,
                f"{s3_path}/en.vtt",
                ExtraArgs={"ContentType": "text/vtt"},
            )
    # TODO
    # upload_update_answer(
    #     AnswerUpdateRequest(
    #         mentor=mentor,
    #         question=question,
    #         transcript=transcript,
    #         media=media,
    #         has_edited_transcript=False,
    #     )
    # )


def handler(event, context):
    log.info(json.dumps(event))
    for record in event["Records"]:
        body = json.loads(str(record["body"]))
        request = json.loads(str(body["Message"]))["request"]
        is_idle = is_idle_question(request["question"])

        if is_idle:
            log.info("question is idle, nothing to transcribe")
            return

        log.info("video to process %s", request["video"])
        with tempfile.TemporaryDirectory() as work_dir:
            work_file = os.path.join(work_dir, "original.mp4")
            s3.download_file(s3_bucket, request["video"], work_file)
            s3_path = os.path.dirname(
                request["video"]
            )  # same 'folder' as original file
            log.info("%s downloaded to %s", request["video"], work_dir)

            transcribe_video(work_file, s3_path)

            # TODO notify graphql
