from mentor_upload_process.process import process_answer_video


def test_transcribes_mentor_answer():
    req = {"mentor": "m1", "question": "q1", "video_path": "video1.mp4"}
    assert process_answer_video(req) == req


def test_raises_if_video_path_not_specified():
    req = {"mentor": "m1", "question": "q1"}
    caught_exception = None
    try:
        process_answer_video(req)
    except Exception as err:
        caught_exception = err
    assert caught_exception is not None
    assert str(caught_exception) == "missing required param 'video_path'"
