#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
import json
from typing import List
from mentor_upload_api.api import (
    upload_task_req_gql,
    UploadTaskRequest,
    get_graphql_endpoint,
    TaskInfo,
)
from os import path
from unittest.mock import patch, Mock
import responses
import uuid

import pytest

from .utils import Bunch, fixture_path


def _mock_gql_upload_task_update(
    mentor: str,
    question: str,
    task_list: List[TaskInfo],
    transcript: str = None,
    media=None,
) -> dict:
    gql_query = upload_task_req_gql(
        UploadTaskRequest(
            mentor=mentor,
            question=question,
            task_list=task_list,
            transcript="",
            media=[],
        )
    )
    responses.add(
        responses.POST,
        get_graphql_endpoint(),
        json=gql_query,
        status=200,
    )
    return gql_query


def _expect_gql(expected_gql_queries: List[dict]) -> None:
    assert len(responses.calls) == len(expected_gql_queries)
    for i, query in enumerate(expected_gql_queries):
        assert responses.calls[i].request.url == get_graphql_endpoint()
        assert responses.calls[i].request.body.decode("UTF-8") == json.dumps(query)


@pytest.fixture(autouse=True)
def python_path_env(monkeypatch, tmpdir):
    monkeypatch.setenv("UPLOAD_ROOT", path.abspath(tmpdir.join("uploads")))


@pytest.mark.parametrize(
    "upload_domain,input_mentor,input_question,input_video,fake_finalization_task_id,fake_transcoding_task_id,fake_transcribing_task_id,fake_trim_upload_task_id",
    [
        (
            "https://mentor.org",
            "mentor1",
            "q1",
            "video.mp4",
            "fake_finalization_task_id",
            "fake_transcoding_task_id",
            "fake_transcribing_task_id",
            "fake_trim_upload_task_id",
        ),
        (
            "http://a.diff.org",
            "mentor2",
            "q2",
            "video.mp4",
            "fake_finalization_task_id_2",
            "fake_transcoding_task_id_2",
            "fake_transcribing_task_id_2",
            "fake_trim_upload_task_id_2",
        ),
    ],
)
@responses.activate
@patch("mentor_upload_api.blueprints.upload.answer.begin_tasks_in_parallel")
@patch("mentor_upload_tasks.tasks.trim_upload_stage")
@patch("mentor_upload_tasks.tasks.transcode_stage")
@patch("mentor_upload_tasks.tasks.transcribe_stage")
@patch("mentor_upload_tasks.tasks.finalization_stage")
@patch.object(uuid, "uuid4")
def test_upload(
    mock_uuid,
    finalization_stage_task,
    transcribe_stage_task,
    transcode_stage_task,
    trim_upload_stage_task,
    mock_begin_tasks_in_parallel,
    tmpdir,
    upload_domain,
    input_mentor,
    input_question,
    input_video,
    fake_finalization_task_id,
    fake_transcoding_task_id,
    fake_transcribing_task_id,
    fake_trim_upload_task_id,
    client,
):
    mock_uuid.return_value = "fake_uuid"
    mock_chord_result = Bunch(
        parent=Bunch(
            results=[
                Bunch(id=fake_transcoding_task_id),
                Bunch(id=fake_transcribing_task_id),
            ],
            parent=Bunch(results=[Bunch(id=fake_trim_upload_task_id)]),
        ),
        id=fake_finalization_task_id,
    )
    mock_begin_tasks_in_parallel.return_value = mock_chord_result

    fake_task_id_collection = [
        fake_transcoding_task_id,
        fake_transcribing_task_id,
        fake_trim_upload_task_id,
        fake_finalization_task_id,
    ]

    expected_status_update_query = _mock_gql_upload_task_update(
        mentor=input_mentor,
        question=input_question,
        task_list=[
            {
                "task_name": "trim_upload",
                "task_id": fake_trim_upload_task_id,
                "status": "QUEUED",
            },
            {
                "task_name": "transcoding",
                "task_id": fake_transcoding_task_id,
                "status": "QUEUED",
            },
            {
                "task_name": "transcribing",
                "task_id": fake_transcribing_task_id,
                "status": "QUEUED",
            },
            {
                "task_name": "finalization",
                "task_id": fake_finalization_task_id,
                "status": "QUEUED",
            },
        ],
    )
    # sends the request to trigger upload()
    res = client.post(
        f"{upload_domain}/upload/answer",
        data={
            "body": json.dumps({"mentor": input_mentor, "question": input_question}),
            "video": open(path.join(fixture_path("input_videos"), input_video), "rb"),
        },
    )
    _expect_gql([expected_status_update_query])
    assert res.status_code == 200
    assert res.json == {
        "data": {
            "id": fake_task_id_collection,
            "statusUrl": f"{upload_domain}/upload/answer/status/{fake_task_id_collection}",
        }
    }
    root_ext = path.splitext(input_video)
    assert path.exists(
        path.join(
            tmpdir, f"uploads/fake_uuid-{input_mentor}-{input_question}{root_ext[1]}"
        )
    )


