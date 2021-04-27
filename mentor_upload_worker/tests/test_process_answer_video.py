import re
from unittest.mock import patch, Mock

import pytest

from mentor_upload_process.process import process_answer_video
from .utils import fixture_upload


@pytest.fixture()
def uploads_fixture(monkeypatch) -> str:
    uploads_path = fixture_upload("")
    monkeypatch.setenv("UPLOADS", uploads_path)
    return uploads_path


@patch("ffmpy.FFmpeg")
def test_transcribes_mentor_answer(mock_ffmpeg_cls: Mock, uploads_fixture: str):
    req = {"mentor": "m1", "question": "q1", "video_path": "video1.mp4"}
    mock_ffmpeg_inst = Mock()
    mock_ffmpeg_cls.return_value = mock_ffmpeg_inst
    """
    TODO:
     - converts video to audio
     - uploads audio to transcribe
     - on success, writes transcription to gql
    """
    assert process_answer_video(req) == req
    video_path = fixture_upload(req.get("video_path", ""))
    expected_audio_path = re.sub("mp4$", "mp3", video_path)
    mock_ffmpeg_cls.assert_called_once_with(
        inputs={video_path: None},
        outputs={expected_audio_path: "-loglevel quiet -y"},
    )
    mock_ffmpeg_inst.run.assert_called_once()


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
