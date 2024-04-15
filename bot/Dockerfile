# pull official base image
FROM python:3.12-alpine

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

ENV BOT_HOME=/usr/src/bot

ENV LC_CTYPE='C.UTF-8'
ENV TZ='Asia/Tokyo'

RUN mkdir -p $BOT_HOME && \
    mkdir $BOT_HOME/staticfiles && \
    mkdir $BOT_HOME/mediafiles

# create the bot user
RUN addgroup -S bot && adduser -S bot -G bot

# set work directory
WORKDIR $BOT_HOME

RUN apk update && \
    apk add gcc python3-dev musl-dev libpq curl git tzdata ncdu libffi-dev && \
    pip install --upgrade pip && \
    pip install uv && \
    cp /usr/share/zoneinfo/Asia/Tokyo /etc/localtime

ENV VIRTUAL_ENV=/usr/local

ENV LANG ja_JP.UTF-8
ENV LANGUAGE ja_JP:ja
ENV LC_ALL ja_JP.UTF-8
ENV TZ JST-9

# install dependencies
COPY ./requirements.txt .

RUN uv pip install -r requirements.txt

# copy bot startup script
COPY ./bot.sh $BOT_HOME

# copy project
COPY . $BOT_HOME

# chown all the files to the bot user
RUN chown -R bot:bot $BOT_HOME

# change to the bot user
USER bot

# run bot startup script
CMD ["./bot.sh"]