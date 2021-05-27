#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from contextlib import contextmanager
import json
from os import path, makedirs
import re
from shutil import copyfile
from typing import List, Tuple
from unittest.mock import call, patch, Mock

from callee.operators import Contains
import pytest
import responses
import transcribe
from transcribe.mock import MockTranscribeJob, MockTranscriptions

from mentor_upload_process.api import (
    answer_update_gql,
    get_graphql_endpoint,
    AnswerUpdateRequest,
)
import mentor_upload_process.process
from .utils import fixture_upload, mock_s3_client

TEST_STATIC_AWS_S3_BUCKET = "mentorpal-origin"
TEST_STATIC_URL_BASE = "http://static-somedomain.mentorpal.org"


@contextmanager
def _test_env(video_file: str, monkeypatch, tmpdir):
    patcher = patch("mentor_upload_process.process._new_work_dir_name")
    try:
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
        mock_new_work_dir_name = patcher.start()
        mock_new_work_dir_name.return_value = "test"
        yield transcode_work_dir / "test"
    finally:
        patcher.stop()


def _expect_gql_answer_update(expected_gql_query: dict) -> None:
    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == get_graphql_endpoint()
    assert responses.calls[0].request.body.decode("UTF-8") == json.dumps(
        expected_gql_query
    )


def _expect_transcode_calls(
    video_path: str, mock_ffmpeg_cls: Mock
) -> Tuple[str, str, str]:
    """
    There are currently 3 transcode calls that need to happen in the upload process:

     - convert the uploaded video to an audio file (for transcription)
     - convert the uploaded video to a web-optimized video
     - convert the uploaded video to a mobile-optimized video
    """
    expected_audio_path = re.sub("mp4$", "mp3", video_path)
    expected_mobile_video_path = path.join(path.split(video_path)[0], "mobile.mp4")
    expected_web_video_path = path.join(path.split(video_path)[0], "web.mp4")
    mock_ffmpeg_cls.assert_has_calls(
        [
            call(
                inputs={video_path: None},
                outputs={expected_audio_path: "-loglevel quiet -y"},
            ),
            call().run(),
            call(
                inputs={video_path: None},
                outputs={expected_mobile_video_path: Contains("libx264")},
            ),
            call().run(),
            call(
                inputs={video_path: None},
                outputs={expected_web_video_path: Contains("libx264")},
            ),
            call().run(),
        ],
    )
    return expected_audio_path, expected_web_video_path, expected_mobile_video_path


def _mock_gql_answer_update(
    mentor: str, question: str, transcript: str
) -> Tuple[dict, List[dict]]:
    base_path = f"videos/{mentor}/{question}/"
    media = [
        {"type": "video", "tag": "mobile", "url": f"{base_path}mobile.mp4"},
        {"type": "video", "tag": "web", "url": f"{base_path}web.mp4"},
    ]
    gql_query = answer_update_gql(
        AnswerUpdateRequest(
            mentor=mentor, question=question, transcript=transcript, media=media
        )
    )
    responses.add(
        responses.POST,
        get_graphql_endpoint(),
        json=answer_update_gql(
            AnswerUpdateRequest(
                mentor=mentor,
                question=question,
                transcript=transcript,
                media=media,
            )
        ),
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


@pytest.mark.only
@responses.activate
@patch.object(transcribe, "init_transcription_service")
@patch("ffmpy.FFmpeg")
@patch("boto3.client")
def test_transcribes_mentor_answer(
    mock_boto3_client: Mock,
    mock_ffmpeg_cls: Mock,
    mock_init_transcription_service: Mock,
    monkeypatch,
    tmpdir,
):
    video_path = "video1.mp4"
    with _test_env(video_path, monkeypatch, tmpdir) as work_dir:
        mentor = "m1"
        question = "q1"
        fake_transcript = "mentor answer for question 1"
        req = {"mentor": mentor, "question": question, "video_path": video_path}
        mock_ffmpeg_inst = Mock()
        mock_ffmpeg_cls.return_value = mock_ffmpeg_inst
        mock_transcriptions = MockTranscriptions(mock_init_transcription_service, ".")
        mock_transcriptions.mock_transcribe_result(
            [
                MockTranscribeJob(
                    batch_id="b1",
                    request=transcribe.TranscribeJobRequest(
                        sourceFile=re.sub("mp4$", "mp3", video_path)
                    ),
                    transcript=fake_transcript,
                )
            ]
        )
        expected_gql_query, expected_media = _mock_gql_answer_update(
            mentor, question, fake_transcript
        )
        mock_s3 = mock_s3_client(mock_boto3_client)
        assert mentor_upload_process.process.process_answer_video(req) == {
            "mentor": mentor,
            "question": question,
            "video_path": video_path,
            "transcript": fake_transcript,
            "media": expected_media,
        }
        (
            _,
            expected_web_video_path,
            expected_mobile_video_path,
        ) = _expect_transcode_calls(str(work_dir / video_path), mock_ffmpeg_cls)
        _expect_gql_answer_update(expected_gql_query)
        expected_upload_file_calls = [
            call(
                expected_mobile_video_path,
                TEST_STATIC_AWS_S3_BUCKET,
                f"videos/{mentor}/{question}/mobile.mp4",
            ),
            call(
                expected_web_video_path,
                TEST_STATIC_AWS_S3_BUCKET,
                f"videos/{mentor}/{question}/web.mp4",
            ),
        ]
        mock_s3.upload_file.assert_has_calls(expected_upload_file_calls)


def test_raises_if_video_path_not_specified():
    req = {"mentor": "m1", "question": "q1"}
    caught_exception = None
    try:
        mentor_upload_process.process.process_answer_video(req)
    except Exception as err:
        caught_exception = err
    assert caught_exception is not None
    assert str(caught_exception) == "missing required param 'video_path'"


def test_raises_if_video_not_found_for_path():
    req = {"mentor": "m1", "question": "q1", "video_path": "not_exists.mp4"}
    caught_exception = None
    try:
        mentor_upload_process.process.process_answer_video(req)
    except Exception as err:
        caught_exception = err
    assert caught_exception is not None
    assert str(caught_exception) == "video not found for path 'not_exists.mp4'"
