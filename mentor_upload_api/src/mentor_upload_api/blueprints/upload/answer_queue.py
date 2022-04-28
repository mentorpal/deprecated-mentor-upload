#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from datetime import datetime
import tempfile
from dateutil import tz
import json
import logging
import uuid
import boto3
import os
import ffmpy
from typing import Tuple, Union
from os import environ, path, makedirs, remove, scandir
from flask import Blueprint, jsonify, request, send_from_directory
from mentor_upload_api.api import (
    AnswerUpdateRequest,
    FetchUploadTaskReq,
    UploadTaskRequest,
    is_upload_in_progress,
    upload_answer_and_task_update,
    fetch_answer_transcript_and_media,
)
from mentor_upload_api.blueprints.upload.answer import video_upload_json_schema
from mentor_upload_api.helpers import (
    validate_form_payload_decorator,
    validate_json_payload_decorator,
    ValidateFormJsonBody,
)
from mentor_upload_api.authorization_decorator import (
    authorize_to_manage_content,
    authorize_to_edit_mentor,
)
from pymediainfo import MediaInfo
from werkzeug.exceptions import BadRequest
from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired
from flask_wtf.file import FileRequired, FileAllowed, FileField

from mentor_upload_api.media_tools import transcript_to_vtt

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


def submit_job(req):
    arn_param = f"/mentorpal/{os.environ.get('STAGE')}/shared/upload_sns_arn"
    response = ssm.get_parameters(Names=[arn_param], WithDecryption=False)
    log.debug("ssm response %s", response)
    upload_arn = response["Parameters"][0]["Value"]
    log.info("publishing job request to %s", upload_arn)
    # todo test failure if we need to check sns_msg.ResponseMetadata.HTTPStatusCode != 200
    sns_msg = sns.publish(TopicArn=upload_arn, Message=json.dumps(req))
    log.info("sns message published %s", json.dumps(sns_msg))


def create_task_list(trim, has_edited_transcript):
    transcode_web_task = {
        "task_name": "transcoding-web",
        "task_id": str(uuid.uuid4()),
        "status": "QUEUED",
    }
    transcode_mobile_task = {
        "task_name": "transcoding-mobile",
        "task_id": str(uuid.uuid4()),
        "status": "QUEUED",
    }
    transcribe_task = (
        {
            "task_name": "transcribing",
            "task_id": str(uuid.uuid4()),
            "status": "QUEUED",
        }
        if not has_edited_transcript
        else None
    )
    trim_upload_task = (
        {
            "task_name": "trim-upload",
            "task_id": str(uuid.uuid4()),
            "status": "QUEUED",
        }
        if trim
        else None
    )

    return transcode_web_task, transcode_mobile_task, transcribe_task, trim_upload_task


def upload_to_s3(file_path, s3_path):
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


def verify_no_upload_in_progress(mentor, question):
    upload_in_progress = is_upload_in_progress(FetchUploadTaskReq(mentor, question))
    if upload_in_progress:
        raise BadRequest("There is an upload already in progress, please wait.")


# Flask-WTF form: defines schema for multipart/form-data request
class UploadVideoFormSchema(FlaskForm):
    body = StringField(
        "body",
        [DataRequired(), ValidateFormJsonBody(json_schema=video_upload_json_schema)],
    )
    video = FileField(
        "video",
        [
            FileRequired(),
            FileAllowed(["mp3", "mp4"], "mp3 or mp4 file format required."),
        ],
    )


@answer_queue_blueprint.route("/", methods=["POST"])
@answer_queue_blueprint.route("", methods=["POST"])
@validate_form_payload_decorator(UploadVideoFormSchema)
def upload(body):
    log.info("%s", {"files": request.files, "body": request.form.get("body")})

    # request.form contains the entire video encoded, dont want all that in the logs:
    # req_log.info(request.form(as_text=True)[:300])

    mentor = body.get("mentor")
    question = body.get("question")
    has_edited_transcript = body.get("hasEditedTranscript")
    verify_no_upload_in_progress(mentor, question)
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
    minfo = MediaInfo.parse(file_path)
    if len(minfo.video_tracks) == 0:
        raise BadRequest("No video tracks found!")
    try:
        if minfo.video_tracks[0].duration < 1000:  # 1sec
            raise BadRequest("Video too short!")
    except Exception as e:
        log.info(f"Failed to check video duration: {e}")

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
    upload_to_s3(file_path, s3_path)

    (
        transcode_web_task,
        transcode_mobile_task,
        transcribe_task,
        trim_upload_task,
    ) = create_task_list(trim, has_edited_transcript)

    req = {
        "request": {
            "mentor": mentor,
            "question": question,
            "video": f"{s3_path}/original.mp4",
            "transcodeWebTask": transcode_web_task,
            "transcodeMobileTask": transcode_mobile_task,
            "trimUploadTask": trim_upload_task,
            "transcribeTask": transcribe_task,
        }
    }

    original_video_url = get_original_video_url(mentor, question)
    # we risk here overriding values, perhaps processing was already done, so status is DONE
    # but this will overwrite and revert them back to QUEUED. Can we just append?
    upload_answer_and_task_update(
        AnswerUpdateRequest(mentor=mentor, question=question, transcript=""),
        UploadTaskRequest(
            mentor=mentor,
            question=question,
            transcode_web_task=transcode_web_task,
            transcode_mobile_task=transcode_mobile_task,
            trim_upload_task=trim_upload_task,
            transcribe_task=transcribe_task,
            transcript="",
            original_media={
                "type": "video",
                "tag": "original",
                "url": original_video_url,
            },
        ),
    )
    submit_job(req)

    return jsonify(
        {
            "data": {
                "transcodeWebTask": transcode_web_task,
                "transcodeMobileTask": transcode_mobile_task,
                "transcribeTask": transcribe_task,
                "trimUploadTask": trim_upload_task,
                "statusUrl": _to_status_url(request.url_root, str(uuid.uuid4())),
            }
        }
    )


