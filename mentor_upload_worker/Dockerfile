FROM python:3.8-slim
ADD requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
RUN rm /tmp/requirements.txt
WORKDIR /app
COPY src/* .
COPY bin/training_worker.sh .
RUN chmod a+x training_worker.sh
ENTRYPOINT ["training_worker.sh"]
