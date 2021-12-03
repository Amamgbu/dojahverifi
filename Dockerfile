FROM python:3.8.1

ENV APP_HOME /app
WORKDIR $APP_HOME

COPY . /app

RUN pip3 install Flask
RUN pip3 install boto3
RUN pip3 install python-dotenv
RUN pip3 install flask-restx
RUN pip3 install botocore
RUN pip3 install flask-restplus
RUN pip install -r requirements.txt

ENTRYPOINT ["python app.py"]