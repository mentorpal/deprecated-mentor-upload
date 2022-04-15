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
import urllib.request
import json

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
    ProcessTransferMentor,
    TrimExistingUploadRequest,
    RegenVTTRequest,
)
from .media_tools import (
    video_trim,
    existing_video_trim,
    video_encode_for_mobile,
    video_encode_for_web,
    video_to_audio,
    transcript_to_vtt,
    trim_vtt_and_transcript_via_timestamps,
)
from .api import (
    ImportMentorGQLRequest,
    fetch_answer,
    fetch_question_name,
    import_mentor_gql,
    upload_update_answer,
    update_media,
    AnswerUpdateRequest,
    upload_task_status_update,
    UpdateTaskStatusRequest,
    MediaUpdateRequest,
    fetch_answer_transcript_and_media,
    fetch_text_from_url,
    import_task_update_gql,
    ImportTaskUpdateGQLRequest,
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
    makedirs(media_work_dir)
    video_file = media_work_dir / path.basename(source_path)
    copyfile(source_path, video_file)
    yield (video_file, media_work_dir)


@contextmanager
def _delete_video_work_dir(work_dir: str):
    try:
        rmtree(str(work_dir))
    except Exception as x:
        import logging

        logging.error(f"failed to delete media work dir {work_dir}")
        logging.exception(x)


@contextmanager
def _trimming_work_dir():
    media_work_dir = (
        Path(environ.get("TRANSCODE_WORK_DIR") or mkdtemp()) / _new_work_dir_name()
    )
    try:
        makedirs(media_work_dir)
        yield media_work_dir
    finally:
        try:
            rmtree(str(media_work_dir))
        except Exception as x:
            import logging

            logging.error(f"failed to delete media work dir {media_work_dir}")
            logging.exception(x)


def cancel_task(req: CancelTaskRequest) -> CancelTaskResponse:
    upload_task_status_update(
        UpdateTaskStatusRequest(
            mentor=req.get("mentor"),
            question=req.get("question"),
            task_id=req.get("task_id"),
            new_status="CANCELLING",
        )
    )
    # TODO: potentially need to cancel s3 upload and aws transcribe if they have already started?
    upload_task_status_update(
        UpdateTaskStatusRequest(
            mentor=req.get("mentor"),
            question=req.get("question"),
            task_id=req.get("task_id"),
            new_status="CANCELLED",
        )
    )


def is_idle_question(question_id: str) -> bool:
    name = fetch_question_name(question_id)
    return name == "_IDLE_"


def trim_upload_stage(req: ProcessAnswerRequest, task_id: str):
    trim = req.get("trim", None)
    video_path = req.get("video_path", "")
    if not video_path:
        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=req.get("mentor"),
                question=req.get("question"),
                task_id=task_id,
                new_status="FAILED",
            )
        )
        raise Exception("missing required param 'video_path'")
    video_path_full = upload_path(video_path)
    if not path.isfile(video_path_full):
        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=req.get("mentor"),
                question=req.get("question"),
                task_id=task_id,
                new_status="FAILED",
            )
        )
        raise Exception(f"video not found for path '{video_path}'")
    with _video_work_dir(video_path_full) as context:
        try:
            video_file, work_dir = context
            upload_task_status_update(
                UpdateTaskStatusRequest(
                    mentor=req.get("mentor"),
                    question=req.get("question"),
                    task_id=task_id,
                    new_status="IN_PROGRESS",
                )
            )
            if trim:
                trim_file = work_dir / "trim.mp4"
                video_trim(video_file, trim_file, trim.get("start"), trim.get("end"))
                from shutil import copyfile

                copyfile(trim_file, video_file)
            upload_task_status_update(
                UpdateTaskStatusRequest(
                    mentor=req.get("mentor"),
                    question=req.get("question"),
                    task_id=task_id,
                    new_status="DONE",
                )
            )
            return {"video_file": str(video_file), "work_dir": str(work_dir)}
        except Exception as x:
            import logging

            logging.exception(x)
            _delete_video_work_dir(work_dir)
            upload_task_status_update(
                UpdateTaskStatusRequest(
                    mentor=req.get("mentor"),
                    question=req.get("question"),
                    task_id=task_id,
                    new_status="FAILED",
                )
            )


