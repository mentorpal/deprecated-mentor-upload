# Running locally

Uploader uses https://ffmpy.readthedocs.io/en/latest/ to transcode videos for mobile and web. 
Install ffmpeg locally first:

```bash
brew install ffmpeg
```

## Asynchronous triggers

In order to run handlers for asynchronous event triggers locally, e.g. events fired by `SNS` or `SQS`, execute `sls invoke --local -f <function>`. To define a custom event payload, create a `*event.json` file and point to its path with `sls invoke --local -f <function> -p <path_to_event.json>`. Be sure to commit a `.dist` version of it for other developers to be used.

**Example**

```
answer-transcribe.py -> handler to test
answer-event.event.json -> your local copy of event.json.dist, which is ignored by git
answer-event.event.json.dist -> reference event for other developers to be copied and used locally
```

Here's a VS Code launch config to debug locally outside docker:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "upload-worker-local",
            "type": "python",
            "request": "launch",
            "cwd": "${workspaceFolder}/mentor_upload_worker/src",
            "env": {
                "LOG_LEVEL_UPLOAD_API": "DEBUG",
                "LOG_FORMAT_UPLOAD_API": "json",
                "FLASK_ENV": "development",
            },
            "program": "/opt/anaconda3/envs/mentorpal/bin/celery",
            "gevent": true,
            "args": ["--app", "mentor_upload_tasks.tasks.celery", "worker", "--loglevel","DEBUG"]
        }
    ]
}
```
