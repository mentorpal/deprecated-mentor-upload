#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from os import environ, path

import transcribe

from . import ProcessAnswerRequest, ProcessAnswerResponse
from .media_tools import video_to_audio
from .api import update_answer, AnswerUpdateRequest


def upload_path(p: str) -> str:
    uploads_dir = path.abspath(environ.get("UPLOADS") or "uploads")
    return path.join(uploads_dir, p)


def process_answer_video(req: ProcessAnswerRequest) -> ProcessAnswerResponse:
    video_path = req.get("video_path", "")
    if not video_path:
        raise Exception("missing required param 'video_path'")
    video_path_full = upload_path(video_path)
    if not path.isfile(video_path_full):
        raise Exception(f"video not found for path '{video_path}'")
    audio_file = video_to_audio(video_path_full)
    transcription_service = transcribe.init_transcription_service()
    mentor = req.get("mentor")
    question = req.get("question")
    transcribe_result = transcription_service.transcribe(
        [transcribe.TranscribeJobRequest(sourceFile=audio_file)]
    )
    import logging

    logging.warning(f"transcribe_result={transcribe_result.to_dict()}")
    job_result = transcribe_result.first()
    transcript = job_result.transcript if job_result else ""
    update_answer(
        AnswerUpdateRequest(mentor=mentor, question=question, transcript=transcript)
    )
    return ProcessAnswerResponse(**req, transcript=transcript)
