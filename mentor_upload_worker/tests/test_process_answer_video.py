#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
import json
import re
from unittest.mock import patch, Mock

import pytest
import responses
import transcribe
from transcribe.mock import MockTranscribeJob, MockTranscriptions

from mentor_upload_process.api import (
    answer_update_gql,
    get_graphql_endpoint,
    AnswerUpdateRequest,
)
from mentor_upload_process.process import process_answer_video
from .utils import fixture_upload


@pytest.fixture()
def uploads_fixture(monkeypatch) -> str:
    uploads_path = fixture_upload("")
    monkeypatch.setenv("UPLOADS", uploads_path)
    return uploads_path


@responses.activate
@patch.object(transcribe, "init_transcription_service")
@patch("ffmpy.FFmpeg")
def test_transcribes_mentor_answer(
    mock_ffmpeg_cls: Mock, mock_init_transcription_service: Mock, uploads_fixture: str
):
    mentor = "m1"
    question = "q1"
    fake_transcript = "mentor answer for question 1"
    video_path = "video1.mp4"
    media = [{"type": "video", "tag": "web", "url": video_path}]
    req = {"mentor": mentor, "question": question, "video_path": video_path}
    expected_res = {
        "mentor": mentor,
        "question": question,
        "video_path": video_path,
        "transcript": fake_transcript,
        "media": media,
    }
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
    responses.add(
        responses.POST,
        get_graphql_endpoint(),
        json=answer_update_gql(
            AnswerUpdateRequest(
                mentor=mentor,
                question=question,
                transcript=fake_transcript,
                media=media,
            )
        ),
        status=200,
    )
    assert process_answer_video(req) == expected_res
    video_path = fixture_upload(req.get("video_path", ""))
    expected_audio_path = re.sub("mp4$", "mp3", video_path)
    mock_ffmpeg_cls.assert_called_once_with(
        inputs={video_path: None},
        outputs={expected_audio_path: "-loglevel quiet -y"},
    )
    mock_ffmpeg_inst.run.assert_called_once()
    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == get_graphql_endpoint()
    assert responses.calls[0].request.body.decode("UTF-8") == json.dumps(
        answer_update_gql(
            AnswerUpdateRequest(
                mentor=mentor,
                question=question,
                transcript=fake_transcript,
                media=media,
            )
        )
    )


def test_raises_if_video_path_not_specified(uploads_fixture):
    req = {"mentor": "m1", "question": "q1"}
    caught_exception = None
    try:
        process_answer_video(req)
    except Exception as err:
        caught_exception = err
    assert caught_exception is not None
    assert str(caught_exception) == "missing required param 'video_path'"


def test_raises_if_video_not_found_for_path(uploads_fixture):
    req = {"mentor": "m1", "question": "q1", "video_path": "not_exists.mp4"}
    caught_exception = None
    try:
        process_answer_video(req)
    except Exception as err:
        caught_exception = err
    assert caught_exception is not None
    assert str(caught_exception) == "video not found for path 'not_exists.mp4'"
