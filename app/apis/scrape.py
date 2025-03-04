import asyncio
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, status

router = APIRouter()
logger = logging.getLogger(__name__)


async def execute_scrapy_command(command: List[str]) -> Dict[str, str]:
    """
    Execute a Scrapy command as an async subprocess and return the results.

    Args:
        command: List of command parts to execute

    Returns:
        Dictionary containing stdout and stderr output

    Raises:
        asyncio.SubprocessError: If subprocess execution fails
    """
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    logger.info(f"Executing command: {' '.join(command)}")
    stdout, stderr = await process.communicate()

    logger.info(f"Command completed with return code: {process.returncode}")
    logger.info(f"Standard output: {stdout.decode()}")
    logger.info(f"Standard error: {stderr.decode()}")

    return {
        "returncode": process.returncode,
        "stdout": stdout.decode(),
        "stderr": stderr.decode(),
    }


def build_scrapy_command(url: str, line_user_id: str) -> List[str]:
    """
    Build the Scrapy command with the given parameters.

    Args:
        url: The URL of the apartment to scrape
        line_user_id: The LINE user ID for notification

    Returns:
        List of command parts
    """
    return [
        "scrapy",
        "runspider",
        "mansion_watch_scraper/spiders/suumo_scraper.py",
        "-a",
        f"url={url}",
        "-a",
        f"line_user_id={line_user_id}",
    ]


@router.get("/scrape", summary="Scrape the given apartment URL asynchronously")
async def start_scrapy(url: str, line_user_id: str) -> Dict[str, Any]:
    """
    Scrape the given apartment URL asynchronously using Scrapy.

    Args:
        url: The URL of the apartment to scrape
        line_user_id: The LINE user ID for notification

    Returns:
        Dictionary with scraping results

    Raises:
        HTTPException: If scraping fails
    """
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="URL parameter is required"
        )

    if not line_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LINE user ID parameter is required",
        )

    try:
        command = build_scrapy_command(url, line_user_id)
        logger.info(f"Starting Scrapy process for URL: {url}")

        result = await execute_scrapy_command(command)

        # Check for error messages in stderr
        stderr = result["stderr"]

        # Check for HTTP errors or other error messages in the output
        # We need to be careful to exclude log messages that just have ERROR as the log level
        if (
            "ERROR: HttpError on" in stderr
            or "HTTP Status Code: 404" in stderr
            or "HTTP Status Code: 403" in stderr
            or "HTTP Status Code: 500" in stderr
            or "ERROR: Property name not found" in stderr
            or "ValidationError" in stderr
            or "pydantic_core._pydantic_core.ValidationError" in stderr
            or result["returncode"]
            != 0  # Check if the process returned a non-zero exit code
        ):
            logger.error(f"Scrapy process encountered errors: {stderr}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Scrapy error: {stderr}",
            )

        logger.info(f"Scrapy process completed successfully for URL: {url}")
        return {
            "message": "Scrapy crawl and db insert completed successfully",
            "output": result["stdout"],
            "error": stderr,
            "success": True,
        }

    except asyncio.SubprocessError as e:
        logger.exception(f"Subprocess error while running Scrapy: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Subprocess error: {str(e)}",
        )

    except Exception as e:
        logger.exception(f"Unexpected error during scraping: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error: {str(e)}"
        )
