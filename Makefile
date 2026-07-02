# SaviorBill — удобные цели для разработки, тестов и прод-запуска.
#
#   make setup      — подготовить deploy/.env и запустить (прод)
#   make dev        — dev-стек со сборкой из исходников
#   make dev-down   — остановить dev-стек и удалить тома
#   make test       — полный прогон тестов (unit+integration в докере)
#   make test-down  — снять тестовый стек
#   make prod       — прод-стек из образов реестра (docker compose up -d)
#   make prod-down  — остановить прод-стек
#   make unit       — быстрые юнит-тесты billing локально
#   make mw-unit    — юнит-тесты mediaworker локально
#   make fmt        — формат Black по всем пакетам

PROD := docker compose -f deploy/docker-compose.yml
DEV  := docker compose -f deploy/dev/docker-compose.yml
TEST := docker compose -f deploy/dev/docker-compose.yml -f deploy/test/docker-compose.yml

.PHONY: setup dev dev-down test test-down prod prod-down unit mw-unit fmt logs

setup:
	bash deploy/setup.sh

dev:
	$(DEV) up --build

dev-down:
	$(DEV) down -v

test:
	$(TEST) up --build --abort-on-container-exit --exit-code-from tests

test-down:
	$(TEST) down -v

prod:
	$(PROD) pull && $(PROD) up -d

prod-down:
	$(PROD) down

unit:
	PYTHONPATH=src DB_PASS=ci JWT_SECRET=ci-secret-ci-secret-ci-secret-32 pytest -c deploy/test/pytest.ini --rootdir=. -m unit

mw-unit:
	cd mediaworker && PYTHONPATH=src pytest -q

fmt:
	black src tests migrations mediaworker

logs:
	$(PROD) logs -f
