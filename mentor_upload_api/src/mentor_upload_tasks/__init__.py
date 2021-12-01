#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from os import environ
from typing import List, TypedDict


def get_queue_trim_upload_stage() -> str:
    return environ.get("TRIM_UPLOAD_QUEUE_NAME") or "trim_upload"


def get_queue_transcribe_stage() -> str:
    return environ.get("TRANSCRIBE_QUEUE_NAME") or "transcribe"


def get_queue_transcode_stage() -> str:
    return environ.get("TRANSCODE_QUEUE_NAME") or "transcode"


def get_queue_finalization_stage() -> str:
    return environ.get("FINALIZATION_QUEUE_NAME") or "finalization"


def get_queue_cancel_task() -> str:
    return environ.get("CANCEL_TASK_QUEUE_NAME") or "cancel"


class TrimRequest(TypedDict):
    start: float
    end: float


class ProcessAnswerRequest(TypedDict):
    mentor: str
    question: str
    video_path: str
    trim: TrimRequest


class Media:
    type: str
    tag: str
    url: str
    needsTransfer: bool  # noqa: N815


class TrimExistingUploadRequest(TypedDict):
    mentor: str
    question: str
    trim: TrimRequest
    transcript: str
    answer_media: List[Media]


class RegenVTTRequest(TypedDict):
    mentor: str
    question: str


class ProcessTransferRequest(TypedDict):
    mentor: str
    question: str


class UpdateTranscriptRequest(TypedDict):
    mentor: str
    question: str
    transcript: str


class CancelTaskRequest(TypedDict):
    mentor: str
    question: str
    task_id: str