@pytest.mark.parametrize(
    "upload_domain,input_mentor,input_question,input_video,fake_finalization_task_id,fake_transcoding_task_id,fake_transcribing_task_id,fake_trim_upload_task_id,fake_cancel_finalization_task_id,fake_cancel_transcribe_task_id,fake_cancel_transcode_task_id,fake_cancel_trim_upload_task_id",
    [
        (
            "https://mentor.org",
            "mentor1",
            "q1",
            "video.mp4",
            "fake_finalization_task_id",
            "fake_transcoding_task_id",
            "fake_transcribing_task_id",
            "fake_trim_upload_task_id",
            "fake_cancel_finalization_task_id",
            "fake_cancel_transcribe_task_id",
            "fake_cancel_transcode_task_id",
            "fake_cancel_trim_upload_task_id",
        ),
        (
            "http://a.diff.org",
            "mentor2",
            "q2",
            "video.mp4",
            "fake_finalization_task_id_2",
            "fake_transcoding_task_id_2",
            "fake_transcribing_task_id_2",
            "fake_trim_upload_task_id_2",
            "fake_cancel_finalization_task_id_2",
            "fake_cancel_transcribe_task_id_2",
            "fake_cancel_transcode_task_id_2",
            "fake_cancel_trim_upload_task_id_2",
        ),
    ],
)
@responses.activate
@patch("mentor_upload_api.blueprints.upload.answer.group")
@patch("mentor_upload_api.blueprints.upload.answer.begin_tasks_in_parallel")
@patch("mentor_upload_tasks.tasks.cancel_task")
@patch("mentor_upload_tasks.tasks.trim_upload_stage")
@patch("mentor_upload_tasks.tasks.transcode_stage")
@patch("mentor_upload_tasks.tasks.transcribe_stage")
@patch("mentor_upload_tasks.tasks.finalization_stage")
@patch.object(uuid, "uuid4")
def test_cancel(
    mock_uuid,
    finalization_stage_task,
    transcribe_stage_task,
    transcode_stage_task,
    trim_upload_stage_task,
    mock_cancel_task,
    mock_begin_tasks_in_parallel,
    mock_task_group,
    tmpdir,
    upload_domain,
    input_mentor,
    input_question,
    input_video,
    fake_finalization_task_id,
    fake_transcoding_task_id,
    fake_transcribing_task_id,
    fake_trim_upload_task_id,
    fake_cancel_finalization_task_id,
    fake_cancel_transcribe_task_id,
    fake_cancel_transcode_task_id,
    fake_cancel_trim_upload_task_id,
    client,
):
    mock_uuid.return_value = "fake_uuid"
    # mocking the result of the chord
    mock_chord_result = Bunch(
        parent=Bunch(
            results=[
                Bunch(id=fake_transcoding_task_id),
                Bunch(id=fake_transcribing_task_id),
            ],
            parent=Bunch(results=[Bunch(id=fake_trim_upload_task_id)]),
        ),
        id=fake_finalization_task_id,
    )
    mock_begin_tasks_in_parallel.return_value = mock_chord_result

    fake_task_id_collection = [
        fake_transcoding_task_id,
        fake_transcribing_task_id,
        fake_trim_upload_task_id,
        fake_finalization_task_id,
    ]

    expected_status_update_query = _mock_gql_upload_task_update(
        mentor=input_mentor,
        question=input_question,
        task_list=[
            {
                "task_name": "trim_upload",
                "task_id": fake_trim_upload_task_id,
                "status": "QUEUED",
            },
            {
                "task_name": "transcoding",
                "task_id": fake_transcoding_task_id,
                "status": "QUEUED",
            },
            {
                "task_name": "transcribing",
                "task_id": fake_transcribing_task_id,
                "status": "QUEUED",
            },
            {
                "task_name": "finalization",
                "task_id": fake_finalization_task_id,
                "status": "QUEUED",
            },
        ],
    )
    res = client.post(
        f"{upload_domain}/upload/answer",
        data={
            "body": json.dumps({"mentor": input_mentor, "question": input_question}),
            "video": open(path.join(fixture_path("input_videos"), input_video), "rb"),
        },
    )
    _expect_gql([expected_status_update_query])
    assert res.status_code == 200
    assert res.json == {
        "data": {
            "id": fake_task_id_collection,
            "statusUrl": f"{upload_domain}/upload/answer/status/{fake_task_id_collection}",
        }
    }
    # cancelling 1 task
    mock_task_group().apply_async.return_value = Bunch(
        id=fake_cancel_trim_upload_task_id
    )
    mock_cancel_trim_upload_task_id = Bunch(id=fake_cancel_trim_upload_task_id)
    mock_cancel_task.si.set.return_value = mock_cancel_trim_upload_task_id
    res = client.post(
        f"{upload_domain}/upload/answer/cancel",
        json={
            "mentor": input_mentor,
            "question": input_question,
            "task_ids_to_cancel": [fake_trim_upload_task_id],
        },
    )
    assert res.status_code == 200
    assert res.json == {
        "data": {
            "id": fake_cancel_trim_upload_task_id,
            "cancelledIds": [fake_trim_upload_task_id],
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
@responses.activate
@patch("mentor_upload_api.blueprints.upload.answer.begin_tasks_in_parallel")
@patch("mentor_upload_tasks.tasks.trim_upload_stage")
@patch("mentor_upload_tasks.tasks.transcode_stage")
@patch("mentor_upload_tasks.tasks.transcribe_stage")
@patch("mentor_upload_tasks.tasks.finalization_stage")
def test_env_fixes_ssl_status_url(
    finalization_stage_task,
    transcribe_stage_task,
    transcode_stage_task,
    trim_upload_stage_task,
    mock_begin_tasks_in_parallel: Mock,
    request_root: str,
    env_val: str,
    expected_status_url_root: str,
    monkeypatch,
    client,
):
    fake_mentor_id = "mentor1"
    fake_question_id = "question1"
    fake_video = open(path.join(fixture_path("input_videos"), "video.mp4"), "rb")
    if env_val is not None:
        monkeypatch.setenv("STATUS_URL_FORCE_HTTPS", env_val)

    fake_trim_upload_task_id = "fake_trim_upload_task_id"
    fake_transcribe_task_id = "fake_transcribe_task_id"
    fake_transcode_task_id = "fake_transcode_task_id"
    fake_finalization_task_id = "fake_finalization_task_id"
    mock_chord_result = Bunch(
        parent=Bunch(
            results=[
                Bunch(id=fake_transcode_task_id),
                Bunch(id=fake_transcribe_task_id),
            ],
            parent=Bunch(results=[Bunch(id=fake_trim_upload_task_id)]),
        ),
        id=fake_finalization_task_id,
    )
    mock_begin_tasks_in_parallel.return_value = mock_chord_result

    expected_status_update_query = _mock_gql_upload_task_update(
        mentor=fake_mentor_id,
        question=fake_question_id,
        task_list=[
            {
                "task_name": "trim_upload",
                "task_id": fake_trim_upload_task_id,
                "status": "QUEUED",
            },
            {
                "task_name": "transcoding",
                "task_id": fake_transcode_task_id,
                "status": "QUEUED",
            },
            {
                "task_name": "transcribing",
                "task_id": fake_transcribe_task_id,
                "status": "QUEUED",
            },
            {
                "task_name": "finalization",
                "task_id": fake_finalization_task_id,
                "status": "QUEUED",
            },
        ],
    )
    res = client.post(
        f"{request_root}/upload/answer",
        data={
            "body": json.dumps(
                {"mentor": fake_mentor_id, "question": fake_question_id}
            ),
            "video": fake_video,
        },
    )
    _expect_gql([expected_status_update_query])
    assert res.status_code == 200
    assert res.json == {
        "data": {
            "id": [
                fake_transcode_task_id,
                fake_transcribe_task_id,
                fake_trim_upload_task_id,
                fake_finalization_task_id,
            ],
            "statusUrl": f"{expected_status_url_root}/upload/answer/status/{[fake_transcode_task_id,fake_transcribe_task_id,fake_trim_upload_task_id,fake_finalization_task_id]}",
        }
    }


# TODO: update along with upload_status(task_id: str) in answer.py
# @pytest.mark.only
# @pytest.mark.parametrize(
#     "task_id,state,status,info,expected_info",
#     [
#         ("fake-task-id-123", "PENDING", "working", None, None),
#         ("fake-task-id-234", "STARTED", "working harder", None, None),
#         ("fake-task-id-456", "SUCCESS", "done!", None, None),
#         (
#             "fake-task-id-678",
#             "FAILURE",
#             "error!",
#             Exception("error message"),
#             "error message",
#         ),
#     ],
# )
# @patch("mentor_upload_tasks.tasks.trim_upload_stage")
# @patch("mentor_upload_tasks.tasks.transcode_stage")
# @patch("mentor_upload_tasks.tasks.transcribe_stage")
# @patch("mentor_upload_tasks.tasks.finalization_stage")
# def test_it_returns_status_for_a_upload_job(
#     finalization_stage_task,
#     transcribe_stage_task,
#     transcode_stage_task,
#     trim_upload_stage_task,
#     task_id,
#     state,
#     status,
#     info,
#     expected_info,
#     client,
# ):
#     mock_task = Bunch(id=task_id, state=state, status=status, info=info)
#     trim_upload_stage_task.AsyncResult.return_value = mock_task
#     res = client.get(f"/upload/answer/status/{task_id}")
#     assert res.status_code == 200
#     assert res.json == {
#         "data": {
#             "task_id": task_id,
#             "state": state,
#             "status": status,
#             "info": expected_info,
#         }
#     }
