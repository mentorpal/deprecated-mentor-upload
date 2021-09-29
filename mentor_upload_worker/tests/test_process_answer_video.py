#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from contextlib import contextmanager
from dataclasses import dataclass
import json
from os import path, makedirs
from pathlib import Path
import re
from shutil import copyfile
from typing import Dict, List, Tuple
from unittest.mock import call, patch, Mock

from freezegun import freeze_time
import pytest
import responses
import transcribe
from transcribe.mock import MockTranscribeJob, MockTranscriptions

from mentor_upload_process import TrimRequest
from mentor_upload_process.api import (
    answer_update_gql,
    status_update_gql,
    fetch_question_name_gql,
    get_graphql_endpoint,
    AnswerUpdateRequest,
    StatusUpdateRequest,
)
from mentor_upload_process.media_tools import (
    output_args_trim_video,
    output_args_video_encode_for_mobile,
    output_args_video_encode_for_web,
    output_args_video_to_audio,
)
from .utils import fixture_upload, mock_s3_client

TEST_STATIC_AWS_S3_BUCKET = "mentorpal-origin"
TEST_STATIC_URL_BASE = "http://static-somedomain.mentorpal.org"


@contextmanager
def _test_env(
    video_file: str, timestamp: str, video_dims: Tuple[int, int], monkeypatch, tmpdir
):
    patcher_find_video_dims = patch("mentor_upload_process.media_tools.find_video_dims")
    patcher_new_work_dir_name = patch(
        "mentor_upload_process.process._new_work_dir_name"
    )
    freezer = freeze_time(timestamp)
    try:
        freezer.start()
        uploads_path = tmpdir / "uploads"
        makedirs(uploads_path)
        copyfile(fixture_upload(video_file), uploads_path / video_file)
        monkeypatch.setenv("UPLOADS", str(uploads_path))
        monkeypatch.setenv("STATIC_AWS_S3_BUCKET", TEST_STATIC_AWS_S3_BUCKET)
        monkeypatch.setenv("STATIC_AWS_REGION", "us-east-10000")
        monkeypatch.setenv("STATIC_AWS_ACCESS_KEY_ID", "fake-access-key-id")
        monkeypatch.setenv("STATIC_AWS_SECRET_ACCESS_KEY", "fake-access-key-secret")
        monkeypatch.setenv("STATIC_AWS_SECRET_ACCESS_KEY", "fake-access-key-secret")
        monkeypatch.setenv("STATIC_URL_BASE", TEST_STATIC_URL_BASE)
        transcode_work_dir = tmpdir / "workdir"
        monkeypatch.setenv("TRANSCODE_WORK_DIR", str(transcode_work_dir))
        mock_new_work_dir_name = patcher_new_work_dir_name.start()
        mock_new_work_dir_name.return_value = "test"
        mock_find_video_dims = patcher_find_video_dims.start()
        mock_find_video_dims.return_value = video_dims
        yield transcode_work_dir / "test"
    finally:
        patcher_new_work_dir_name.stop()
        patcher_find_video_dims.stop()
        freezer.stop()


def _mock_gql_answer_update(
    mentor: str, question: str, transcript: str, timestamp: str, media=None
) -> Tuple[dict, List[dict]]:
    base_path = f"videos/{mentor}/{question}/{timestamp}/"
    if media is None:
        media = [
            {"type": "video", "tag": "mobile", "url": f"{base_path}mobile.mp4"},
            {"type": "video", "tag": "web", "url": f"{base_path}web.mp4"},
        ]
        if question != "q1_idle":
            media.append(
                {"type": "subtitles", "tag": "en", "url": f"{base_path}en.vtt"},
            )
    gql_query = answer_update_gql(
        AnswerUpdateRequest(
            mentor=mentor, question=question, transcript=transcript, media=media
        )
    )
    responses.add(
        responses.POST,
        get_graphql_endpoint(),
        json=gql_query,
        status=200,
    )
    return gql_query, list(
        map(
            lambda m: {
                k: (v if k != "url" else f"{TEST_STATIC_URL_BASE}/{v}")
                for k, v in m.items()
            },
            media,
        )
    )


def _transcode_expected_media(
    mentor: str, question: str, timestamp: str, media=None
) -> Tuple[dict, List[dict]]:
    base_path = f"videos/{mentor}/{question}/{timestamp}/"
    if media is None:
        media = [
            {"type": "video", "tag": "mobile", "url": f"{base_path}mobile.mp4"},
            {"type": "video", "tag": "web", "url": f"{base_path}web.mp4"},
        ]
    return list(
        map(
            lambda m: {k: (v) for k, v in m.items()},
            media,
        )
    )


