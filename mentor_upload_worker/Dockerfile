FROM python:3.8-slim
ADD requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
RUN rm /tmp/requirements.txt
WORKDIR /app
COPY src/* ./
COPY bin/entrypoint.sh .
RUN chmod a+x entrypoint.sh
ENTRYPOINT ["entrypoint.sh"]
