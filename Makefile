.PHONY: up down logs test

# Build and start the whole stack: backend :8000, frontend :3000
up:
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example - add real LLM_API_KEYS to it.")
	docker compose up --build -d
	@echo "Frontend: http://localhost:3000   Backend: http://localhost:8000/health"

# Stop the stack (the named volume with the SQLite file is kept)
down:
	docker compose down

logs:
	docker compose logs -f

test:
	cd backend && python -m pytest -q
