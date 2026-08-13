.PHONY: setup test run-gateway docker-up docker-down self-check dashboard

setup:
	bash setup_rob_ai_studio.sh
test:
	pytest -v tests/
run-gateway:
	uvicorn actions.enterprise_api_gateway.main:app --reload --port 8000
docker-up:
	docker-compose up -d --build
docker-down:
	docker-compose down
self-check:
	python3 core/system_self_check.py
dashboard:
	python3 core/dashboard_tui.py
