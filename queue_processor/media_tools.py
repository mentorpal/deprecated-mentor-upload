#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved. 
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
from dataclasses import dataclass
import logging
import os
import re
from typing import List, Optional, Tuple, Union
import math
import ffmpy
from pymediainfo import MediaInfo


LIB_FILE = os.environ.get(
    "MEDIAINFO_LIB", "/opt/MediaInfo_DLL_21.09_Lambda/lib/libmediainfo.so"
)
FFMPEG_EXECUTABLE = os.environ.get("FFMPEG_EXECUTABLE", "/opt/ffmpeg/ffmpeg")

log = logging.getLogger("media-tools")


def find_duration(audio_or_video_file: str) -> float:
    log.info(audio_or_video_file)
    media_info = MediaInfo.parse(audio_or_video_file, library_file=LIB_FILE)
    for t in media_info.tracks:
        if t.track_type in ["Video", "Audio"]:
            try:
                log.debug(t)
                return float(t.duration / 1000)
            except Exception:
                pass
    return -1.0


def find_video_dims(video_file: str) -> Tuple[int, int]:
    log.info(video_file)
    media_info = MediaInfo.parse(video_file, library_file=LIB_FILE)
    video_tracks = [t for t in media_info.tracks if t.track_type == "Video"]
    log.debug(video_tracks)
    return (
        (video_tracks[0].width, video_tracks[0].height)
        if len(video_tracks) >= 1
        else (-1, -1)
    )


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


def output_args_video_encode_for_mobile(
    src_file: str, target_height=480, video_dims: Optional[Tuple[int, int]] = None
) -> Tuple[str, ...]:
    i_w, i_h = video_dims or find_video_dims(src_file)
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
    return (
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
    )


def output_args_video_encode_for_web(
    src_file: str,
    max_height=720,
    target_aspect=1.77777777778,
    video_dims: Optional[Tuple[int, int]] = None,
) -> Tuple[str, ...]:
    i_w, i_h = video_dims or find_video_dims(src_file)
    crop_w = 0
    crop_h = 0
    o_w = 0
    o_h = 0
    i_aspect = float(i_w) / float(i_h)
    if i_aspect >= target_aspect:
        crop_w = i_w - (i_h * target_aspect)
        o_h = round(min(max_height, i_h))
    else:
        o_h = round(min(max_height, i_w * (1.0 / target_aspect)))
    o_w = int(o_h * target_aspect)
    if o_w % 2 != 0:
        o_w += 1  # ensure width is divisible by 2
    if o_h % 2 != 0:
        o_h += 1  # ensure height is divisible by 2
    return (
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
    )


def output_args_video_to_audio() -> Tuple[str, ...]:
    return ("-loglevel", "quiet", "-y")


def video_encode_for_mobile(src_file: str, tgt_file: str, target_height=480) -> None:
    log.info("%s, %s, %s", src_file, tgt_file, target_height)

    ff = ffmpy.FFmpeg(
        inputs={str(src_file): None},
        outputs={
            str(tgt_file): output_args_video_encode_for_mobile(
                src_file, target_height=target_height
            )
        },
        executable=FFMPEG_EXECUTABLE,
    )
    ff.run()
    log.debug(ff)


def video_encode_for_web(
    src_file: str, tgt_file: str, max_height=720, target_aspect=1.77777777778
) -> None:
    log.info("%s, %s, %s, %s", src_file, tgt_file, max_height, target_aspect)
    os.makedirs(os.path.dirname(tgt_file), exist_ok=True)
    ff = ffmpy.FFmpeg(
        inputs={str(src_file): None},
        outputs={
            str(tgt_file): output_args_video_encode_for_web(
                src_file, max_height=max_height, target_aspect=target_aspect
            )
        },
        executable=FFMPEG_EXECUTABLE,
    )
    ff.run()
    log.debug(ff)


def video_to_audio(
    input_file: str, output_file: str = "", output_audio_encoding="mp3"
) -> str:
    """
    Converts the .mp4 file to an audio file (.mp3 by default).
    This function is equivalent to running `ffmpeg -i input_file output_file -loglevel quiet` on the command line.

    Parameters:
    input_file: Examples are /example/path/to/session1/session1part1.mp4
    output_file: if not set, uses {input_file}.mp3

    Returns: path to the new audio file
    """
    log.info("%s, %s, %s", input_file, output_file, output_audio_encoding)

    output_file = (
        output_file or f"{os.path.splitext(input_file)[0]}.{output_audio_encoding}"
    )
    ff = ffmpy.FFmpeg(
        inputs={str(input_file): None},
        outputs={str(output_file): output_args_video_to_audio()},
        executable=FFMPEG_EXECUTABLE,
    )
    ff.run()
    log.debug(ff)
    return output_file


def video_trim(
    input_file: str, output_file: str, start_secs: float, end_secs: float
) -> None:
    log.info("%s, %s, %s-%s", input_file, output_file, start_secs, end_secs)
    # couldnt get to output to stdout like here
    # https://aws.amazon.com/blogs/media/processing-user-generated-content-using-aws-lambda-and-ffmpeg/
    ff = ffmpy.FFmpeg(
        inputs={str(input_file): None},
        outputs={str(output_file): output_args_trim_video(start_secs, end_secs)},
        executable=FFMPEG_EXECUTABLE,
    )
    ff.run()
    log.debug(ff)


