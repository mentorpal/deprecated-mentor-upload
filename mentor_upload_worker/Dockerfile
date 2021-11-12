FROM python:3.8-slim as builder
# To use celery over AWS SQS requires pycurl
# and it doesn't work unless it's compiled,
# which requires hundreds of MB of build tools...
# So we do a two-phase docker build.
# In the first phase, we compile pycurl
# as a wheel, and then in the final phase,
# we install from that wheel (to avoid needing the build tools)
RUN apt-get update && \
    apt-get install -y \
        build-essential \
        libcurl4-openssl-dev \
        libssl-dev \
    && pip install wheel \
    && pip wheel \
            --wheel-dir=/svc/wheels \
            --no-binary :all: \
            --global-option="--with-openssl" \
            --no-cache-dir \
        pycurl
FROM python:3.8-slim
COPY --from=builder /svc /svc
WORKDIR /svc
ADD requirements.txt /tmp/requirements.txt
RUN apt-get update && \
    apt-get install -y \
        ffmpeg \
        libcurl4-openssl-dev \
        libssl-dev \
        mediainfo \
    && pip install -r /tmp/requirements.txt --extra-index-url https://test.pypi.org/simple/ \
    && pip uninstall pycurl \
    && pip install --no-index --find-links=/svc/wheels pycurl \
    && rm -rf /var/lib/apt/lists/*
RUN rm /tmp/requirements.txt
WORKDIR /app
COPY src ./
ADD bin/entrypoint.sh .
RUN chmod a+x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
