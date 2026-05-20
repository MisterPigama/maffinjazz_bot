# 📄 файл: Dockerfile

FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости отдельно для кэширования слоёв
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

CMD ["python", "main.py"]