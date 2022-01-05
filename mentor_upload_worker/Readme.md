# Running locally

Uploader uses https://ffmpy.readthedocs.io/en/latest/ to transcode videos for mobile and web. 
If you want to run it outside docker, you have to install ffmpeg locally first:


```bash
brew install ffmpeg
```

start redis:
```bash
docker run --name mentor  -d  -p 6363:6379 redis:6-alpine
```

You need .env, place it in `./src`.

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
