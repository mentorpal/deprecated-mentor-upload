#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
import json
import logging
import uuid
import boto3
import os
import ffmpy
from typing import Tuple, Union
from os import environ, path, makedirs
from flask import Blueprint, jsonify, request
from mentor_upload_api.api import (
    UploadTaskRequest,
    upload_task_update,
)
from mentor_upload_api.blueprints.upload.answer import video_upload_json_schema
from mentor_upload_api.helpers import validate_json_payload_decorator

log = logging.getLogger()
answer_queue_blueprint = Blueprint("answer-queue", __name__)


def _require_env(n: str) -> str:
    env_val = os.environ.get(n, "")
    if not env_val:
        raise EnvironmentError(f"missing required env var {n}")
    return env_val


static_s3_bucket = _require_env("STATIC_AWS_S3_BUCKET")
log.info("using s3 bucket %s", static_s3_bucket)
s3_client = boto3.client(
    "s3",
    region_name=_require_env("STATIC_AWS_REGION"),
    aws_access_key_id=_require_env("STATIC_AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=_require_env("STATIC_AWS_SECRET_ACCESS_KEY"),
)
sns = boto3.client(
    "sns",
    region_name=os.environ.get("STATIC_AWS_REGION"),
    aws_access_key_id=_require_env("STATIC_AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=_require_env("STATIC_AWS_SECRET_ACCESS_KEY"),
)
ssm = boto3.client(
    "ssm",
    region_name=os.environ.get("STATIC_AWS_REGION"),
    aws_access_key_id=_require_env("STATIC_AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=_require_env("STATIC_AWS_SECRET_ACCESS_KEY"),
)


def _to_status_url(root: str, id: str) -> str:
    return f"{request.url_root.replace('http://', 'https://', 1) if (environ.get('STATUS_URL_FORCE_HTTPS') or '').lower() in ('1', 'y', 'true', 'on') and str.startswith(request.url_root,'http://') else request.url_root}/upload/answer/status/{id}"


def get_upload_root() -> str:
    return environ.get("UPLOAD_ROOT") or "./uploads"


def format_secs(secs: Union[float, int, str]) -> str:
    return f"{float(str(secs)):.3f}"


def output_args_trim_video(start_secs: float, end_secs: float) -> Tuple[str, ...]:
    return (
        "-ss",
        format_secs(start_secs),
        "-to",
        format_secs(end_secs),
        "-c:v",
        "libx264",
        "-crf",
        "30",
    )


def video_trim(
    input_file: str, output_file: str, start_secs: float, end_secs: float
) -> None:
    log.info("%s, %s, %s-%s", input_file, output_file, start_secs, end_secs)
    # couldnt get to output to stdout like here
    # https://aws.amazon.com/blogs/media/processing-user-generated-content-using-aws-lambda-and-ffmpeg/
    ff = ffmpy.FFmpeg(
        inputs={str(input_file): None},
        outputs={str(output_file): output_args_trim_video(start_secs, end_secs)},
    )
    ff.run()
    log.debug(ff)


@answer_queue_blueprint.route("/", methods=["POST"])
@answer_queue_blueprint.route("", methods=["POST"])
@validate_json_payload_decorator(video_upload_json_schema)
def upload(body):
    log.info("%s", {"files": request.files, "body": request.form.get("body")})
    # TODO reject request if there's already a job in progress

    # request.form contains the entire video encoded, dont want all that in the logs:
    # req_log.info(request.form(as_text=True)[:300])

    mentor = body.get("mentor")
    question = body.get("question")
    trim = body.get("trim")
    upload_file = request.files["video"]
    root_ext = path.splitext(upload_file.filename)
    file_name = f"{uuid.uuid4()}-{mentor}-{question}{root_ext[1]}"
    file_path = path.join(get_upload_root(), file_name)
    log.info(
        "%s",
        {
            "trim": trim,
            "file": upload_file,
            "ext": root_ext,
            "file_name": file_name,
            "path": file_path,
        },
    )
    makedirs(get_upload_root(), exist_ok=True)
    upload_file.save(file_path)

    if trim:
        log.info("trimming file %s", trim)
        trim_file = f"{file_path}-trim.mp4"
        video_trim(
            file_path,
            trim_file,
            trim["start"],
            trim["end"],
        )
        file_path = trim_file  # from now on work with the trimmed file

    s3_path = f"videos/{mentor}/{question}"
    log.info("uploading %s to %s", file_path, s3_path)
    # to prevent data inconsistency by partial failures (new web.mp3 - old transcript...)
    all_artifacts = ["original.mp4", "web.mp4", "mobile.mp4", "en.vtt"]
    s3_client.delete_objects(
        Bucket=static_s3_bucket,
        Delete={"Objects": [{"Key": f"{s3_path}/{name}"} for name in all_artifacts]},
    )

    s3_client.upload_file(
        file_path,
        static_s3_bucket,
        f"{s3_path}/original.mp4",
        ExtraArgs={"ContentType": "video/mp4"},
    )

    task_list = []
    if trim:
        task_list.append(
            {
                "task_name": "trim_upload",
                "task_id": str(uuid.uuid4()),
                "status": "DONE",
            }
        )

    task_list.append(
        {
            "task_name": "transcoding-web",
            "task_id": str(uuid.uuid4()),
            "status": "QUEUED",
        }
    )
    task_list.append(
        {
            "task_name": "transcoding-mobile",
            "task_id": str(uuid.uuid4()),
            "status": "QUEUED",
        }
    )
    task_list.append(
        {"task_name": "transcribing", "task_id": str(uuid.uuid4()), "status": "QUEUED"}
    )

    req = {
        "request": {
            "mentor": mentor,
            "question": question,
            "video": f"{s3_path}/original.mp4",
            "task_list": task_list,
        }
    }

    arn_param = f"/mentorpal/{os.environ.get('STAGE')}/shared/upload_sns_arn"
    response = ssm.get_parameters(Names=[arn_param], WithDecryption=False)
    log.debug("ssm response %s", response)
    upload_arn = response["Parameters"][0]["Value"]
    log.info("publishing job request to %s", upload_arn)
    # todo test failure if we need to check sns_msg.ResponseMetadata.HTTPStatusCode != 200
    sns_msg = sns.publish(TopicArn=upload_arn, Message=json.dumps(req))
    log.info("sns message published %s", sns_msg["MessageId"])
    # we risk here overriding values, perhaps processing was already done, so status is DONE
    # but this will overwrite and revert them back to QUEUED. Can we just append?
    upload_task_update(
        UploadTaskRequest(
            mentor=mentor,
            question=question,
            task_list=task_list,
            transcript="",
            media=[],
        )
    )
    return jsonify(
        {
            "data": {
                "taskList": task_list,
                # this seems incorrect, passing multiple ids
                "statusUrl": _to_status_url(
                    request.url_root, [t["task_id"] for t in task_list]
                ),
            }
        }
    )
