#!/usr/bin/env bash
set -e

STUDIO_PATH="/mnt/c/Rob AI Studio"
cd "$STUDIO_PATH"

source venv/bin/activate

echo "📦 Namestitev vseh 6 repozitorijev v editable (-e) načinu..."
pip install --upgrade pip setuptools wheel uv
pip install pydantic==2.7.1 fastapi==0.111.0 uvicorn pytest pytest-asyncio httpx networkx pyyaml sqlite-utils

for repo in repos/*; do
  if [ -d "$repo" ]; then
    echo "⚙️ Nameščam modul: $repo"
    pip install -e "$repo"
  fi
done

echo "✅ Vsi repozitoriji so bili uspešno nameščeni brez napak!"
