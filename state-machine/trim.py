import json
from dataclasses import dataclass
import logging
from typing import List, Optional, Tuple, Union
import math
import ffmpy
from pymediainfo import MediaInfo
import os
import sys

log = logging.getLogger("trim")

# # add ffmpeg binary to the path:
# here = os.path.dirname(os.path.realpath(__file__))
# sys.path.append(os.path.join(here, 'binaries/ffmpeg'))

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
    media_info = MediaInfo.parse(audio_or_video_file, library_file='./binaries/MediaInfo_DLL_21.09_Lambda/lib/libmediainfo.so')
    for t in media_info.tracks:
        if t.track_type in ["Video", "Audio"]:
            try:
                log.debug(t)
                return float(t.duration / 1000)
            except Exception:
                pass
    return -1.0

def handler(event, context):
    # print('full duration', find_duration('./celery-short.mp4'))
    ff = ffmpy.FFmpeg(
        # executable="./binaries/ffmpeg/ffmpeg",
        # inputs={str('./celery-short.mp4'): None},
        inputs={str('https://static-mentorpal-v2-mentorpal-origin.s3.amazonaws.com/videos/60ba6dbc733e6a54b9b9af3a/6098b41257ab183da46cf777/20210605T013318Z/web.mp4'): None},
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