#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
import logging
import os
import re
import math
from pymediainfo import MediaInfo

log = logging.getLogger()


def find_duration(audio_or_video_file: str) -> float:
    log.info(audio_or_video_file)
    media_info = MediaInfo.parse(audio_or_video_file)
    for t in media_info.tracks:
        if t.track_type in ["Video", "Audio"]:
            try:
                log.debug(t)
                return float(t.duration / 1000)
            except Exception:
                pass
    return -1.0


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
