FROM python:3.8-slim
RUN apt-get update && \
    apt-get install -y \
    build-essential \
    ffmpeg \
    libcurl4-openssl-dev \
    libssl-dev \
    mediainfo \
    && rm -rf /var/lib/apt/lists/*
ADD requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt \
    && pip uninstall pycurl \
    && pip install pycurl --compile --global-option="--with-openssl" --no-cache-dir
RUN rm /tmp/requirements.txt
WORKDIR /app
COPY src ./
ADD bin/entrypoint.sh .
RUN chmod a+x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
