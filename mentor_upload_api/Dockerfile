FROM python:3.8
ENV STATUS_URL_FORCE_HTTPS=false
ADD requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
RUN rm /tmp/requirements.txt
ENV FLASK_APP=mentor_upload_api
WORKDIR /app
COPY src .
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]