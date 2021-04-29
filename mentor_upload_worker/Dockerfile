FROM python:3.8-slim
WORKDIR /tmp
COPY requirements.txt .
RUN pip install -r requirements.txt
WORKDIR /app
COPY src/* .
COPY bin/training_worker.sh .
RUN chmod a+x training_worker.sh
ENTRYPOINT ["training_worker.sh"]
