from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.apis.scrape import build_scrapy_command, execute_scrapy_command, start_scrapy


class TestExecuteScrapyCommand:
    @pytest.fixture
    def mock_subprocess(self) -> Generator[tuple[AsyncMock, AsyncMock], None, None]:
        """
        Mock the asyncio.create_subprocess_exec function.

        Returns:
            Generator[tuple[AsyncMock, AsyncMock], None, None]: A tuple containing the mock subprocess and process
        """
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            process_mock = AsyncMock()
            process_mock.returncode = 0
            process_mock.communicate.return_value = (b"stdout output", b"stderr output")
            mock_subprocess.return_value = process_mock
            yield mock_subprocess, process_mock

    async def test_execute_scrapy_command_success(self, mock_subprocess):
        mock_subprocess_exec, mock_process = mock_subprocess

        command = [
            "scrapy",
            "runspider",
            "mansion_watch_scraper/spiders/suumo_scraper.py",
            "-a",
            "url=https://example.com",
        ]
        result = await execute_scrapy_command(command)

        # Check that subprocess was called with the correct command
        mock_subprocess_exec.assert_called_once()
        assert mock_subprocess_exec.call_args[0] == tuple(command)

        # Check that communicate was called
        mock_process.communicate.assert_called_once()

        # Check the result
        assert result["returncode"] == 0
        assert result["stdout"] == "stdout output"
        assert result["stderr"] == "stderr output"

    async def test_execute_scrapy_command_error(self, mock_subprocess):
        mock_subprocess_exec, mock_process = mock_subprocess

        # Configure the mock to simulate a failed command
        mock_process.returncode = 1

        command = [
            "scrapy",
            "runspider",
            "mansion_watch_scraper/spiders/suumo_scraper.py",
            "-a",
            "url=https://example.com",
        ]
        result = await execute_scrapy_command(command)

        # Check that subprocess was called with the correct command
        mock_subprocess_exec.assert_called_once()

        # Check the result
        assert result["returncode"] == 1
        assert result["stdout"] == "stdout output"
        assert result["stderr"] == "stderr output"


class TestBuildScrapyCommand:
    def test_build_scrapy_command(self):
        url = "https://suumo.jp/chintai/jnc_000056437301/"
        line_user_id = "test_user_id"

        command = build_scrapy_command(url, line_user_id)

        # Check that the command is correctly built
        assert command[0] == "scrapy"
        assert command[1] == "runspider"
        assert command[2] == "mansion_watch_scraper/spiders/suumo_scraper.py"
        assert "-a" in command
        assert f"url={url}" in command
        assert f"line_user_id={line_user_id}" in command


class TestStartScrapy:
    @pytest.fixture
    def mock_execute_scrapy_command(self) -> Generator[AsyncMock, None, None]:
        """
        Mock the execute_scrapy_command function.

        Returns:
            Generator[AsyncMock, None, None]: A mock of the execute_scrapy_command function
        """
        with patch("app.apis.scrape.execute_scrapy_command") as mock_execute:
            mock_execute.return_value = {
                "returncode": 0,
                "stdout": "Scraping completed successfully",
                "stderr": "",
            }
            yield mock_execute

    @pytest.fixture
    def mock_build_scrapy_command(self) -> Generator[MagicMock, None, None]:
        """
        Mock the build_scrapy_command function.

        Returns:
            Generator[MagicMock, None, None]: A mock of the build_scrapy_command function
        """
        with patch("app.apis.scrape.build_scrapy_command") as mock_build:
            mock_build.return_value = [
                "scrapy",
                "runspider",
                "mansion_watch_scraper/spiders/suumo_scraper.py",
                "-a",
                "url=test_url",
                "-a",
                "line_user_id=test_user",
            ]
            yield mock_build

    async def test_start_scrapy_success(
        self, mock_execute_scrapy_command, mock_build_scrapy_command
    ):
        url = "https://suumo.jp/chintai/jnc_000056437301/"
        line_user_id = "test_user_id"

        result = await start_scrapy(url=url, line_user_id=line_user_id)

        # Check that build_scrapy_command was called with the correct parameters
        mock_build_scrapy_command.assert_called_once_with(url, line_user_id)

        # Check that execute_scrapy_command was called with the result of build_scrapy_command
        mock_execute_scrapy_command.assert_called_once_with(
            [
                "scrapy",
                "runspider",
                "mansion_watch_scraper/spiders/suumo_scraper.py",
                "-a",
                "url=test_url",
                "-a",
                "line_user_id=test_user",
            ]
        )

        # Check the result
        assert "message" in result
        assert result["message"] == "Scrapy crawl and db insert completed successfully"

    async def test_start_scrapy_404_error(
        self, mock_execute_scrapy_command, mock_build_scrapy_command
    ):
        # Configure the mock to simulate a 404 error
        mock_execute_scrapy_command.return_value = {
            "returncode": 0,  # Note: 404 errors don't cause a non-zero return code in our implementation
            "stdout": "",
            "stderr": "2025-03-05 10:55:03 [mansion_watch_scraper] INFO: HTTP Status Code: 404\n2025-03-05 10:55:03 [mansion_watch_scraper] INFO: Property not found (404). The URL may be incorrect or the property listing may have been removed.",
        }

        url = "https://suumo.jp/ms/chuko/tokyo/sc_shinjuku/nc_98246732/"
        line_user_id = "test_user_id"

        result = await start_scrapy(url=url, line_user_id=line_user_id)

        # Check that build_scrapy_command was called with the correct parameters
        mock_build_scrapy_command.assert_called_once_with(url, line_user_id)

        # Check that execute_scrapy_command was called with the result of build_scrapy_command
        mock_execute_scrapy_command.assert_called_once_with(
            [
                "scrapy",
                "runspider",
                "mansion_watch_scraper/spiders/suumo_scraper.py",
                "-a",
                "url=test_url",
                "-a",
                "line_user_id=test_user",
            ]
        )

        # Check the result
        assert "message" in result
        assert result["message"] == "Property not found"
        assert result["status"] == "not_found"
        assert result["url"] == url
        assert "error" in result
        assert "404 status code" in result["error"]

    async def test_start_scrapy_error(
        self, mock_execute_scrapy_command, mock_build_scrapy_command
    ):
        # Configure the mock to simulate a failed command
        mock_execute_scrapy_command.return_value = {
            "returncode": 1,
            "stdout": "",
            "stderr": "Error: Spider not found",
        }

        url = "https://suumo.jp/chintai/jnc_000056437301/"
        line_user_id = "test_user_id"

        # Mock the asyncio.SubprocessError to avoid the attribute error
        with patch("app.apis.scrape.asyncio") as mock_asyncio:
            # Create a custom exception class for testing
            class MockSubprocessError(Exception):
                pass

            # Set the SubprocessError attribute on the mock
            mock_asyncio.SubprocessError = MockSubprocessError

            # The function should raise an HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await start_scrapy(url=url, line_user_id=line_user_id)

            # Check the exception
            assert exc_info.value.status_code == 500
            assert "Scrapy error" in exc_info.value.detail
