from os import environ, path

import transcribe

from . import ProcessAnswerRequest, ProcessAnswerResponse
from .media_tools import video_to_audio


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
    """
     TODO: fix the py-transcribe module...
     - should generate a jobId if you don't set one
     - should not require a batch id
     - {result}.jobs() seems to not return what it should?
     - seems to ignore passed in 'jobId'?
    """
    transcribe_result = transcription_service.transcribe(
        [transcribe.TranscribeJobRequest(sourceFile=audio_file)]
    )
    import logging

    logging.warning(f"transcribe_result={transcribe_result.to_dict()}")
    job_result = transcribe_result.first()
    transcript = job_result.transcript if job_result else ""
    return ProcessAnswerResponse(**req, transcript=transcript)
