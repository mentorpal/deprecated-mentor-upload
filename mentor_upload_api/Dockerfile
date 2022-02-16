FROM python:3.8-slim
ENV STATUS_URL_FORCE_HTTPS=false
RUN apt-get update && \
    apt-get install -y ffmpeg

ADD requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt \
    && rm -rf /tmp/requirements.txt \
    && apt-get install -y libmediainfo0v5 

ENV FLASK_APP=mentor_upload_api
WORKDIR /app
COPY src .
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
