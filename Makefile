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
	scrapy runspider mansion_watch_scraper/spiders/suumo_scraper.py -a url="https://suumo.jp/ms/chuko/tokyo/sc_meguro/nc_75709932/" -a line_user_id="U23b619197d01bab29b2c54955db6c2a1"

.PHONY: ngrok
ngrok: ## Start ngrok.
	ngrok http http://localhost:8080

.PHONY: test
test: ## Run the tests.
	python -W ignore -m pytest tests/unit/ -v

.PHONY: test-cov
test-cov: ## Run the tests with coverage report.
	python -W ignore -m pytest tests/unit/ -v

.PHONY: test-docker
test-docker: ## Run the tests in the docker container.
	docker compose exec mansion_watch_scraper python -W ignore -m pytest tests/unit/ -v || true
