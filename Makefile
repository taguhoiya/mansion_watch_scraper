.PHONY: run
run: ## Start the development docker container.
	docker compose up --build -d

.PHONY: down
down: ## Stop the development docker container.
	docker compose down

.PHONY: lint
lint: ## Format the code.
	docker compose exec mansion_watch_scraper isort . && docker compose exec mansion_watch_scraper black . && docker compose exec mansion_watch_scraper flake8 .

.PHONY: deploy
deploy: ## Deploy the application to Heroku.
	gcloud app deploy

.PHONY: pip
pip: ## Install the dependencies.
	pip install -r requirements.txt

# TODO: Tweak this to work with a proper file
.PHONY: scrape
scrape: ## Run the scraper.
	@source .env && scrapy runspider mansion_watch_scraper/spiders/suumo_scraper.py -a url="https://suumo.jp/ms/chuko/tokyo/sc_meguro/nc_75709932/"

.PHONY: ngrok
ngrok: ## Start ngrok.
	ngrok http http://localhost:8080
