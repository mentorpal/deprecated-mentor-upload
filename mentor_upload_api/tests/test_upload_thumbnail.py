#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from contextlib import contextmanager
from datetime import datetime
import json
from os import path
from typing import List
from unittest.mock import call, patch, Mock

from callee.general import Any
from freezegun import freeze_time
import pytest
import responses

from mentor_upload_api.api import (
    get_graphql_endpoint,
    thumbnail_update_gql,
    GQLQueryBody,
    MentorThumbnailUpdateRequest,
)
from .utils import fixture_path, mock_s3_client

TEST_STATIC_AWS_REGION = "us-east-1"
TEST_STATIC_AWS_S3_BUCKET = "mentorpal-origin"
TEST_STATIC_URL_BASE = "https://test-static-123.mentorpal.org"
TIMESTAMP_DEFAULT = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def _expect_gql(expected_gql_queries: List[GQLQueryBody]) -> None:
    assert len(responses.calls) == len(expected_gql_queries)
    for i, query in enumerate(expected_gql_queries):
        assert responses.calls[i].request.url == get_graphql_endpoint()
        assert responses.calls[i].request.body.decode("UTF-8") == json.dumps(query)


def _mock_gql_thumbnail_update(mentor: str, thumbnail: str) -> GQLQueryBody:
    gql_req = MentorThumbnailUpdateRequest(mentor=mentor, thumbnail=thumbnail)
    gql_body = thumbnail_update_gql(gql_req)
    responses.add(
        responses.POST,
        get_graphql_endpoint(),
        json={"data": {"api": {"mentorThumbnailUpdate": True}}},
        status=200,
    )
    return gql_body


@contextmanager
def _test_env(monkeypatch, timestamp: str):
    freezer = freeze_time(timestamp)
    try:
        freezer.start()
        monkeypatch.setenv("STATIC_AWS_S3_BUCKET", TEST_STATIC_AWS_S3_BUCKET)
        monkeypatch.setenv("STATIC_AWS_REGION", TEST_STATIC_AWS_REGION)
        monkeypatch.setenv("STATIC_AWS_ACCESS_KEY_ID", "fake-access-key-id")
        monkeypatch.setenv("STATIC_AWS_SECRET_ACCESS_KEY", "fake-access-key-secret")
        monkeypatch.setenv("STATIC_URL_BASE", TEST_STATIC_URL_BASE)
        yield None
    finally:
        freezer.stop()


@responses.activate
@pytest.mark.parametrize(
    "input_mentor,input_thumbnail,timestamp",
    [
        ("mentor1-fake-mongoose-id", "thumbnail.txt", TIMESTAMP_DEFAULT),
    ],
)
@patch("boto3.client")
def test_upload(
    mock_boto3_client: Mock,
    input_mentor: str,
    input_thumbnail: str,
    timestamp: str,
    client,
    monkeypatch,
):
    fake_upload_png_path = path.join(fixture_path("input_thumbnails"), input_thumbnail)
    with _test_env(monkeypatch, timestamp):
        mock_s3 = mock_s3_client(mock_boto3_client)
        expected_thumbnail_path = (
            f"mentor/thumbnails/{input_mentor}/{timestamp}/thumbnail.png"
        )
        expected_gql_body = _mock_gql_thumbnail_update(
            input_mentor, expected_thumbnail_path
        )
        res = client.post(
            "upload/thumbnail",
            data={
                "body": json.dumps({"mentor": input_mentor}),
                "thumbnail": open(fake_upload_png_path, "rb"),
            },
        )
        assert res.status_code == 200
        assert res.json == {
            "data": {"thumbnail": f"{TEST_STATIC_URL_BASE}/{expected_thumbnail_path}"}
        }
        mock_s3.upload_fileobj.assert_called_once()
        expected_upload_file_calls = [
            call(
                Any(),
                TEST_STATIC_AWS_S3_BUCKET,
                expected_thumbnail_path,
                ExtraArgs={"ContentType": "image/png"},
            ),
        ]
        mock_s3.upload_fileobj.assert_has_calls(expected_upload_file_calls)

        _expect_gql([expected_gql_body])
