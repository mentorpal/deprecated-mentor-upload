from typing import TypedDict


class ProcessAnswerRequest(TypedDict):
    mentor: str
    question: str
    video_path: str


class ProcessAnswerResponse(TypedDict):
    mentor: str
    question: str
    transcript: str
