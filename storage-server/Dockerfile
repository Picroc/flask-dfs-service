FROM python:3.7.4
ADD . /app
RUN mkdir buffer
WORKDIR /app
EXPOSE 4000
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
ENTRYPOINT ["python","index.py"]