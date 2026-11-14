FROM python:3.12-slim

WORKDIR /app

# Copy requirements first so Docker can cache this layer.
# Dependencies only reinstall when requirements.txt changes,
# not every time you edit app.py.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./

# Don't run as root inside the container
RUN useradd --create-home appuser
USER appuser

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]