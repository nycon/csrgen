FROM python:3.12-slim

LABEL maintainer="CSRgen"
LABEL description="CSR Generator - TLS/SSL Certificate Signing Request Tool"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

RUN useradd -r -s /bin/false csrgen
USER csrgen

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "30", "app:app"]
