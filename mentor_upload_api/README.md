# mentor-upload-api
dockerized REST api for the mentor upload

# Running and testing locally (outside docker)

You need .env, place it in `./src`.

Here's a VS Code launch config to debug locally outside docker:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "api-local",
            "type": "python",
            "request": "launch",
            "cwd": "${workspaceFolder}/mentor_upload_api/src",
            "env": {
                "LOG_LEVEL_UPLOAD_API": "DEBUG",
                "LOG_FORMAT_UPLOAD_API": "json",
                "FLASK_ENV": "development",
            },
            "program": "/opt/anaconda3/envs/mentorpal/bin/gunicorn",
            "gevent": true,
            "args": ["manage:app", "--bind=127.0.0.1:5555","-w", "1", "--timeout=320000"]
        }
    ]
}
```

To hit an endpoint:

```bash
curl -v  -F body='{"mentor":"6196af5e068d43dc686194f8","question":"6098b41257ab183da46cf777"}' -F video=@celery-short.mp4  'http://localhost:5000/upload/answer'
```

## Licensing

All source code files must include a USC open license header.

To check if files have a license header:

```
make test-license
```

To add license headers:

```
make license
```