def extract_params_for_transcode_transcribe_stages(
    dict_tuple: dict, req: ProcessAnswerRequest, task_id: str
):
    params = req
    for dic in dict_tuple:
        if "video_file" in dic:
            params["video_file"] = dic["video_file"]
        if "work_dir" in dic:
            params["work_dir"] = dic["work_dir"]

    if "video_file" not in params:
        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=req.get("mentor"),
                question=req.get("question"),
                task_id=task_id,
                new_status="FAILED",
            )
        )
        raise Exception("missing required param 'video_file'")
    if "work_dir" not in params:
        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=req.get("mentor"),
                question=req.get("question"),
                task_id=task_id,
                new_status="FAILED",
            )
        )
        raise Exception("missing required param 'work_dir'")
    if "video_path" not in params:
        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=req.get("mentor"),
                question=req.get("question"),
                task_id=task_id,
                new_status="FAILED",
            )
        )
        raise Exception("missing required param 'video_path'")
    return params


def transcode_stage(dict_tuple: dict, req: ProcessAnswerRequest, task_id: str):
    params = extract_params_for_transcode_transcribe_stages(dict_tuple, req, task_id)
    try:
        mentor = params.get("mentor")
        question = params.get("question")
        work_dir = Path(params.get("work_dir"))
        video_file = Path(params.get("video_file"))
        MediaUpload = Tuple[  # noqa: N806
            str, str, str, str, str
        ]  # media_type, tag, file_name, content_type, file
        media_uploads: List[MediaUpload] = []
        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=req.get("mentor"),
                question=req.get("question"),
                task_id=task_id,
                new_status="IN_PROGRESS",
            )
        )
        video_mobile_file = work_dir / "mobile.mp4"
        video_encode_for_mobile(video_file, video_mobile_file)
        media_uploads.append(
            ("video", "mobile", "mobile.mp4", "video/mp4", video_mobile_file)
        )
        video_web_file = work_dir / "web.mp4"
        video_encode_for_web(video_file, video_web_file)
        media_uploads.append(("video", "web", "web.mp4", "video/mp4", video_web_file))

        media = []
        s3 = _create_s3_client()
        s3_bucket = _require_env("STATIC_AWS_S3_BUCKET")
        video_path_base = f"videos/{mentor}/{question}/{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}/"
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

        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=req.get("mentor"),
                question=req.get("question"),
                task_id=task_id,
                new_status="DONE",
            )
        )
        return {
            "media": media,
            "video_file": str(video_file),
            "work_dir": str(work_dir),
        }
    except Exception as x:
        import logging

        logging.exception(x)
        _delete_video_work_dir(work_dir)
        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=req.get("mentor"),
                question=req.get("question"),
                task_id=task_id,
                new_status="FAILED",
            )
        )


def transcribe_stage(dict_tuple: dict, req: ProcessAnswerRequest, task_id: str):
    params = extract_params_for_transcode_transcribe_stages(dict_tuple, req, task_id)
    try:
        mentor = params.get("mentor")
        question = params.get("question")
        work_dir = params.get("work_dir")
        video_file = params.get("video_file")
        is_idle = is_idle_question(question)
        audio_file = video_to_audio(video_file)
        transcript = ""
        subtitles = ""
        if not is_idle:
            upload_task_status_update(
                UpdateTaskStatusRequest(
                    mentor=mentor,
                    question=question,
                    task_id=task_id,
                    new_status="IN_PROGRESS",
                )
            )
            transcription_service = transcribe.init_transcription_service()
            transcribe_result = transcription_service.transcribe(
                [
                    transcribe.TranscribeJobRequest(
                        sourceFile=audio_file, generateSubtitles=True
                    )
                ]
            )
            job_result = transcribe_result.first()
            transcript = job_result.transcript if job_result else ""
            subtitles = job_result.subtitles if job_result else ""
        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=mentor,
                question=question,
                task_id=task_id,
                new_status="DONE",
            )
        )
        return {"transcript": transcript, "subtitles": subtitles}
    except Exception as x:
        import logging

        logging.exception(x)
        _delete_video_work_dir(work_dir)
        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=mentor,
                question=question,
                task_id=task_id,
                new_status="FAILED",
            )
        )


