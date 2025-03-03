# mansion_watch_scraper

## Run locally without docker

````bash
```python
python -m venv .venv
source .venv/bin/activate
make pip
````

## Run locally with docker

```bash
make run
```

## Enable ngrok

```bash
make ngrok
```

## Testing

### Run tests locally

```bash
# Activate virtual environment if not already activated
source .venv/bin/activate

# Run all tests
make test

# Run tests with coverage report
make test-cov
```

### Run tests in Docker

```bash
# Run all tests in Docker
make test-docker
```

### Testing Notes

- The test suite uses pytest with pytest-asyncio for testing asynchronous code
- Tests are configured to use function-scoped event loops for better isolation
- All tests run successfully in both local and Docker environments
- Current test coverage is approximately 66%
- Warnings are suppressed in Docker test runs using Python's `-W ignore` flag
- A custom fixture in conftest.py handles asyncio event loop cleanup properly
- All fixtures have proper type annotations and descriptive docstrings
- Fixtures that use context managers (with `yield`) are properly typed with `Generator[ReturnType, None, None]`

#### Test Structure and Best Practices

- **Type Annotations**: All test functions and fixtures use proper type hints for better code quality
  - Fixtures that use `yield` are properly typed with `Generator[ReturnType, None, None]`
  - Mock fixtures specify their exact return types (e.g., `MagicMock`, `AsyncMock`)
  - Tuple returns are explicitly typed as `tuple[Type1, Type2]`
- **Descriptive Docstrings**: Each test class and function includes detailed docstrings explaining its purpose
  - Fixture docstrings include information about what they mock and their return types
- **Arrange-Act-Assert Pattern**: Tests follow the AAA pattern (Given-When-Then) for clarity
- **Test Markers**: Tests are categorized using pytest markers (e.g., `@pytest.mark.webhook`)
- **Isolated Fixtures**: Each test class defines its own fixtures to maintain isolation
- **Functional Approach**: Tests follow functional programming principles with minimal state

#### Key Test Areas

- **URL Extraction**: Tests verify that URLs can be correctly extracted from messages, including cases with property names and URLs in the same message
- **URL Validation**: Tests ensure that only valid property URLs (e.g., from suumo.jp) are accepted
- **Webhook Handling**: Tests cover the full flow of receiving and processing webhook events from LINE
- **Error Handling**: Tests verify proper error handling for various scenarios, including invalid URLs and scraping failures
- **Message Processing**: Integration tests simulate the entire flow from receiving a message to initiating scraping

#### Test Exclusions in Docker

Some tests related to subprocess execution are excluded when running in Docker due to environment differences. These tests are still run in the local environment to ensure full coverage
