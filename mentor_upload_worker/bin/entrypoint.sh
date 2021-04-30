#!/usr/bin/env bash
celery --app mentor_upload_tasks.tasks.celery worker --loglevel=INFO