def existing_video_trim(
    input_file: str, output_file: str, start_secs: float, end_secs: float
) -> None:
    log.info("%s, %s, %s-%s", input_file, output_file, start_secs, end_secs)
    ff = ffmpy.FFmpeg(
        inputs={str(input_file): None},
        outputs={str(output_file): output_args_trim_video(start_secs, end_secs)},
        executable=FFMPEG_EXECUTABLE,
    )
    ff.run()
    log.debug(ff)


def find(
    s: str, ch: str
):  # gives indexes of all of the spaces so we don't split words apart
    return [i for i, ltr in enumerate(s) if ltr == ch]


def transcript_to_vtt(
    audio_or_video_file_or_url: str, vtt_file: str, transcript: str
) -> str:
    log.info("%s, %s, %s", audio_or_video_file_or_url, vtt_file, transcript)

    if not os.path.exists(audio_or_video_file_or_url) and not re.search(
        "^https?", audio_or_video_file_or_url
    ):
        raise Exception(
            f"ERROR: Can't generate vtt, {audio_or_video_file_or_url} doesn't exist or is not a valid url"
        )
    duration = find_duration(audio_or_video_file_or_url)
    log.debug(duration)
    if duration <= 0:
        log.warning(f"video duration for {audio_or_video_file_or_url} returned 0")
        return ""
    piece_length = 68
    word_indexes = find(transcript, " ")
    split_index = [0]
    for k in range(1, len(word_indexes)):
        for el in range(1, len(word_indexes)):
            if word_indexes[el] > piece_length * k:
                split_index.append(word_indexes[el])
                break
    split_index.append(len(transcript))
    log.debug(split_index)
    amount_of_chunks = math.ceil(len(transcript) / piece_length)
    log.debug(amount_of_chunks)
    vtt_str = "WEBVTT FILE:\n\n"
    for j in range(len(split_index) - 1):  # this uses a constant piece length
        seconds_start = round((duration / amount_of_chunks) * j, 2) + 0.85
        seconds_end = round((duration / amount_of_chunks) * (j + 1), 2) + 0.85
        output_start = (
            str(math.floor(seconds_start / 60)).zfill(2)
            + ":"
            + ("%.3f" % (seconds_start % 60)).zfill(6)
        )
        output_end = (
            str(math.floor(seconds_end / 60)).zfill(2)
            + ":"
            + ("%.3f" % (seconds_end % 60)).zfill(6)
        )
        vtt_str += f"00:{output_start} --> 00:{output_end}\n"
        vtt_str += f"{transcript[split_index[j] : split_index[j + 1]]}\n\n"
    os.makedirs(os.path.dirname(vtt_file), exist_ok=True)
    with open(vtt_file, "w") as f:
        f.write(vtt_str)
    log.debug(vtt_str)
    return vtt_str


@dataclass
class TimestampSegment:
    secs_start: float
    secs_end: float
    transcript_segment: str


def vtt_str_file_to_objects(vtt_str_file) -> List[TimestampSegment]:
    timestamp_segs = []
    vtt_file = open(vtt_str_file, "r")
    line = vtt_file.readline()
    while line:
        if re.search("^00:", line):
            timestamp_split = line.split(" --> ")
            start_duration = timestamp_split[0]
            (
                start_hours,
                start_minutes,
                start_seconds,
            ) = start_duration.split(":")
            end_duration = timestamp_split[1]
            (
                end_hours,
                end_minutes,
                end_seconds,
            ) = end_duration.split(":")
            timestamp_segs.append(
                TimestampSegment(
                    float(start_minutes) * 60 + float(start_seconds),
                    float(end_minutes) * 60 + float(end_seconds),
                    vtt_file.readline().strip(),
                )
            )
        line = vtt_file.readline()
    vtt_file.close()
    return timestamp_segs


def trim_vtt_and_transcript_via_timestamps(
    vtt_str_file: str, trim_start_secs: float, trim_end_secs: float
):
    timestamp_segs = vtt_str_file_to_objects(vtt_str_file)
    # Removes timestamp segments that come after the new end of the video
    # In the future, should also accomodate for the user trimming the start of the video
    for timestamp_seg in timestamp_segs[:]:
        if timestamp_seg.secs_start >= trim_end_secs:
            timestamp_segs.remove(timestamp_seg)

    new_vtt_str = "WEBVTT FILE:\n\n"
    new_transcript = ""
    for timestamp_seg in timestamp_segs:
        output_start = (
            str(math.floor(timestamp_seg.secs_start / 60)).zfill(2)
            + ":"
            + ("%.3f" % (timestamp_seg.secs_start % 60)).zfill(6)
        )
        output_end = (
            str(math.floor(timestamp_seg.secs_end / 60)).zfill(2)
            + ":"
            + ("%.3f" % (timestamp_seg.secs_end % 60)).zfill(6)
        )
        new_vtt_str += f"00:{output_start} --> 00:{output_end}\n"
        new_vtt_str += f"{timestamp_seg.transcript_segment}\n\n"
        new_transcript += f"{timestamp_seg.transcript_segment} "
    new_transcript = new_transcript.strip()

    vtt_file = open(vtt_str_file, "w")
    vtt_file.write(new_vtt_str)
    vtt_file.close()
    return new_vtt_str, new_transcript
