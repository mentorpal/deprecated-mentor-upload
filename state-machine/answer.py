import json
import boto3
import tempfile
import os
import logger

from media_tools import (
    video_trim,
    video_encode_for_mobile,
    video_encode_for_web,
    video_to_audio,
    transcript_to_vtt,
    trim_vtt_and_transcript_via_timestamps,
)

log = logger.getLogger("answer-handler")

def _require_env(n: str) -> str:
    env_val = os.environ.get(n, "")
    if not env_val:
        raise EnvironmentError(f"missing required env var {n}")
    return env_val

s3_bucket = _require_env("S3_STATIC_ARN").split(':')[-1]
log.info('using s3 bucket %s', s3_bucket)
s3 = boto3.client("s3")


def transcode_stage(video_file, s3_path):
    work_dir = os.path.dirname(video_file)
    mobile_mp4 = os.path.join(work_dir, "mobile.mp4")
    video_encode_for_mobile(video_file, mobile_mp4)
    
    log.debug("uploading %s to %s", mobile_mp4, s3_bucket)
    s3.upload_file(
        mobile_mp4,
        s3_bucket,
        os.path.join(f"{s3_path}/mobile.mp4"),
        ExtraArgs={"ContentType": "video/mp4"},
    )

    web_mp4 = os.path.join(work_dir, "web.mp4")
    video_encode_for_web(video_file, web_mp4)

    log.debug("uploading %s to %s", web_mp4, s3_bucket)
    s3.upload_file(
        web_mp4,
        s3_bucket,
        os.path.join(f"{s3_path}/web.mp4"),
        ExtraArgs={"ContentType": "video/mp4"},
    )
        

def handler(event, context):
    log.info(json.dumps(event))
    for record in event['Records']:
        payload = record["body"]
        request = json.loads(str(payload))['request']
        log.info('video to process %s', request['video'])
        with tempfile.TemporaryDirectory() as work_dir:
            work_file = os.path.join(work_dir, 'original.mp4')
            s3.download_file(s3_bucket, request['video'], work_file)
            s3_path = os.path.dirname(request['video']) # same 'folder' as original file
            log.debug('%s downloaded to %s', request['video'], work_dir)

            if 'trim' in request:
                trim_file = os.path.join(work_dir, "trim.mp4")
                video_trim(work_file, trim_file, request['trim']['start'], request['trim']['end'])
                work_file = trim_file # from now on work with the trimmed file
            
            transcode_stage(work_file, s3_path)
            
            # TODO notify graphql

# TODO dlq
# TODO alerting and monitoring

# if __name__ == "__main__":
#     with open('./answer.event.json.dist','r') as f:
#         e = json.loads(f.read())
#         handler(e,{})