#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import json
from os import path
from pathlib import Path

import boto3
from boto3_type_annotations.s3 import ServiceResource
from moto import mock_s3
from freezegun import freeze_time
import pytest

from . import fixture_path

TEST_STATIC_AWS_REGION = "us-east-1"
TEST_STATIC_AWS_S3_BUCKET = "mentorpal-origin"
TEST_STATIC_URL_BASE = "https://test-static-123.mentorpal.org"
TIMESTAMP_DEFAULT = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


@dataclass
class _TestEnv:
    s3: ServiceResource


@contextmanager
def _test_env(monkeypatch, timestamp: str) -> _TestEnv:
    freezer = freeze_time(timestamp)
    s3_mocker = mock_s3()
    try:
        s3_mocker.start()
        freezer.start()
        monkeypatch.setenv("STATIC_AWS_S3_BUCKET", TEST_STATIC_AWS_S3_BUCKET)
        monkeypatch.setenv("STATIC_AWS_REGION", TEST_STATIC_AWS_REGION)
        monkeypatch.setenv("STATIC_AWS_ACCESS_KEY_ID", "fake-access-key-id")
        monkeypatch.setenv("STATIC_AWS_SECRET_ACCESS_KEY", "fake-access-key-secret")
        monkeypatch.setenv("STATIC_URL_BASE", TEST_STATIC_URL_BASE)
        conn = boto3.resource(
            "s3",
            region_name=TEST_STATIC_AWS_REGION,
            aws_access_key_id="fake-access-key-id",
            aws_secret_access_key="fake-access-key-secret",
        )
        # We need to create the bucket since this is all in Moto's 'virtual' AWS account
        conn.create_bucket(Bucket=TEST_STATIC_AWS_S3_BUCKET)
        yield _TestEnv(s3=conn)
    finally:
        freezer.stop()
        s3_mocker.stop()


@pytest.mark.parametrize(
    "input_mentor,input_thumbnail,timestamp",
    [
        ("mentor1", "thumbnail.txt", TIMESTAMP_DEFAULT),
    ],
)
def test_upload(
    input_mentor: str, input_thumbnail: str, timestamp: str, client, monkeypatch
):
    fake_upload_png_path = path.join(fixture_path("input_thumbnails"), input_thumbnail)
    with _test_env(monkeypatch, timestamp) as test_env:
        res = client.post(
            "upload/thumbnail",
            data={
                "body": json.dumps({"mentor": input_mentor}),
                "thumbnail": open(fake_upload_png_path, "rb"),
            },
        )
        assert res.status_code == 200
        expected_thumbnail_path = (
            f"mentor/thumbnails/{input_mentor}/{timestamp}/thumbnail.png"
        )
        assert res.json == {
            "data": {"thumbnail": f"{TEST_STATIC_URL_BASE}/{expected_thumbnail_path}"}
        }
        uploaded_content = (
            test_env.s3.Object(TEST_STATIC_AWS_S3_BUCKET, expected_thumbnail_path)
            .get()["Body"]
            .read()
            .decode("utf-8")
        )
        assert uploaded_content == Path(fake_upload_png_path).read_text()