def _mock_gql_status_update(
    mentor: str,
    question: str,
    task_id: str,
    transferring_flag: str = None,
    upload_flag: str = None,
    transcribing_flag: str = None,
    transcoding_flag: str = None,
    finalization_flag: str = None,
    transcript: str = None,
    timestamp: str = None,
    media=None,
) -> dict:
    if media is None and timestamp is not None:
        media = []
        base_path = f"videos/{mentor}/{question}/{timestamp}/"
        media = [
            {"type": "video", "tag": "mobile", "url": f"{base_path}mobile.mp4"},
            {"type": "video", "tag": "web", "url": f"{base_path}web.mp4"},
        ]
        if question != "q1_idle":
            media.append(
                {"type": "subtitles", "tag": "en", "url": f"{base_path}en.vtt"}
            )
    gql_query = status_update_gql(
        StatusUpdateRequest(
            mentor=mentor,
            question=question,
            task_id=task_id,
            upload_flag=upload_flag,
            transcribing_flag=transcribing_flag,
            transcoding_flag=transcoding_flag,
            finalization_flag=finalization_flag,
            transcript=transcript,
            media=media,
        )
    )
    responses.add(
        responses.POST,
        get_graphql_endpoint(),
        json=gql_query,
        status=200,
    )
    return gql_query


def _mock_is_idle_question_(question_id: str) -> dict:
    gql_query = fetch_question_name_gql(question_id)
    responses.add(
        responses.POST,
        get_graphql_endpoint(),
        json={"data": {"question": {"name": "_IDLE_"}}}
        if question_id == "q1_idle"
        else {"data": {"question": {"name": ""}}},
        status=200,
    )
    return gql_query


def _expect_gql(expected_gql_queries: List[dict]) -> None:
    assert len(responses.calls) == len(expected_gql_queries)
    for i, query in enumerate(expected_gql_queries):
        assert responses.calls[i].request.url == get_graphql_endpoint()
        assert responses.calls[i].request.body.decode("UTF-8") == json.dumps(query)


def _transcode_stage_expect_transcode_calls(
    video_path: str,
    mock_ffmpeg_cls: Mock,
    video_dims: Tuple[int, int],
) -> Tuple[str, str, str, str, str]:
    """
    There are currently 2 transcode calls that need to happen in the transcode stage:
     - convert the uploaded video to a web-optimized video
     - convert the uploaded video to a mobile-optimized video
    """
    expected_mobile_video_path = path.join(path.split(video_path)[0], "mobile.mp4")
    expected_web_video_path = path.join(path.split(video_path)[0], "web.mp4")
    mock_ffmpeg_cls.assert_has_calls(
        [
            call(
                inputs={video_path: None},
                outputs={
                    expected_mobile_video_path: output_args_video_encode_for_mobile(
                        video_path, video_dims=video_dims
                    )
                },
            ),
            call(
                inputs={video_path: None},
                outputs={
                    expected_web_video_path: output_args_video_encode_for_web(
                        video_path, video_dims=video_dims
                    )
                },
            ),
        ],
    )
    return (
        expected_web_video_path,
        expected_mobile_video_path,
    )


def _transcribe_stage_expect_transcode_calls(
    video_path: str,
    mock_ffmpeg_cls: Mock,
) -> Tuple[str, str, str, str, str]:
    """
    There is currently 1 transcode call that need to happen in the transcribe process:
     - convert the uploaded video to an audio file (for transcription)
    """
    expected_audio_path = re.sub("mp4$", "mp3", video_path)
    mock_ffmpeg_cls.assert_has_calls(
        [
            call(
                inputs={video_path: None},
                outputs={expected_audio_path: output_args_video_to_audio()},
            ),
        ],
    )
    return expected_audio_path


