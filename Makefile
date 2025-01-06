.PHONY: run
run: ## Start the development docker container.
	docker compose up --build -d

.PHONY: down
down: ## Stop the development docker container.
	docker compose down

.PHONY: lint
format: ## Format the code.
	docker compose exec scall-backend isort app && docker compose exec scall-backend black app && docker compose exec scall-backend flake8 app

.PHONY: deploy
deploy: ## Deploy the application to Heroku.
	gcloud app deploy

.PHONY: pipi
pipi: ## Install the dependencies.
	pip install -r requirements.txt

# TODO: Tweak this to work with a proper file
.PHONY: scrape
scrape: ## Run the scraper.
	scrapy runspider sample_scraper.py
