BIN := .venv/bin

.DEFAULT_GOAL := help
.PHONY: help setup routing page page-offline open lint format test check bump clean

help: ## Mostra questo elenco
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Crea il virtualenv con quello che serve per sviluppare
	python3 -m venv .venv
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q "pytest>=8.2,<9.0" "ruff>=0.6,<0.7"
	@echo "fatto. Metti BOT_TOKEN in .env per vedere numeri e foto."

routing: ## Riscarica gruppi e topic dal repo del bot (serve gh, o fallo a mano)
	@gh api repos/Soli-su-Git/solizia/contents/public/routing.json \
		-H "Accept: application/vnd.github.raw" > data/routing.json \
		&& echo "data/routing.json aggiornato" \
		|| echo "non ci sono riuscito: copia a mano public/routing.json dal repo del bot"

page: ## Costruisce la pagina in site/ con i dati freschi (serve BOT_TOKEN)
	@$(BIN)/python build_page.py

page-offline: ## Costruisce la pagina senza chiamare Telegram (niente numeri né foto)
	@$(BIN)/python build_page.py --offline

open: page ## Costruisce la pagina e la apre nel browser
	@open site/index.html

lint: ## Controlla stile ed errori statici
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

format: ## Formatta il codice e sistema gli import
	$(BIN)/ruff check --fix .
	$(BIN)/ruff format .

test: ## Esegue i test
	$(BIN)/pytest

check: lint test ## Lint + test (quello che gira in CI)

bump: ## Alza la versione della pagina (MESSAGE="feat: ...")
	@$(BIN)/python bump.py --message "$(MESSAGE)"

clean: ## Rimuove cache e pagina costruita
	rm -rf site stats.json .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
