#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
import os
import datetime

import ffmpy
from pymediainfo import MediaInfo


def get_upload_root() -> str:
    return environ.get("UPLOAD_ROOT") or "./uploads"


def trim_video(input_file, output_file, start, end):
    if not os.path.exists(input_file):
        raise Exception(f"ERROR: Can't trim, {input_file} doesn't exist")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    output_command = [
        "-ss",
        str(datetime.timedelta(seconds=start)),
        "-to",
        str(datetime.timedelta(seconds=end)),
        "-c:v",
        "libx264",
        "-crf",
        "30",
    ]
    ff = ffmpy.FFmpeg(
        inputs={str(input_file): None},
        outputs={str(output_file): tuple(i for i in output_command)},
    )
    ff.run()


def find_video_dims(video_file):
    media_info = MediaInfo.parse(video_file)
    video_tracks = [t for t in media_info.tracks if t.track_type == "Video"]
    return (
        (video_tracks[0].width, video_tracks[0].height)
        if len(video_tracks) >= 1
        else (-1, -1)
    )


def video_encode_for_mobile(src_file: str, tgt_file: str, target_height=480) -> None:
    i_w, i_h = find_video_dims(src_file)
    o_w, o_h = (target_height, target_height)
    crop_w = 0
    crop_h = 0
    if i_w > i_h:
        # for now assumes we want to zoom in slightly on landscape videos
        # before cropping to square
        crop_h = i_h * 0.25
        crop_w = i_w - (i_h - crop_h)
    else:
        crop_h = crop_h - crop_h
    os.makedirs(os.path.dirname(tgt_file), exist_ok=True)
    output_command = [
        "-y",
        "-filter:v",
        f"crop=iw-{crop_w:.0f}:ih-{crop_h:.0f},scale={o_w:.0f}:{o_h:.0f}",
        "-c:v",
        "libx264",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-ac",
        "1",
        "-loglevel",
        "quiet",
    ]
    ff = ffmpy.FFmpeg(
        inputs={str(src_file): None},
        outputs={str(tgt_file): tuple(i for i in output_command)},
    )
    ff.run()


def video_encode_for_web(
    src_file: str, tgt_file: str, max_height=720, target_aspect=1.77777777778
) -> None:
    i_w, i_h = find_video_dims(src_file)
    crop_w = 0
    crop_h = 0
    o_w = 0
    o_h = 0
    i_aspect = float(i_w) / float(i_h)
    if i_aspect >= target_aspect:
        crop_w = i_w - (i_h * target_aspect)
        o_h = round(min(max_height, i_h))
    else:
        crop_h = i_h - (i_w * (1.0 / target_aspect))
        o_h = round(min(max_height, i_w * (1.0 / target_aspect)))
    o_w = int(o_h * target_aspect)
    if o_w % 2 != 0:
        o_w += 1  # ensure width is divisible by 2
    if o_h % 2 != 0:
        o_h += 1  # ensure height is divisible by 2
    os.makedirs(os.path.dirname(tgt_file), exist_ok=True)
    output_command = [
        "-y",
        "-filter:v",
        f"crop=iw-{crop_w:.0f}:ih-{crop_h:.0f},scale={o_w:.0f}:{o_h:.0f}",
        "-c:v",
        "libx264",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-ac",
        "1",
        "-loglevel",
        "quiet",
    ]
    ff = ffmpy.FFmpeg(
        inputs={str(src_file): None},
        outputs={str(tgt_file): tuple(i for i in output_command)},
    )
    ff.run()


# def slice_audio(
#     src_file: str, target_file: str, time_start: float, time_end: float
# ) -> None:
#     output_command = [
#         "-y",
#         "-ss",
#         f"{time_start}",
#         "-to",
#         f"{time_end}",
#         "-ac",
#         "1",
#         "-q:a",
#         "5",
#         "-loglevel",
#         "quiet",
#     ]
#     if target_file.endswith(".mp3"):
#         output_command.extend(["-acodec", "libmp3lame"])
#     os.makedirs(os.path.dirname(target_file), exist_ok=True)
#     ff = ffmpy.FFmpeg(
#         inputs={src_file: None}, outputs={target_file: tuple(i for i in output_command)}
#     )
#     ff.run()


def video_to_audio(input_file, output_file=None, output_audio_encoding="mp3") -> str:
    """
    Converts the .mp4 file to an audio file (.mp3 by default).
    This function is equivalent to running `ffmpeg -i input_file output_file -loglevel quiet` on the command line.

    Parameters:
    input_file: Examples are /example/path/to/session1/session1part1.mp4
    output_file: if not set, uses {input_file}.mp3

    Returns: path to the new audio file
    """
    if not os.path.exists(input_file):
        raise Exception(f"ERROR: Can't covert audio, {input_file} doesn't exist")
    input_base, input_ext = os.path.splitext(input_file)
    output_file = output_file or f"{input_base}.{output_audio_encoding}"
    output_command = "-loglevel quiet -y"
    ff = ffmpy.FFmpeg(
        inputs={str(input_file): None}, outputs={str(output_file): output_command}
    )
    ff.run()
    return output_file
