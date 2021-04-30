FROM python:3.8-slim
RUN apt-get update && \
    apt-get install -y \
    ffmpeg \
    git \
    mediainfo \
    && rm -rf /var/lib/apt/lists/*
ADD requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
RUN rm /tmp/requirements.txt
WORKDIR /app
COPY src ./
ADD bin/entrypoint.sh .
RUN chmod a+x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