def _expect_transcode_calls(
    video_path: str,
    mock_ffmpeg_cls: Mock,
    video_dims: Tuple[int, int],
    trim: Dict[str, int] = {},
) -> Tuple[str, str, str, str, str]:
    """
    There are currently 3 transcode calls that need to happen in the upload process:

     - convert the uploaded video to an audio file (for transcription)
     - convert the uploaded video to a web-optimized video
     - convert the uploaded video to a mobile-optimized video
    """
    expected_audio_path = re.sub("mp4$", "mp3", video_path)
    expected_vtt_path = path.join(path.split(video_path)[0], "subtitles.vtt")
    expected_trim_path = (
        path.join(path.split(video_path)[0], "trim.mp4") if trim else ""
    )
    expected_mobile_video_path = path.join(path.split(video_path)[0], "mobile.mp4")
    expected_web_video_path = path.join(path.split(video_path)[0], "web.mp4")
    expected_trim_path = path.join(path.split(video_path)[0], "trim.mp4")
    mock_ffmpeg_cls.assert_has_calls(
        (
            [
                call(
                    inputs={video_path: None},
                    outputs={
                        expected_trim_path: output_args_trim_video(
                            trim.get("start", 0), trim.get("end", 0)
                        )
                    },
                ),
            ]
            if trim
            else []
        )
        + [
            call(
                inputs={video_path: None},
                outputs={
                    expected_mobile_video_path: output_args_video_encode_for_mobile(
                        video_path, video_dims=video_dims
                    )
                },
            ),
            call(
                inputs={video_path: None},
                outputs={
                    expected_web_video_path: output_args_video_encode_for_web(
                        video_path, video_dims=video_dims
                    )
                },
            ),
            call(
                inputs={video_path: None},
                outputs={expected_audio_path: output_args_video_to_audio()},
            ),
        ],
    )
    return (
        expected_audio_path,
        expected_vtt_path,
        expected_trim_path,
        expected_web_video_path,
        expected_mobile_video_path,
    )


@dataclass
class _TestProcessExample:
    mentor: str
    question: str
    timestamp: str
    transcript_fake: str
    trim: TrimRequest
    video_dims: Tuple[int, int]
    video_name: str
    video_duration_fake: float


@responses.activate
@patch("ffmpy.FFmpeg")
@pytest.mark.parametrize(
    "ex",
    [
        (
            _TestProcessExample(
                mentor="m1",
                question="q1",
                timestamp="20120114T032134Z",
                transcript_fake="mentor answer for question 1",
                trim=None,
                video_dims=(400, 400),
                video_name="video1.mp4",
                video_duration_fake=13.5,
            )
        ),
        (
            _TestProcessExample(
                mentor="m1",
                question="q1",
                timestamp="20120114T032134Z",
                transcript_fake="mentor answer for question 1",
                trim={"start": 0.0, "end": 5.0},
                video_dims=(1280, 720),
                video_name="video1.mp4",
                video_duration_fake=13.5,
            )
        ),
        (
            _TestProcessExample(
                mentor="m1",
                question="q1",
                timestamp="20120114T032134Z",
                transcript_fake="mentor answer for question 1",
                trim={"start": 5.3, "end": 8.921},
                video_dims=(480, 640),
                video_name="video1.mp4",
                video_duration_fake=13.5,
            )
        ),
        (
            _TestProcessExample(
                mentor="m1",
                question="q1_idle",
                timestamp="20120114T032134Z",
                transcript_fake="",
                trim={"start": 5.3, "end": 8.921},
                video_dims=(480, 640),
                video_name="video1.mp4",
                video_duration_fake=13.5,
            )
        ),
    ],
)
def test_init_stage(
    mock_ffmpeg_cls: Mock,
    monkeypatch,
    tmpdir,
    ex: _TestProcessExample,
):
    with _test_env(ex.video_name, ex.timestamp, ex.video_dims, monkeypatch, tmpdir):
        req = {
            "mentor": ex.mentor,
            "question": ex.question,
            "trim": ex.trim,
            "video_path": ex.video_name,
        }
        mock_ffmpeg_inst = Mock()

        def mock_ffmpeg_constructor(inputs: dict, outputs: dict) -> Mock:
            """
            when FFMpeg constructor is called,
            we need to capture the target 'output' file
            and create a fake output there
            """
            if outputs:
                output_file = list(outputs.keys())[0]
                Path(output_file).write_text("fake output")
            return mock_ffmpeg_inst

        mock_ffmpeg_cls.side_effect = mock_ffmpeg_constructor

        expected_gql = [
            _mock_gql_status_update(
                req["mentor"],
                req["question"],
                "fake_task_id",
                upload_flag="IN_PROGRESS",
            ),
            _mock_gql_status_update(
                req["mentor"],
                req["question"],
                "fake_task_id",
                upload_flag="DONE",
            ),
        ]

        from mentor_upload_process.process import (
            init_stage,
        )

        init_stage(req, "fake_task_id")

        _expect_gql(expected_gql)


