FROM python:3.10
WORKDIR /TelegramBotPython
COPY requirements.txt /TelegramBotPython/
RUN pip install -r requirements.txt
COPY . /TelegramBotPython
CMD python telegramBot.py