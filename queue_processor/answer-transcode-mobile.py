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
from media_tools import video_encode_for_mobile
from api import (
    UpdateTaskStatusRequest,
    AnswerUpdateRequest,
    upload_task_status_update,
    upload_answer_and_task_status_update,
    fetch_task,
)


log = logger.get_logger("answer-transcode-mobile-handler")

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


def transcode_mobile(video_file, s3_path):
    work_dir = os.path.dirname(video_file)
    mobile_mp4 = os.path.join(work_dir, "mobile.mp4")

    video_encode_for_mobile(video_file, mobile_mp4)

    log.info("uploading %s to %s/%s", mobile_mp4, s3_bucket, s3_path)
    s3.upload_file(
        mobile_mp4,
        s3_bucket,
        f"{s3_path}/mobile.mp4",
        ExtraArgs={"ContentType": "video/mp4"},
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
    log.info("video to process %s", request["video"])
    stored_task = fetch_from_graphql(request, task)
    if stored_task["status"].startswith("CANCEL"):
        log.info("task cancelled, skipping transcription")
        return

    with tempfile.TemporaryDirectory() as work_dir:
        work_file = os.path.join(work_dir, "original.mp4")
        s3.download_file(s3_bucket, request["video"], work_file)
        s3_path = os.path.dirname(request["video"])  # same 'folder' as original file
        log.info("%s downloaded to %s", request["video"], work_dir)

        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=request["mentor"],
                question=request["question"],
                task_id=task["task_id"],
                new_status="IN_PROGRESS",
            )
        )

        transcode_mobile(work_file, s3_path)

        media = [
            {
                "type": "video",
                "tag": "mobile",
                "url": f"{s3_path}/mobile.mp4",
            }
        ]
        upload_answer_and_task_status_update(
            AnswerUpdateRequest(
                mentor=request["mentor"],
                question=request["question"],
                transcript="",
                media=media,
            ),
            UpdateTaskStatusRequest(
                mentor=request["mentor"],
                question=request["question"],
                task_id=task["task_id"],
                new_status="DONE",
                media=media,
            ),
        )


def handler(event, context):
    log.info(json.dumps(event))
    for record in event["Records"]:
        body = json.loads(str(record["body"]))
        request = json.loads(str(body["Message"]))["request"]
        task_list = request["task_list"]
        task = next(filter(lambda t: t["task_name"] == "transcoding-mobile", task_list))
        if not task:
            log.warning("no transcoding-mobile task requested")
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