@responses.activate
@patch.object(transcribe, "init_transcription_service")
@patch("ffmpy.FFmpeg")
@pytest.mark.parametrize(
    "ex",
    [
        (
            _TestProcessExample(
                mentor="m1",
                question="q1",
                timestamp="20120114T032134Z",
                transcript_fake="mentor answer for question 1",
                trim=None,
                video_dims=(400, 400),
                video_name="video1.mp4",
                video_duration_fake=13.5,
            )
        ),
        (
            _TestProcessExample(
                mentor="m1",
                question="q1",
                timestamp="20120114T032134Z",
                transcript_fake="mentor answer for question 1",
                trim={"start": 0.0, "end": 5.0},
                video_dims=(1280, 720),
                video_name="video1.mp4",
                video_duration_fake=13.5,
            )
        ),
        (
            _TestProcessExample(
                mentor="m1",
                question="q1",
                timestamp="20120114T032134Z",
                transcript_fake="mentor answer for question 1",
                trim={"start": 5.3, "end": 8.921},
                video_dims=(480, 640),
                video_name="video1.mp4",
                video_duration_fake=13.5,
            )
        ),
        (
            _TestProcessExample(
                mentor="m1",
                question="q1_idle",
                timestamp="20120114T032134Z",
                transcript_fake="",
                trim={"start": 5.3, "end": 8.921},
                video_dims=(480, 640),
                video_name="video1.mp4",
                video_duration_fake=13.5,
            )
        ),
    ],
)
def test_transcribing_stage(
    mock_ffmpeg_cls: Mock,
    mock_init_transcription_service: Mock,
    monkeypatch,
    tmpdir,
    ex: _TestProcessExample,
):
    with _test_env(
        ex.video_name, ex.timestamp, ex.video_dims, monkeypatch, tmpdir
    ) as work_dir:
        req = {
            "mentor": ex.mentor,
            "question": ex.question,
            "trim": ex.trim,
            "video_path": ex.video_name,
        }
        is_idle = req["question"] == "q1_idle"
        mock_ffmpeg_inst = Mock()

        def mock_ffmpeg_constructor(inputs: dict, outputs: dict) -> Mock:
            """
            when FFMpeg constructor is called,
            we need to capture the target 'output' file
            and create a fake output there
            """
            if outputs:
                output_file = list(outputs.keys())[0]
                Path(output_file).write_text("fake output")
            return mock_ffmpeg_inst

        mock_ffmpeg_cls.side_effect = mock_ffmpeg_constructor
        mock_transcriptions = MockTranscriptions(mock_init_transcription_service, ".")
        mock_transcriptions.mock_transcribe_result(
            [
                MockTranscribeJob(
                    batch_id="b1",
                    request=transcribe.TranscribeJobRequest(
                        sourceFile=re.sub("mp4$", "mp3", ex.video_name)
                    ),
                    transcript=ex.transcript_fake,
                )
            ]
        )
        expected_is_idle_question_gql_query = _mock_is_idle_question_(ex.question)

        expected_gql = [expected_is_idle_question_gql_query]

        if not is_idle:
            expected_gql.append(
                _mock_gql_status_update(
                    ex.mentor,
                    ex.question,
                    "fake_task_id",
                    transcribing_flag="IN_PROGRESS",
                ),
            )

        expected_gql.append(
            _mock_gql_status_update(
                req["mentor"],
                req["question"],
                "fake_task_id",
                transcribing_flag="DONE",
            ),
        )

        from mentor_upload_process.process import transcribe_stage

        assert transcribe_stage(req, "fake_task_id") == {
            "transcript": ex.transcript_fake,
        }

        if not is_idle:
            _transcribe_stage_expect_transcode_calls(
                str(work_dir / ex.video_name), mock_ffmpeg_cls
            )

        _expect_gql(expected_gql)


