import subprocess

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/scrape", summary="Scrape the given apartment URL asynchronously")
async def start_scrapy(url: str):
    """
    Scrape the given apartment URL asynchronously using Scrapy.
    url: str: The URL of the apartment to scrape.
    """
    try:
        # Define the Scrapy command
        command = [
            "scrapy",
            "runspider",
            "mansion_watch_scraper/spiders/suumo_scraper.py",
            "-a",
            f"url={url}",
        ]

        # Run Scrapy as a subprocess
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        # Wait for the process to complete
        stdout, stderr = process.communicate()

        # Capture the output and error messages
        if process.returncode != 0:
            raise HTTPException(
                status_code=500, detail=f"Scrapy error: {stderr.decode()}"
            )

        # Return the result or logs from the Scrapy process
        return {
            "message": "Scrapy crawl and db insert completed successfully",
            "output": stdout.decode(),
            "error": stderr.decode(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
