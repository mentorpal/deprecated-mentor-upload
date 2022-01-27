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
from mentor_upload_api.helpers import validate_json


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
            "mentor1-fake-mongoose-id",
            "question1-fakemongooseid",
            "video.mp4",
            "fake_finalization_task_id",
            "fake_transcoding_task_id",
            "fake_transcribing_task_id",
            "fake_trim_upload_task_id",
        ),
        (
            "http://a.diff.org",
            "mentor2-fake-mongoose-id",
            "question2-fakemongooseid",
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
@patch("mentor_upload_api.authorization_decorator.jwt.decode")
@patch.object(uuid, "uuid4")
def test_upload(
    mock_uuid,
    jwt_decode_mock: Mock,
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
    jwt_decode_mock.return_value = {
        "id": input_mentor,
        "role": "USER",
        "mentorIds": [input_mentor, "123456"],
    }
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
    task_list = [
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
    ]
    expected_status_update_query = _mock_gql_upload_task_update(
        mentor=input_mentor, question=input_question, task_list=task_list
    )
    res = client.post(
        f"{upload_domain}/upload/answer",
        data={
            "body": json.dumps({"mentor": input_mentor, "question": input_question}),
            "video": open(path.join(fixture_path("input_videos"), input_video), "rb"),
        },
        headers={"Authorization": "bearer abcdefg1234567"},
    )
    _expect_gql([expected_status_update_query])
    assert res.status_code == 200
    assert res.json == {
        "data": {
            "taskList": task_list,
            "statusUrl": f"{upload_domain}/upload/answer/status/{fake_task_id_collection}",
        }
    }
    root_ext = path.splitext(input_video)
    assert path.exists(
        path.join(
            tmpdir, f"uploads/fake_uuid-{input_mentor}-{input_question}{root_ext[1]}"
        )
    )


json_validation_fail_response_schema = {
    "type": "object",
    "properties": {
        "error": {"type": "string", "enum": ["ValidationError"]},
        "message": {"type": "string"},
    },
    "required": ["error", "message"],
}


def test_upload_throws_incorrect_json_payload(
    client,
):
    # No mentor provided
    res = client.post(
        "/upload/answer",
        data={
            "body": json.dumps({"question": "question1-fakemongooseid"}),
        },
    )
    json_data = res.json
    validate_json(json_data, json_validation_fail_response_schema)
    assert "'mentor' is a required property" in json_data["message"]

    # No question provided
    res = client.post(
        "/upload/answer",
        data={
            "body": json.dumps({"mentor": "mentor1-fake-mongoose-id"}),
            "video": open(path.join(fixture_path("input_videos"), "video.mp4"), "rb"),
        },
    )
    json_data = res.json
    validate_json(json_data, json_validation_fail_response_schema)
    assert "'question' is a required property" in res.json["message"]

    # Incorrect types
    res = client.post(
        "/upload/answer",
        data={
            "body": json.dumps({"mentor": 123, "question": 123}),
            "video": open(path.join(fixture_path("input_videos"), "video.mp4"), "rb"),
        },
    )
    json_data = res.json
    validate_json(json_data, json_validation_fail_response_schema)
    assert "123 is not of type 'string'" in res.json["message"]


def test_trim_existing_upload_throws_incorrect_json_payload(
    client,
):
    # No mentor provided
    res = client.post(
        "/upload/answer/trim_existing_upload",
        data={
            "body": json.dumps({"question": "question1-fakemongooseid"}),
            "video": open(path.join(fixture_path("input_videos"), "video.mp4"), "rb"),
        },
    )
    json_data = res.json
    validate_json(json_data, json_validation_fail_response_schema)
    assert "'mentor' is a required property" in res.json["message"]

    # No question provided
    res = client.post(
        "/upload/answer/trim_existing_upload",
        data={
            "body": json.dumps({"mentor": "mentor1-fake-mongoose-id"}),
            "video": open(path.join(fixture_path("input_videos"), "video.mp4"), "rb"),
        },
    )
    json_data = res.json
    validate_json(json_data, json_validation_fail_response_schema)
    assert "'question' is a required property" in res.json["message"]

    # Optional Trim provided, but incorrect type
    res = client.post(
        "/upload/answer/trim_existing_upload",
        data={
            "body": json.dumps(
                {
                    "mentor": "mentor1-fake-mongoose-id",
                    "question": "question1-fakemongooseid",
                    "trim": {"start": "123", "end": "123"},
                }
            ),
            "video": open(path.join(fixture_path("input_videos"), "video.mp4"), "rb"),
        },
    )
    json_data = res.json
    validate_json(json_data, json_validation_fail_response_schema)
    assert "'123' is not of type 'number'" in res.json["message"]


@pytest.mark.parametrize(
    "upload_domain,input_mentor,input_question,input_video,fake_finalization_task_id,fake_transcoding_task_id,fake_transcribing_task_id,fake_trim_upload_task_id,fake_cancel_finalization_task_id,fake_cancel_transcribe_task_id,fake_cancel_transcode_task_id,fake_cancel_trim_upload_task_id",
    [
        (
            "https://mentor.org",
            "mentor1-fake-mongoose-id",
            "question1-fakemongooseid",
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
            "mentor2-fake-mongoose-id",
            "question2-fakemongooseid",
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
@patch("mentor_upload_api.authorization_decorator.jwt.decode")
@patch.object(uuid, "uuid4")
def test_cancel(
    mock_uuid,
    jwt_decode_mock: Mock,
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
    jwt_decode_mock.return_value = {
        "id": "mentor1-fake-mongoose-id",
        "role": "ADMIN",
        "mentorIds": ["123456", "123456"],
    }
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
    task_list = [
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
    ]
    expected_status_update_query = _mock_gql_upload_task_update(
        mentor=input_mentor, question=input_question, task_list=task_list
    )
    res = client.post(
        f"{upload_domain}/upload/answer",
        data={
            "body": json.dumps({"mentor": input_mentor, "question": input_question}),
            "video": open(path.join(fixture_path("input_videos"), input_video), "rb"),
        },
        headers={"Authorization": "bearer abcdefg1234567"},
    )
    _expect_gql([expected_status_update_query])
    assert res.status_code == 200
    assert res.json == {
        "data": {
            "taskList": task_list,
            "statusUrl": f"{upload_domain}/upload/answer/status/{fake_task_id_collection}",
        }
    }

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
        headers={"Authorization": "bearer abcdefg1234567"},
    )
    assert res.status_code == 200
    assert res.json == {
        "data": {
            "id": fake_cancel_trim_upload_task_id,
            "cancelledIds": [fake_trim_upload_task_id],
        }
    }


def test_cancel_upload_throw_incorrect_json_payload(client):
    # Missing task_ids_to_cancel
    res = client.post(
        "/upload/answer/cancel",
        json={
            "mentor": "mentor1-fake-mongoose-id",
            "question": "question1-fakemongooseid",
        },
    )
    json_data = res.json
    validate_json(json_data, json_validation_fail_response_schema)
    assert "'task_ids_to_cancel' is a required property" in res.json["message"]

    # # Missing question
    res = client.post(
        "/upload/answer/cancel",
        json={
            "mentor": "mentor1-fake-mongoose-id",
            "task_ids_to_cancel": ["123", "123"],
        },
    )
    json_data = res.json
    validate_json(json_data, json_validation_fail_response_schema)
    assert "'question' is a required property" in res.json["message"]

    # # Incorrect Types
    res = client.post(
        "/upload/answer/cancel",
        json={
            "mentor": "mentor1-fake-mongoose-id",
            "question": "question1-fakemongooseid",
            "task_ids_to_cancel": [123, 123],
        },
    )
    json_data = res.json
    validate_json(json_data, json_validation_fail_response_schema)
    assert "123 is not of type 'string'" in res.json["message"]


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
@patch("mentor_upload_api.authorization_decorator.jwt.decode")
def test_env_fixes_ssl_status_url(
    jwt_decode_mock: Mock,
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
    jwt_decode_mock.return_value = {
        "id": "mentor1-fake-mongoose-id",
        "role": "ADMIN",
        "mentorIds": ["123456", "123456"],
    }
    fake_mentor_id = "mentor1-fake-mongoose-id"
    fake_question_id = "question-fake-mongooseid"
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
    task_list = [
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
    ]
    expected_status_update_query = _mock_gql_upload_task_update(
        mentor=fake_mentor_id, question=fake_question_id, task_list=task_list
    )
    res = client.post(
        f"{request_root}/upload/answer",
        data={
            "body": json.dumps(
                {"mentor": fake_mentor_id, "question": fake_question_id}
            ),
            "video": fake_video,
        },
        headers={"Authorization": "bearer abcdefg1234567"},
    )
    _expect_gql([expected_status_update_query])
    assert res.status_code == 200
    assert res.json == {
        "data": {
            "taskList": task_list,
            "statusUrl": f"{expected_status_url_root}/upload/answer/status/{[fake_transcode_task_id,fake_transcribe_task_id,fake_trim_upload_task_id,fake_finalization_task_id]}",
        }
    }


@pytest.mark.parametrize(
    "task_name,task_id,state,status,info,expected_info",
    [
        ("trim_upload", "fake-task-id-123", "PENDING", "working", None, None),
        ("finalization", "fake-task-id-234", "STARTED", "working harder", None, None),
        ("transcode", "fake-task-id-456", "SUCCESS", "done!", None, None),
        (
            "transcribe",
            "fake-task-id-678",
            "FAILURE",
            "error!",
            Exception("error message"),
            "error message",
        ),
    ],
)
@patch("mentor_upload_tasks.tasks.trim_upload_stage")
@patch("mentor_upload_tasks.tasks.transcode_stage")
@patch("mentor_upload_tasks.tasks.transcribe_stage")
@patch("mentor_upload_tasks.tasks.finalization_stage")
def test_it_returns_status_for_a_upload_job(
    finalization_stage_task,
    transcribe_stage_task,
    transcode_stage_task,
    trim_upload_stage_task,
    task_name,
    task_id,
    state,
    status,
    info,
    expected_info,
    client,
):
    mock_task = Bunch(id=task_id, state=state, status=status, info=info)
    trim_upload_stage_task.AsyncResult.return_value = mock_task
    transcode_stage_task.AsyncResult.return_value = mock_task
    transcribe_stage_task.AsyncResult.return_value = mock_task
    finalization_stage_task.AsyncResult.return_value = mock_task
    res = client.get(f"/upload/answer/status/{task_name}/{task_id}")
    assert res.status_code == 200
    assert res.json == {
        "data": {
            "id": task_id,
            "state": state,
            "status": status,
            "info": expected_info,
        }
    }