def get_original_video_url(mentor: str, question: str) -> str:
    base_url = os.environ.get("STATIC_URL_BASE", "")
    return f"{base_url}/videos/{mentor}/{question}/original.mp4"


def list_files_from_directory(file_directory: str):
    files = []
    cali_tz = tz.gettz("America/Los_Angeles")
    for entry in scandir(file_directory):
        files.append(
            {
                "fileName": entry.name,
                "size": entry.stat().st_size,
                "uploadDate": datetime.fromtimestamp(
                    entry.stat().st_ctime, tz=cali_tz
                ).strftime("%m/%d/%Y %I:%M:%S %p")
                + " (PST)",
            }
        )
    return files


@answer_queue_blueprint.route("/mounted_files/", methods=["GET"])
@answer_queue_blueprint.route("/mounted_files", methods=["GET"])
@authorize_to_manage_content
def mounted_files():
    try:
        file_directory = get_upload_root()
        files = list_files_from_directory(file_directory)
        return {
            "data": {
                "mountedFiles": files,
            }
        }
    except Exception as x:
        logging.error("failed to fetch files from upload directory")
        logging.exception(x)


@answer_queue_blueprint.route("/remove_mounted_file/<file_name>/", methods=["POST"])
@answer_queue_blueprint.route("/remove_mounted_file/<file_name>", methods=["POST"])
@authorize_to_manage_content
def remove_mounted_file(file_name: str):
    try:
        file_path = path.join(get_upload_root(), file_name)
        remove(file_path)
        return {"data": {"fileRemoved": True}}
    except Exception as x:
        logging.error(f"failed to remove file {file_name} from uploads directory")
        logging.exception(x)
        return {"data": {"fileRemoved": False}}


@answer_queue_blueprint.route("/download_mounted_file/<file_name>/", methods=["GET"])
@answer_queue_blueprint.route("/download_mounted_file/<file_name>", methods=["GET"])
@authorize_to_manage_content
def download_mounted_file(file_name: str):
    try:
        file_directory = get_upload_root()
        return send_from_directory(file_directory, file_name, as_attachment=True)
    except Exception as x:
        logging.error(
            f"failed to find video file {file_name} in folder {file_directory}"
        )
        logging.exception(x)


regen_vtt_json_schema = {
    "type": "object",
    "properties": {
        "mentor": {"type": "string", "maxLength": 60, "minLength": 5},
        "question": {"type": "string", "maxLength": 60, "minLength": 5},
    },
    "required": ["mentor", "question"],
    "additionalProperties": False,
}


@answer_queue_blueprint.route("/regen_vtt/", methods=["POST"])
@answer_queue_blueprint.route("/regen_vtt", methods=["POST"])
@validate_json_payload_decorator(json_schema=regen_vtt_json_schema)
@authorize_to_edit_mentor
def regen_vtt(body):
    mentor = body.get("mentor")
    question = body.get("question")
    result = _regen_vtt(mentor, question)
    return jsonify({"data": result})


def _regen_vtt(mentor: str, question: str):
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            vtt_file_path = os.path.join(tmp_dir, "en.vtt")
            (
                transcript,
                answer_media,
            ) = fetch_answer_transcript_and_media(mentor, question)
            web_media = next((x for x in answer_media if x["tag"] == "web"), None)
            if not web_media:
                logging.info(
                    f"no answer media for mentor: {mentor} and question: {question}"
                )
                return {"regen_vtt": False}
            transcript_to_vtt(web_media["url"], vtt_file_path, transcript)
            video_path_base = f"videos/{mentor}/{question}/"
            if path.isfile(vtt_file_path):
                item_path = f"{video_path_base}en.vtt"
                s3_client.upload_file(
                    str(vtt_file_path),
                    static_s3_bucket,
                    item_path,
                    ExtraArgs={"ContentType": "text/vtt"},
                )
            else:
                raise Exception(f"Failed to find vtt file at {vtt_file_path}")
            return {"regen_vtt": True}
        except Exception as x:

            logging.info(
                f"failed to regenerate vtt for mentor {mentor} and question {question}"
            )
            logging.exception(x)
            return {"regen_vtt": False}
