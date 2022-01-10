import json
import boto3
import tempfile
import os
import logger
import transcribe

from media_tools import (
    video_trim,
    video_encode_for_mobile,
    video_encode_for_web,
    video_to_audio,
)
from api import (
    fetch_question_name,
)

log = logger.get_logger("answer-handler")


def _require_env(n: str) -> str:
    env_val = os.environ.get(n, "")
    if not env_val:
        raise EnvironmentError(f"missing required env var {n}")
    return env_val


s3_bucket = _require_env("S3_STATIC_ARN").split(":")[-1]
log.info("using s3 bucket %s", s3_bucket)
s3 = boto3.client("s3")


def transcode_stage(video_file, s3_path):
    work_dir = os.path.dirname(video_file)
    mobile_mp4 = os.path.join(work_dir, "mobile.mp4")
    video_encode_for_mobile(video_file, mobile_mp4)

    log.debug("uploading %s to %s", mobile_mp4, s3_bucket)
    s3.upload_file(
        mobile_mp4,
        s3_bucket,
        f"{s3_path}/mobile.mp4",
        ExtraArgs={"ContentType": "video/mp4"},
    )

    web_mp4 = os.path.join(work_dir, "web.mp4")
    video_encode_for_web(video_file, web_mp4)

    log.debug("uploading %s to %s", web_mp4, s3_bucket)
    s3.upload_file(
        web_mp4,
        s3_bucket,
        f"{s3_path}/web.mp4",
        ExtraArgs={"ContentType": "video/mp4"},
    )


def is_idle_question(question_id: str) -> bool:
    name = fetch_question_name(question_id)
    return name == "_IDLE_"


def transcribe_stage(question, video_file, s3_path):
    is_idle = is_idle_question(question)
    audio_file = video_to_audio(video_file)
    transcript = ""
    subtitles = ""
    if not is_idle:
        log.info("transcribing %s", audio_file)
        transcription_service = transcribe.init_transcription_service()
        transcribe_result = transcription_service.transcribe(
            [
                transcribe.TranscribeJobRequest(
                    sourceFile=audio_file, generateSubtitles=True
                )
            ]
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
        payload = record["body"]
        request = json.loads(str(payload))["request"]
        log.info("video to process %s", request["video"])
        with tempfile.TemporaryDirectory() as work_dir:
            work_file = os.path.join(work_dir, "original.mp4")
            s3.download_file(s3_bucket, request["video"], work_file)
            s3_path = os.path.dirname(
                request["video"]
            )  # same 'folder' as original file
            log.debug("%s downloaded to %s", request["video"], work_dir)

            if "trim" in request:
                trim_file = os.path.join(work_dir, "trim.mp4")
                video_trim(
                    work_file,
                    trim_file,
                    request["trim"]["start"],
                    request["trim"]["end"],
                )
                work_file = trim_file  # from now on work with the trimmed file

            transcode_stage(work_file, s3_path)
            transcribe_stage(request["video"], work_file, s3_path)

            # TODO notify graphql


# TODO dlq
# TODO alerting and monitoring

# if __name__ == "__main__":
#     with open('./answer.event.json.dist','r') as f:
#         e = json.loads(f.read())
#         handler(e,{})
