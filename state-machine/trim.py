import json
from dataclasses import dataclass
import logging
from typing import List, Optional, Tuple, Union
import math
import ffmpy
from pymediainfo import MediaInfo
import os

log = logging.getLogger("trim")

def format_secs(secs: Union[float, int, str]) -> str:
    return f"{float(str(secs)):.3f}"

def output_args_trim_video(start_secs: float, end_secs: float) -> Tuple[str, ...]:
    return (
        "-ss",
        format_secs(start_secs),
        "-to",
        format_secs(end_secs),
        "-c:v",
        "libx264",
        "-crf",
        "30",
    )

def find_duration(audio_or_video_file: str) -> float:
    log.info(audio_or_video_file)
    media_info = MediaInfo.parse(audio_or_video_file, library_file='/opt/MediaInfo_DLL_21.09_Lambda/lib/libmediainfo.so')
    for t in media_info.tracks:
        if t.track_type in ["Video", "Audio"]:
            try:
                log.debug(t)
                return float(t.duration / 1000)
            except Exception:
                pass
    return -1.0

def handler(event, context):
    print('full duration', find_duration('./celery-short.mp4'))
    ff = ffmpy.FFmpeg(
        executable="/opt/ffmpeg/ffmpeg",
        inputs={str('./celery-short.mp4'): None},
        outputs={str("/tmp/trim.mp4"): output_args_trim_video(4, 8)},
    )
    ff.run()
    log.debug(ff)
    body = {
        "message": "test trim executed successfully!",
        "input": event,
        "env": os.environ.get("PYTHON_ENV", "")
    }
    os.remove("/tmp/trim.mp4")
    response = {
        "statusCode": 200,
        "body": json.dumps(body)
    }

    return response

    # Use this code if you don't use the http event with the LAMBDA-PROXY
    # integration
    """
    return {
        "message": "Go Serverless v1.0! Your function executed successfully!",
        "event": event
    }
    """

if __name__ == "__main__":
    handler({}, {})
    # pass