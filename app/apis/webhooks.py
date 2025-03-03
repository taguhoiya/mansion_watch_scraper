import asyncio
import logging
import os
import re
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, status
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
)
from linebot.v3.messaging import TextMessage as TextMessageSend
from linebot.v3.webhooks import FollowEvent, MessageEvent
from linebot.v3.webhooks.models.text_message_content import TextMessageContent

from app.apis.scrape import start_scrapy
from app.db.session import get_db
from app.models.apis.webhook import WebhookResponse
from app.services.dates import get_current_time

router = APIRouter()
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET", ""))
logger = logging.getLogger(__name__)

# Configure LINE messaging API client
configuration = Configuration(access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN", ""))


@router.post(
    "/webhook",
    summary="Process LINE webhook events",
    response_description="Webhook processing status",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
)
async def webhook_message_handler(request: Request) -> WebhookResponse:
    """
    Process incoming LINE webhook events.

    This endpoint receives webhook events from LINE and processes them
    according to their type (message, follow, etc.).
    """
    # Get X-Line-Signature header value
    signature = request.headers.get("X-Line-Signature")
    if not signature:
        logger.error("Missing X-Line-Signature header")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature header"
        )

    # Get request body as text
    body = await request.body()
    body_text = body.decode("utf-8")

    # Handle webhook body
    try:
        handler.handle(body_text, signature)
    except InvalidSignatureError:
        logger.error(
            "Invalid signature. Please check your channel access token/channel secret."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature"
        )
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing webhook",
        )

    return WebhookResponse(message="Webhook message received!")


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event: MessageEvent) -> None:
    """
    Handle text message events from LINE.

    This function processes text messages from users:
    1. Extracts URLs from the message
    2. Validates if the URL is a valid property listing
    3. Triggers the scraping process for valid URLs
    4. Sends a confirmation message back to the user

    Args:
        event: The LINE message event containing text
    """
    asyncio.create_task(process_text_message(event))


async def process_text_message(event: MessageEvent) -> None:
    """
    Process a text message asynchronously.

    Args:
        event: The LINE message event containing text
    """
    try:
        message_text = event.message.text
        line_user_id = event.source.user_id
        reply_token = event.reply_token

        logger.info(f"Processing message from {line_user_id}: {message_text}")

        # Extract URLs from the message
        urls = extract_urls(message_text)

        if not urls:
            await send_reply(
                reply_token,
                "URLが見つかりませんでした。もう一度物件のURLを送ってください。",
            )
            return

        # Process the first URL found (we'll only handle one URL per message)
        url = urls[0]

        # Validate if it's a property listing URL (basic check)
        if not is_valid_property_url(url):
            await send_reply(
                reply_token,
                "送って頂いたメッセージは、有効な物件URLではありません。確認してからもう一度試してください。",
            )
            return

        # Call the scrape endpoint
        try:
            # Send reply first to provide immediate feedback
            await send_reply(
                reply_token,
                "物件のスクレイピングを開始しています。少々お待ちください。",
            )
            # Then start the scraping process
            await start_scrapy(url=url, line_user_id=line_user_id)
            await send_reply(reply_token, "スクレイピングが完了しました！")
        except HTTPException as e:
            logger.error(f"Error calling scrape endpoint: {str(e)}")
            await send_reply(
                reply_token,
                "申し訳ありません。リクエストの処理中にエラーが発生しました。",
            )

    except Exception as e:
        logger.error(f"Error processing text message: {str(e)}")
        # Try to send an error message if possible
        try:
            if event and hasattr(event, "reply_token"):
                await send_reply(
                    event.reply_token,
                    "申し訳ありません。メッセージの処理中にエラーが発生しました。",
                )
        except Exception:
            pass


def extract_urls(text: str) -> list[str]:
    """
    Extract URLs from text using regex.

    Args:
        text: The text to extract URLs from

    Returns:
        A list of URLs found in the text
    """
    # Match full URLs including path components, query parameters, and fragments
    url_pattern = r"(https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[-\w%/.~_]*)?(?:\?[-\w%&=.;]*)?(?:#[-\w%]*)?)"
    matches = re.findall(url_pattern, text)
    return matches


def is_valid_property_url(url: str) -> bool:
    """
    Check if a URL is likely to be a property listing.

    Args:
        url: The URL to validate

    Returns:
        True if the URL appears to be a property listing, False otherwise
    """
    # Parse the URL to get the domain
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower()

    # List of known property listing domains
    property_domains = [
        "suumo.jp",
        # "homes.co.jp",
        # "athome.co.jp",
        # "chintai.net",
    ]

    # Check if the domain is in our list of property listing sites
    return any(prop_domain in domain for prop_domain in property_domains)


async def send_reply(reply_token: str, message: str) -> None:
    """
    Send a reply message to the user.

    Args:
        reply_token: The LINE reply token
        message: The message to send
    """
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessageSend(text=message, type="text")],
                )
            )
    except Exception as e:
        logger.error(f"Error sending reply: {str(e)}")


@handler.add(FollowEvent)
def handle_follow_event(event: FollowEvent) -> None:
    """
    Handle follow events from LINE.

    This function is called when a user follows the LINE bot.
    It creates an asynchronous task to process the follow event.

    Args:
        event: The LINE follow event
    """
    asyncio.create_task(process_follow_event(event))


async def process_follow_event(event: FollowEvent) -> None:
    """
    Process a follow event asynchronously.

    This function stores new user information in the database
    when they follow the LINE bot.

    Args:
        event: The LINE follow event
    """
    try:
        line_user_id = event.source.user_id
        logger.info(f"Processing new follower: {line_user_id}")

        # Get current time for timestamps
        current_time = get_current_time()

        # Get database connection
        db = get_db()
        collection_name = os.getenv("COLLECTION_USERS", "users")
        users_collection = db[collection_name]

        # Check if user already exists
        existing_user = await users_collection.find_one({"line_user_id": line_user_id})
        if existing_user:
            logger.info(f"User already exists: {line_user_id}")
            return

        # Create new user record
        new_user = {
            "line_user_id": line_user_id,
            "created_at": current_time,
            "updated_at": current_time,
        }

        # Insert the new user
        await users_collection.insert_one(new_user)
        logger.info(f"New user created: {line_user_id}")

    except Exception as e:
        logger.error(f"Error processing follow event: {str(e)}")
        # Consider implementing a retry mechanism or error notification system
