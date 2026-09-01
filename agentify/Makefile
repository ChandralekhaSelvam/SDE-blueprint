.PHONY: install demo backend frontend test lint build clean

install:
	cd backend && pip install -r requirements-dev.txt
	cd frontend && npm install

demo:
	@echo "Backend on :8000, frontend on :5173. Ctrl-C stops both."
	cd backend && RUN_MODE=demo LLM_PROVIDER=mock uvicorn app.main:app --port 8000 --reload & \
	cd frontend && npm run dev

backend:
	cd backend && uvicorn app.main:app --port 8000 --reload

frontend:
	cd frontend && npm run dev

test:
	cd backend && python -m pytest tests -q

lint:
	cd backend && ruff check app tests
	cd frontend && npx tsc --noEmit

build:
	cd frontend && npm run build

mock-data:
	cd backend && python tests/make_mock_data.py

clean:
	rm -rf backend/data frontend/dist frontend/node_modules