def extract_params_for_finalization_stage(
    dict_tuple: dict, req: ProcessAnswerRequest, task_id: str
):
    params = req
    params["media"] = []
    dict_tuple = dict_tuple[0]
    for dic in dict_tuple:
        if "video_path" in dic:
            params["video_path"] = dic["video_path"]
        if "video_web_file_path" in dic:
            params["video_web_file_path"] = dic["video_web_file_path"]
        if "transcript" in dic:
            params["transcript"] = dic["transcript"]
        if "subtitles" in dic:
            params["subtitles"] = dic["subtitles"]
        if "media" in dic:
            for media in dic["media"]:
                params["media"].append(media)
        if "work_dir" in dic:
            params["work_dir"] = dic["work_dir"]

    if "media" not in params:
        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=req.get("mentor"),
                question=req.get("question"),
                task_id=task_id,
                new_status="FAILED",
            )
        )
        raise Exception("Missing media param in finalization stage")

    if "transcript" not in params:
        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=req.get("mentor"),
                question=req.get("question"),
                task_id=task_id,
                new_status="FAILED",
            )
        )
        raise Exception("Missing transcript param in finalization stage")
    if "video_path" not in params:
        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=req.get("mentor"),
                question=req.get("question"),
                task_id=task_id,
                new_status="FAILED",
            )
        )
        raise Exception("Missing video_path param in finalization stage")
    return params


def get_video_and_vtt_file_paths(work_dir: str):
    video_web_file = work_dir / "web.mp4"
    vtt_file = work_dir / "subtitles.vtt"
    return video_web_file, vtt_file


def finalization_stage(dict_tuple: dict, req: ProcessAnswerRequest, task_id: str):
    params = extract_params_for_finalization_stage(dict_tuple, req, task_id)
    mentor = params.get("mentor")
    question = params.get("question")
    work_dir = Path(params.get("work_dir"))
    try:
        video_path_full = upload_path(params["video_path"])
        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=req.get("mentor"),
                question=req.get("question"),
                task_id=task_id,
                new_status="IN_PROGRESS",
            )
        )
        media_uploads = []
        media = params["media"]
        transcript = params["transcript"] or ""
        subtitles = params["subtitles"] or ""
        if subtitles:
            try:
                video_web_file, vtt_file = get_video_and_vtt_file_paths(work_dir)
                makedirs(path.dirname(vtt_file), exist_ok=True)
                with open(vtt_file, "w") as f:
                    f.write(subtitles)
                media_uploads.append(
                    ("subtitles", "en", "en.vtt", "text/vtt", vtt_file)
                )
            except Exception as vtt_err:
                import logging

                logging.error(f"Failed to create vtt file at {vtt_file}")
                logging.exception(vtt_err)

        if media_uploads:
            s3 = _create_s3_client()
            s3_bucket = _require_env("STATIC_AWS_S3_BUCKET")
            video_path_base = f"videos/{mentor}/{question}/{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}/"
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
                transcript=transcript,
                media=media,
            )
        )
        return ProcessAnswerResponse(**params)
    except Exception as x:
        import logging

        logging.exception(x)
        _delete_video_work_dir(work_dir)
        upload_task_status_update(
            UpdateTaskStatusRequest(
                mentor=req.get("mentor"),
                question=req.get("question"),
                task_id=task_id,
                new_status="FAILED",
            )
        )
    finally:
        try:
            #  We are deleting the uploaded video file from a shared network mount here
            #  We generally do want to clean these up, but maybe should have a flag
            # in the job request like "disable_delete_file_on_complete" (default False)
            _delete_video_work_dir(work_dir)
            remove(video_path_full)
        except Exception as x:
            import logging

            logging.error(f"failed to delete uploaded video file '{video_path_full}'")
            logging.exception(x)