@responses.activate
@patch("mentor_upload_process.process.get_video_and_vtt_file_paths")
@patch("boto3.client")
@patch("mentor_upload_process.process.transcript_to_vtt")
@pytest.mark.parametrize(
    "ex",
    [
        (
            _TestProcessExample(
                mentor="m1",
                question="q1",
                timestamp="20120114T032134Z",
                transcript_fake="mentor answer for question 1",
                trim=None,
                video_dims=(400, 400),
                video_name="video1.mp4",
                video_duration_fake=13.5,
            )
        ),
        (
            _TestProcessExample(
                mentor="m1",
                question="q1_idle",
                timestamp="20120114T032134Z",
                transcript_fake="",
                trim={"start": 5.3, "end": 8.921},
                video_dims=(480, 640),
                video_name="video1.mp4",
                video_duration_fake=13.5,
            )
        ),
    ],
)
def test_finalization_stage(
    mock_transcript_to_vtt: Mock,
    mock_boto3_client: Mock,
    mock_get_video_and_vtt_file: Mock,
    monkeypatch,
    tmpdir,
    ex: _TestProcessExample,
):
    with _test_env(
        ex.video_name,
        ex.timestamp,
        ex.video_dims,
        monkeypatch,
        tmpdir,
    ):
        mock_s3 = mock_s3_client(mock_boto3_client)
        # Since transcoding step did not run in this given context, we need to manually create the file that it would have created for finalization
        vtt_file = tmpdir / "subtitles.vtt"
        makedirs(path.dirname(vtt_file), exist_ok=True)
        with open(vtt_file, "x") as f:
            f.write("vtt_str")

        mock_get_video_and_vtt_file.return_value = ("", vtt_file)
        req = {"mentor": ex.mentor, "question": ex.question}
        mentor = req["mentor"]
        question = req["question"]
        task_id = "t1"
        timestamp = ex.timestamp
        is_idle = question == "q1_idle"
        transcode_stage_output_dict = {
            "media": [
                {"type": "video", "tag": "mobile", "url": "mobile.mp4"},
                {"type": "video", "tag": "web", "url": "web.mp4"},
            ],
            "video_path": ex.video_name,
        }

        transcribe_stage_output_dict = {
            "transcript": ex.transcript_fake,
        }

        expected_media = list(transcode_stage_output_dict["media"])

        base_path = f"videos/{mentor}/{question}/{timestamp}/"
        if not is_idle:
            expected_media.append(
                {"type": "subtitles", "tag": "en", "url": f"{base_path}en.vtt"}
            )

        expected_update_answer_gql_query, expected_med = _mock_gql_answer_update(
            mentor,
            question,
            transcribe_stage_output_dict["transcript"],
            timestamp,
            media=expected_media,
        )

        from mentor_upload_process.process import finalization_stage

        assert finalization_stage(
            [(transcode_stage_output_dict, transcribe_stage_output_dict)], req, task_id
        ) == {
            "mentor": req["mentor"],
            "question": req["question"],
            "video_path": "video1.mp4",
            "transcript": transcribe_stage_output_dict["transcript"],
            "media": expected_media,
        }

        _expect_gql(
            [
                _mock_gql_status_update(
                    req["mentor"],
                    req["question"],
                    task_id,
                    finalization_flag="IN_PROGRESS",
                ),
                expected_update_answer_gql_query,
                _mock_gql_status_update(
                    req["mentor"],
                    req["question"],
                    task_id,
                    finalization_flag="DONE",
                    transcript=transcribe_stage_output_dict["transcript"],
                    media=expected_media,
                    timestamp=timestamp,
                ),
            ]
        )

        if not is_idle:
            expected_vtt_path = vtt_file
            expected_upload_file_call = (
                call(
                    expected_vtt_path,
                    TEST_STATIC_AWS_S3_BUCKET,
                    f"videos/{mentor}/{question}/{timestamp}/en.vtt",
                    ExtraArgs={"ContentType": "text/vtt"},
                ),
            )

            mock_s3.upload_file.assert_has_calls(expected_upload_file_call)


