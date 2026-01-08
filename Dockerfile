FROM python:3.11-slim

WORKDIR /app

# System dependencies, locale ayarları ve fontlar
RUN apt-get update && apt-get install -y \
    libmagic1 \
    locales \
    fonts-dejavu-core \
    fonts-freefont-ttf \
    fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && sed -i '/tr_TR.UTF-8/s/^# //g' /etc/locale.gen \
    && locale-gen \
    && fc-cache -f -v

# Türkçe locale ve UTF-8 encoding
ENV LANG=tr_TR.UTF-8
ENV LC_ALL=tr_TR.UTF-8
ENV PYTHONIOENCODING=utf-8

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create upload directories
RUN mkdir -p /app/uploads/pdfs /app/uploads/logos

# Expose port
EXPOSE 8000

# Run
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
