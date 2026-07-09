FROM gorialis/discord.py:3.12.2-alpine-pypi-minimal

COPY requirements.txt /usr/src/app/requirements.txt
WORKDIR /usr/src/app
RUN pip install -r requirements.txt
COPY src/ ./
COPY token.txt .

CMD ["python", "./main.py"]

