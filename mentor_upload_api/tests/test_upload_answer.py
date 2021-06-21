#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
import json
from math import isclose
import subprocess
from os import path
from unittest.mock import patch, Mock
import uuid

import pytest

from .utils import Bunch, fixture_path


def _get_video_length(filename):
    result = subprocess.run(
        [
            "./ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            filename,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return float(result.stdout)


@pytest.fixture(autouse=True)
def python_path_env(monkeypatch, tmpdir):
    monkeypatch.setenv("UPLOAD_ROOT", path.abspath(tmpdir.join("uploads")))


@pytest.mark.parametrize(
    "upload_domain,input_mentor,input_question,input_video,fake_task_id",
    [
        ("https://mentor.org", "mentor1", "q1", "video.mp4", "fake_task_id_1"),
        ("http://a.diff.org", "mentor2", "q2", "video.mp4", "fake_task_id_2"),
    ],
)
@patch("mentor_upload_tasks.tasks.process_answer_video")
@patch.object(uuid, "uuid4")
def test_upload(
    mock_uuid,
    mock_upload_task,
    tmpdir,
    upload_domain,
    input_mentor,
    input_question,
    input_video,
    fake_task_id,
    client,
):
    mock_uuid.return_value = "fake_uuid"
    mock_task = Bunch(id=fake_task_id)
    mock_upload_task.apply_async.return_value = mock_task
    res = client.post(
        f"{upload_domain}/upload/answer",
        data={
            "body": json.dumps({"mentor": input_mentor, "question": input_question}),
            "video": open(path.join(fixture_path("input_videos"), input_video), "rb"),
        },
    )
    assert res.status_code == 200
    assert res.json == {
        "data": {
            "id": fake_task_id,
            "statusUrl": f"{upload_domain}/upload/answer/status/{fake_task_id}",
        }
    }
    root_ext = path.splitext(input_video)
    assert path.exists(
        path.join(
            tmpdir, f"uploads/fake_uuid-{input_mentor}-{input_question}{root_ext[1]}"
        )
    )


@pytest.mark.parametrize(
    "upload_domain,input_mentor,input_question,input_video,fake_task_id,fake_cancel_task_id",
    [
        (
            "https://mentor.org",
            "mentor1",
            "q1",
            "video.mp4",
            "fake_task_id_1",
            "fake_cancel_task_id_1",
        ),
        (
            "http://a.diff.org",
            "mentor2",
            "q2",
            "video.mp4",
            "fake_task_id_2",
            "fake_cancel_task_id_2",
        ),
    ],
)
@patch("mentor_upload_tasks.tasks.cancel_task")
@patch("mentor_upload_tasks.tasks.process_answer_video")
@patch.object(uuid, "uuid4")
def test_cancel(
    mock_uuid,
    mock_upload_task,
    mock_cancel_task,
    tmpdir,
    upload_domain,
    input_mentor,
    input_question,
    input_video,
    fake_task_id,
    fake_cancel_task_id,
    client,
):
    mock_uuid.return_value = "fake_uuid"
    mock_task = Bunch(id=fake_task_id)
    mock_upload_task.apply_async.return_value = mock_task
    res = client.post(
        f"{upload_domain}/upload/answer",
        data={
            "body": json.dumps({"mentor": input_mentor, "question": input_question}),
            "video": open(path.join(fixture_path("input_videos"), input_video), "rb"),
        },
    )
    assert res.status_code == 200
    assert res.json == {
        "data": {
            "id": fake_task_id,
            "statusUrl": f"{upload_domain}/upload/answer/status/{fake_task_id}",
        }
    }
    mock_cancel_task_id = Bunch(id=fake_cancel_task_id)
    mock_cancel_task.apply_async.return_value = mock_cancel_task_id
    res = client.post(
        f"{upload_domain}/upload/answer/cancel",
        json={
            "mentor": input_mentor,
            "question": input_question,
            "task": fake_task_id,
        },
    )
    assert res.status_code == 200
    assert res.json == {
        "data": {
            "id": fake_cancel_task_id,
            "cancelledId": fake_task_id,
        }
    }


# ISSUE: if the upload api doesn't do end-to-end ssl
# (e.g. if nginx terminates ssl),
# then upload-api doesn't know that its TRUE
# root url is https://...
@pytest.mark.parametrize(
    "request_root,env_val,expected_status_url_root",
    [
        ("http://mentor.org", None, "http://mentor.org"),
        ("http://mentor.org", "1", "https://mentor.org"),
        ("http://mentor.org", "y", "https://mentor.org"),
        ("http://mentor.org", "true", "https://mentor.org"),
        ("http://mentor.org", "on", "https://mentor.org"),
    ],
)
@patch("mentor_upload_tasks.tasks.process_answer_video")
def test_env_fixes_ssl_status_url(
    mock_upload_task: Mock,
    request_root: str,
    env_val: str,
    expected_status_url_root: str,
    monkeypatch,
    client,
):
    fake_task_id = "fake_task_id"
    fake_mentor_id = "mentor1"
    fake_question_id = "question1"
    fake_video = open(path.join(fixture_path("input_videos"), "video.mp4"), "rb")
    if env_val is not None:
        monkeypatch.setenv("STATUS_URL_FORCE_HTTPS", env_val)
    mock_task = Bunch(id=fake_task_id)
    mock_upload_task.apply_async.return_value = mock_task
    res = client.post(
        f"{request_root}/upload/answer",
        data={
            "body": json.dumps(
                {"mentor": fake_mentor_id, "question": fake_question_id}
            ),
            "video": fake_video,
        },
    )
    assert res.status_code == 200
    assert res.json == {
        "data": {
            "id": fake_task_id,
            "statusUrl": f"{expected_status_url_root}/upload/answer/status/fake_task_id",
        }
    }


@pytest.mark.parametrize(
    "task_id,state,status,info,expected_info",
    [
        ("fake-task-id-123", "PENDING", "working", None, None),
        ("fake-task-id-234", "STARTED", "working harder", None, None),
        ("fake-task-id-456", "SUCCESS", "done!", None, None),
        (
            "fake-task-id-678",
            "FAILURE",
            "error!",
            Exception("error message"),
            "error message",
        ),
    ],
)
@patch("mentor_upload_tasks.tasks.process_answer_video")
def test_it_returns_status_for_a_upload_job(
    mock_upload_task, task_id, state, status, info, expected_info, client
):
    mock_task = Bunch(id=task_id, state=state, status=status, info=info)
    mock_upload_task.AsyncResult.return_value = mock_task
    res = client.get(f"/upload/answer/status/{task_id}")
    assert res.status_code == 200
    assert res.json == {
        "data": {"id": task_id, "state": state, "status": status, "info": expected_info}
    }