@responses.activate
@patch("ffmpy.FFmpeg")
@patch("boto3.client")
@pytest.mark.parametrize(
    "ex",
    [
        (
            _TestProcessExample(
                mentor="m1",
                question="q1",
                timestamp="20120114T032134Z",
                transcript_fake="mentor answer for question 1",
                trim=None,
                video_dims=(400, 400),
                video_name="video1.mp4",
                video_duration_fake=13.5,
            )
        ),
    ],
)
def test_transcode_stage(
    mock_boto3_client: Mock,
    mock_ffmpeg_cls: Mock,
    monkeypatch,
    tmpdir,
    ex: _TestProcessExample,
):
    with _test_env(
        ex.video_name, ex.timestamp, ex.video_dims, monkeypatch, tmpdir
    ) as work_dir:
        req = {
            "mentor": "m1",
            "question": "q1",
            "video_path": "video1.mp4",
            "trim": None,
        }
        task_id = "t1"
        timestamp = "20120114T032134Z"

        mock_ffmpeg_inst = Mock()

        def mock_ffmpeg_constructor(inputs: dict, outputs: dict) -> Mock:
            """
            when FFMpeg constructor is called,
            we need to capture the target 'output' file
            and create a fake output there
            """
            if outputs:
                output_file = list(outputs.keys())[0]
                Path(output_file).write_text("fake output")
            return mock_ffmpeg_inst

        mock_ffmpeg_cls.side_effect = mock_ffmpeg_constructor
        mock_s3 = mock_s3_client(mock_boto3_client)
        from mentor_upload_process.process import transcode_stage

        expected_gql = [
            _mock_gql_status_update(
                "m1",
                "q1",
                task_id,
                transcoding_flag="IN_PROGRESS",
            ),
            _mock_gql_status_update(
                "m1",
                "q1",
                task_id,
                transcoding_flag="DONE",
            ),
        ]

        expected_media = _transcode_expected_media("m1", "q1", timestamp)

        assert transcode_stage(req, task_id) == {
            "media": expected_media,
            "video_path": req["video_path"],
        }
        (
            expected_web_video_path,
            expected_mobile_video_path,
        ) = _transcode_stage_expect_transcode_calls(
            str(work_dir / ex.video_name),
            mock_ffmpeg_cls,
            video_dims=ex.video_dims,
        )
        _expect_gql(expected_gql)

        expected_upload_file_calls = [
            call(
                expected_mobile_video_path,
                TEST_STATIC_AWS_S3_BUCKET,
                f"videos/{ex.mentor}/{ex.question}/{ex.timestamp}/mobile.mp4",
                ExtraArgs={"ContentType": "video/mp4"},
            ),
            call(
                expected_web_video_path,
                TEST_STATIC_AWS_S3_BUCKET,
                f"videos/{ex.mentor}/{ex.question}/{ex.timestamp}/web.mp4",
                ExtraArgs={"ContentType": "video/mp4"},
            ),
        ]

        mock_s3.upload_file.assert_has_calls(expected_upload_file_calls)


@responses.activate
def test_raises_if_video_path_not_specified():
    req = {"mentor": "m1", "question": "q1"}
    caught_exception = None
    expected_gql = [
        _mock_gql_status_update(
            "m1",
            "q1",
            "fake_task_id",
            upload_flag="FAILED",
        ),
        _mock_gql_status_update(
            "m1",
            "q1",
            "fake_task_id",
            transcoding_flag="FAILED",
        ),
        _mock_gql_status_update(
            "m1",
            "q1",
            "fake_task_id",
            transcribing_flag="FAILED",
        ),
    ]
    from mentor_upload_process.process import (
        init_stage,
        transcode_stage,
        transcribe_stage,
    )

    try:
        init_stage(req, "fake_task_id")
        _expect_gql(expected_gql)

    except Exception as err:
        caught_exception = err
    assert caught_exception is not None
    assert str(caught_exception) == "missing required param 'video_path'"

    try:
        transcode_stage(req, "fake_task_id")

    except Exception as err:
        caught_exception = err
    assert caught_exception is not None
    assert str(caught_exception) == "missing required param 'video_path'"

    try:
        transcribe_stage(req, "fake_task_id")

    except Exception as err:
        caught_exception = err
    assert caught_exception is not None
    assert str(caught_exception) == "missing required param 'video_path'"


@responses.activate
def test_raises_if_video_not_found_for_path():
    req = {"mentor": "m1", "question": "q1", "video_path": "not_exists.mp4"}
    caught_exception = None
    expected_gql = [
        _mock_gql_status_update(
            "m1",
            "q1",
            "fake_task_id",
            upload_flag="FAILED",
        ),
        _mock_gql_status_update(
            "m1",
            "q1",
            "fake_task_id",
            transcoding_flag="FAILED",
        ),
        _mock_gql_status_update(
            "m1",
            "q1",
            "fake_task_id",
            transcribing_flag="FAILED",
        ),
    ]
    from mentor_upload_process.process import (
        init_stage,
        transcode_stage,
        transcribe_stage,
    )

    try:

        init_stage(req, "fake_task_id")
        _expect_gql(expected_gql)

    except Exception as err:
        caught_exception = err
    assert caught_exception is not None
    assert str(caught_exception) == "video not found for path 'not_exists.mp4'"

    try:

        transcode_stage(req, "fake_task_id")

    except Exception as err:
        caught_exception = err
    assert caught_exception is not None
    assert str(caught_exception) == "video not found for path 'not_exists.mp4'"

    try:

        transcribe_stage(req, "fake_task_id")

    except Exception as err:
        caught_exception = err
    assert caught_exception is not None
    assert str(caught_exception) == "video not found for path 'not_exists.mp4'"
