FROM python:3.11-slim

# Nastavitev delovnega okolja
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Namestitev sistemskih odvisnosti
RUN apt-get update && apt-get install -y git build-essential && rm -rf /var/lib/apt/lists/*

# Kopiranje projekta
COPY . /app/

# Namestitev Python paketov in repozitorijev v editable načinu
RUN pip install --upgrade pip uv wheel && \
    pip install pydantic==2.7.1 fastapi==0.111.0 uvicorn pytest pytest-asyncio httpx networkx pyyaml sqlite-utils python-dotenv pydantic-settings && \
    for repo in repos/*; do if [ -d "$repo" ]; then pip install -e "$repo"; fi; done

# Zagon krovnega API Gatewaya privzeto
CMD ["uvicorn", "actions.enterprise_api_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
