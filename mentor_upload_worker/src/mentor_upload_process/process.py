from os import environ, path

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
    video_to_audio(video_path_full)
    return req