def trim_existing_upload(req: TrimExistingUploadRequest, task_id: str):
    with _trimming_work_dir() as context:
        try:
            work_dir = context
            mentor = req.get("mentor")
            question = req.get("question")
            trim = req.get("trim")
            (
                transcript,
                answer_media,
                has_edited_transcript,
            ) = fetch_answer_transcript_and_media(mentor, question)
            upload_task_status_update(
                UpdateTaskStatusRequest(
                    mentor=mentor,
                    question=question,
                    task_id=task_id,
                    new_status="IN_PROGRESS",
                    transcript=transcript,
                    media=answer_media,
                )
            )
            web_media = next((x for x in answer_media if x["tag"] == "web"), None)
            mobile_media = next((x for x in answer_media if x["tag"] == "mobile"), None)
            if web_media is None or mobile_media is None:
                raise Exception(
                    f"failed to find video urls for mentor: {mentor} and question: {question}"
                )
            web_video_url = web_media["url"]
            mobile_video_url = mobile_media["url"]
            web_trim_file = work_dir / "web_trim.mp4"
            mobile_trim_file = work_dir / "mobile_trim.mp4"
            existing_video_trim(
                web_video_url, web_trim_file, trim.get("start"), trim.get("end")
            )
            existing_video_trim(
                mobile_video_url, mobile_trim_file, trim.get("start"), trim.get("end")
            )
            media_uploads = []
            new_media = []
            media_uploads.append(
                ("video", "web", "web.mp4", "video/mp4", web_trim_file)
            )
            media_uploads.append(
                ("video", "mobile", "mobile.mp4", "video/mp4", mobile_trim_file)
            )

            vtt_media = next(
                (x for x in answer_media if x["type"] == "subtitles"), None
            )
            if vtt_media and not has_edited_transcript:
                vtt_str = fetch_text_from_url(vtt_media["url"])
                video_web_file, vtt_file = get_video_and_vtt_file_paths(work_dir)
                makedirs(path.dirname(vtt_file), exist_ok=True)
                with open(vtt_file, "w") as f:
                    f.write(vtt_str)
                new_vtt_str, new_transcript = trim_vtt_and_transcript_via_timestamps(
                    vtt_file, trim.get("start"), trim.get("end")
                )
                transcript = new_transcript
                media_uploads.append(
                    ("subtitles", "en", "en.vtt", "text/vtt", vtt_file)
                )
            else:
                new_media.append(vtt_media)

            if media_uploads:
                s3 = _create_s3_client()
                s3_bucket = _require_env("STATIC_AWS_S3_BUCKET")
                video_path_base = f"videos/{mentor}/{question}/{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}/"
                for media_type, tag, file_name, content_type, file in media_uploads:
                    if path.isfile(file):
                        item_path = f"{video_path_base}{file_name}"
                        new_media.append(
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

            upload_update_answer(
                AnswerUpdateRequest(
                    mentor=mentor,
                    question=question,
                    transcript=transcript,
                    media=new_media,
                )
            )
            upload_task_status_update(
                UpdateTaskStatusRequest(
                    mentor=mentor,
                    question=question,
                    task_id=task_id,
                    new_status="DONE",
                    transcript=transcript,
                    media=new_media,
                )
            )
            return {"trim_existing_upload": True}
        except Exception as x:
            import logging

            upload_task_status_update(
                UpdateTaskStatusRequest(
                    mentor=mentor,
                    question=question,
                    task_id=task_id,
                    new_status="FAILED",
                    transcript=transcript,
                    media=answer_media,
                )
            )

            logging.error("failed to trim video")
            logging.exception(x)


def regen_vtt(req: RegenVTTRequest):
    with _trimming_work_dir() as context:
        try:
            work_dir = context
            mentor = req.get("mentor")
            question = req.get("question")
            video_file, vtt_file = get_video_and_vtt_file_paths(work_dir)
            (
                transcript,
                answer_media,
                has_edited_transcript,
            ) = fetch_answer_transcript_and_media(mentor, question)
            web_media = next((x for x in answer_media if x["tag"] == "web"), None)
            mobile_media = next((x for x in answer_media if x["tag"] == "mobile"), None)
            if not web_media or not mobile_media:
                raise Exception(
                    f"failed to find answer media for mentor: {mentor} and question: {question}"
                )
            transcript_to_vtt(web_media["url"], vtt_file, transcript)
            media_uploads = [("subtitles", "en", "en.vtt", "text/vtt", vtt_file)]
            new_media = []
            s3 = _create_s3_client()
            s3_bucket = _require_env("STATIC_AWS_S3_BUCKET")
            video_path_base = f"videos/{mentor}/{question}/{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}/"
            for media_type, tag, file_name, content_type, file in media_uploads:
                if path.isfile(file):
                    item_path = f"{video_path_base}{file_name}"
                    new_media.append(
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
            update_media(
                MediaUpdateRequest(mentor=mentor, question=question, media=new_media[0])
            )
            return {"regen_vtt": True}
        except Exception as x:
            import logging

            logging.error(
                f"failed to regenerate vtt for mentor {mentor} and question {question}"
            )
            logging.exception(x)
            return {"regen_vtt": False}


def process_transfer_video(req: ProcessTransferRequest, task_id: str):
    import logging

    mentor = req.get("mentor")
    question = req.get("question")
    answer = fetch_answer(mentor, question)
    transcript = answer.get("transcript", "")
    media = answer.get("media", [])
    if not answer.get("hasUntransferredMedia", False):
        return
    upload_task_status_update(
        UpdateTaskStatusRequest(
            mentor=mentor,
            question=question,
            task_id=task_id,
            new_status="IN_PROGRESS",
            transcript=transcript,
            media=media,
        )
    )
    for m in media:
        if m.get("needsTransfer", False):
            typ = m.get("type", "")
            tag = m.get("tag", "")
            root_ext = "vtt" if typ == "subtitles" else "mp4"
            try:
                file_path, headers = urllib.request.urlretrieve(m.get("url", ""))
                item_path = f"videos/{mentor}/{question}/{tag}.{root_ext}"
                s3 = _create_s3_client()
                s3_bucket = _require_env("STATIC_AWS_S3_BUCKET")
                content_type = "text/vtt" if typ == "subtitles" else "video/mp4"
                s3.upload_file(
                    file_path,
                    s3_bucket,
                    item_path,
                    ExtraArgs={"ContentType": content_type},
                )
                logging.error("Succesfully uploaded")
                m["needsTransfer"] = False
                m["url"] = item_path

                upload_task_status_update(
                    UpdateTaskStatusRequest(
                        mentor=mentor,
                        question=question,
                        task_id=task_id,
                        new_status="DONE",
                        transcript=transcript,
                        media=media,
                    )
                )
                update_media(
                    MediaUpdateRequest(mentor=mentor, question=question, media=m)
                )
                logging.error("sucessfully updated GQL")
            except Exception as x:
                logging.error(f"Failed to upload video to s3 {x}")

                logging.exception(x)
                upload_task_status_update(
                    UpdateTaskStatusRequest(
                        mentor=mentor,
                        question=question,
                        task_id=task_id,
                        new_status="FAILED",
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


def process_transfer_mentor(req: ProcessTransferMentor, task_id: str):
    import logging

    logging.error("starting transfer process")
    logging.error("req:")
    mentor = req.get("mentor")
    mentor_export_json = req.get("mentorExportJson")
    replaced_mentor_data_changes = req.get("replacedMentorDataChanges")
    logging.error(json.dumps(req))
    graphql_update = {"status": "IN_PROGRESS"}
    import_task_update_gql(
        ImportTaskUpdateGQLRequest(mentor=mentor, graphql_update=graphql_update)
    )
    logging.error("created import task")
    try:
        mentor_import_res = import_mentor_gql(
            ImportMentorGQLRequest(
                mentor, mentor_export_json, replaced_mentor_data_changes
            )
        )
    except Exception as e:
        logging.error("Failed to import mentor")
        logging.error(e)
    logging.error(mentor_import_res)
    graphql_update = {"status": "DONE"}
    import_task_update_gql(
        ImportTaskUpdateGQLRequest(mentor=mentor, graphql_update=graphql_update)
    )

    answers = mentor_import_res["answers"]
    answers_with_media_transfers = list(
        filter(
            lambda a: len(a["media"] or []) > 0,
            answers,
        )
    )
    answer_media_migrations = [
        {"question": q["_id"], "status": "QUEUED"}
        for q in list(map(lambda a: a["question"], answers_with_media_transfers))
    ]
    s3_video_migration = {
        "status": "IN_PROGRESS",
        "answerMediaMigrations": answer_media_migrations,
    }
    import_task_update_gql(
        ImportTaskUpdateGQLRequest(mentor=mentor, s3_video_migration=s3_video_migration)
    )

    for answer in answers_with_media_transfers:
        try:
            question = answer["question"]["_id"]
            logging.error(f"starting media transfer for question {question}")
            for m in answer["media"]:
                if m.get("needsTransfer", False):
                    typ = m.get("type", "")
                    tag = m.get("tag", "")
                    root_ext = "vtt" if typ == "subtitles" else "mp4"
                    try:
                        file_path, headers = urllib.request.urlretrieve(
                            m.get("url", "")
                        )
                        item_path = f"videos/{mentor}/{question}/{tag}.{root_ext}"
                        logging.error(f"uploading to {item_path}")
                        s3 = _create_s3_client()
                        s3_bucket = _require_env("STATIC_AWS_S3_BUCKET")
                        content_type = "text/vtt" if typ == "subtitles" else "video/mp4"
                        s3.upload_file(
                            file_path,
                            s3_bucket,
                            item_path,
                            ExtraArgs={"ContentType": content_type},
                        )
                        logging.error("Succesfully uploaded")
                        m["needsTransfer"] = False
                        m["url"] = item_path
                        update_media(
                            MediaUpdateRequest(
                                mentor=mentor, question=question, media=m
                            )
                        )
                        answer_media_migrate_update = {
                            "question": question,
                            "status": "DONE",
                        }
                        import_task_update_gql(
                            ImportTaskUpdateGQLRequest(
                                mentor=mentor,
                                answerMediaMigrateUpdate=answer_media_migrate_update,
                            )
                        )

                        logging.error("sucessfully updated GQL")
                    except Exception as x:
                        media_url = m.get("url", "")
                        logging.error(f"Failed to upload video {media_url} to s3 {x}")
                        logging.exception(x)
                        raise x
                    finally:
                        try:
                            remove(file_path)
                        except Exception as x:
                            import logging

                            logging.error(f"failed to delete file '{file_path}'")
                            logging.exception(x)
                else:
                    answer_media_migrate_update = {
                        "question": question,
                        "status": "DONE",
                    }
                    import_task_update_gql(
                        ImportTaskUpdateGQLRequest(
                            mentor=mentor,
                            answerMediaMigrateUpdate=answer_media_migrate_update,
                        )
                    )
        except Exception as e:
            logging.error(
                f"Failed to process media for answer with question {question}"
            )
            logging.exception(e)
            import_task_update_gql(
                ImportTaskUpdateGQLRequest(
                    mentor=mentor,
                    answerMediaMigrateUpdate={
                        "question": question,
                        "status": "FAILED",
                        "errorMessage": str(e),
                    },
                )
            )
    logging.error(f"Finished importing mentor {mentor}")
