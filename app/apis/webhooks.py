import asyncio
import logging
import os
import re
from typing import List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, status
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
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


def extract_suumo_url(text: str) -> str:
    """
    Extract a SUUMO property URL from text.

    Args:
        text: The text to extract a SUUMO URL from

    Returns:
        The first valid SUUMO property URL found, or an empty string if none found
    """
    # Extract all URLs from the text
    urls = extract_urls(text)

    # Return the first valid SUUMO property URL
    for url in urls:
        if is_valid_property_url(url) and "suumo.jp" in url:
            return url

    # No valid SUUMO property URL found
    return ""


def find_valid_suumo_url(urls: List[str]) -> Optional[str]:
    """
    Find the first valid SUUMO property URL from a list of URLs.

    Args:
        urls: List of URLs to check

    Returns:
        The first valid SUUMO property URL found, or None if none found
    """
    for url in urls:
        if is_valid_property_url(url) and "suumo.jp" in url:
            return url
    return None


def is_valid_message_event(event: MessageEvent) -> bool:
    """
    Check if the event is a valid message event.

    Args:
        event: The LINE message event

    Returns:
        True if the event is valid, False otherwise
    """
    return bool(
        hasattr(event, "message")
        and isinstance(event.message, TextMessageContent)
        and hasattr(event, "source")
        and hasattr(event.source, "user_id")
        and hasattr(event, "reply_token")
        and event.reply_token is not None
    )


def get_message_info(event: MessageEvent) -> tuple[str, str, str]:
    """
    Extract message information from the event.

    Args:
        event: The LINE message event

    Returns:
        Tuple of (message_text, line_user_id, reply_token)
    """
    return (
        event.message.text,
        event.source.user_id,
        event.reply_token,
    )


async def send_inquiry_response(reply_token: str) -> None:
    """
    Send the inquiry response message.

    Args:
        reply_token: The LINE reply token
    """
    await send_reply(
        reply_token,
        "お問い合わせありがとうございます！\n"
        "SUUMOの物件URLを送っていただければ、情報を取得いたします。",
    )


async def send_invalid_url_response(reply_token: str) -> None:
    """
    Send the invalid URL response message.

    Args:
        reply_token: The LINE reply token
    """
    await send_reply(
        reply_token,
        "SUUMOの物件ページURLを送信してください",
    )


async def process_text_message(event: MessageEvent) -> None:
    """
    Process a text message from a LINE user.

    Args:
        event: The LINE message event
    """
    try:
        # Early return for invalid message events
        if not is_valid_message_event(event):
            return

        # Extract message information
        message_text, line_user_id, reply_token = get_message_info(event)
        logger.info(f"Processing message from {line_user_id}: {message_text}")

        # Extract URLs from the message
        urls = extract_urls(message_text)

        # Case 3: No URL in message - send inquiry response
        if not urls:
            await send_inquiry_response(reply_token)
            return

        # Check if any of the URLs is a valid SUUMO property URL
        valid_suumo_url = find_valid_suumo_url(urls)

        # Case 2: Invalid URL - send request for SUUMO URL
        if not valid_suumo_url:
            await send_invalid_url_response(reply_token)
            return

        # Case 1: Valid SUUMO URL - proceed with scraping
        await handle_scraping(reply_token, valid_suumo_url, line_user_id)

    except Exception as e:
        await handle_message_error(event, e)


async def handle_scraping(reply_token: str, url: str, line_user_id: str) -> None:
    """
    Handle the scraping process and send appropriate messages to the user.

    Args:
        reply_token: The LINE reply token
        url: The URL to scrape
        line_user_id: The LINE user ID
    """
    try:
        # Send reply first to provide immediate feedback - only use the reply token once
        await send_reply(
            reply_token,
            "物件のスクレイピングを開始しています。少々お待ちください。",
        )

        # Start the scraping process
        try:
            result = await start_scrapy(url=url, line_user_id=line_user_id)

            # Check if the result indicates a property not found (404)
            if isinstance(result, dict) and result.get("status") == "not_found":
                logger.info(f"Property not found for URL: {url}")
                await send_push_message(
                    line_user_id,
                    "指定された物件は見つかりませんでした。URLが正しいか、または物件が削除されていないか確認してください。",
                )
            else:
                # Use push message instead of reply since the reply token can only be used once
                await send_push_message(
                    line_user_id,
                    "スクレイピングが完了しました！",
                )
        except HTTPException as e:
            logger.error(f"Error calling scrape endpoint: {str(e)}")
            await send_push_message(
                line_user_id,
                "申し訳ありません。リクエストの処理中にエラーが発生しました。",
            )
        except Exception as e:
            logger.error(f"General error in scraping process: {str(e)}")
            await send_push_message(
                line_user_id,
                "申し訳ありません。リクエストの処理中にエラーが発生しました。",
            )
    except Exception as e:
        logger.error(f"Error in handle_scraping: {str(e)}")
        # Try to send a push message even if the initial reply failed
        try:
            await send_push_message(
                line_user_id,
                "申し訳ありません。リクエストの処理中にエラーが発生しました。",
            )
        except Exception as inner_e:
            logger.error(f"Failed to send error push message: {str(inner_e)}")


async def handle_scraping_error(line_user_id: str, error_message: str) -> None:
    """
    Handle scraping errors and send appropriate error messages to the user.

    Args:
        line_user_id: The LINE user ID
        error_message: The error message from the scraper
    """
    if (
        "HTTP Status Code: 404" in error_message
        or "Property not found (404)" in error_message
    ):
        await send_push_message(
            line_user_id,
            "申し訳ありません。指定された物件は見つかりませんでした。URLが正しいか、または物件が削除されていないか確認してください。",
        )
    elif "HTTP Status Code: 403" in error_message:
        await send_push_message(
            line_user_id,
            "申し訳ありません。アクセスが拒否されました。しばらく時間をおいてから再度お試しください。",
        )
    elif "HTTP Status Code: 500" in error_message:
        await send_push_message(
            line_user_id,
            "申し訳ありません。物件サイトでエラーが発生しています。しばらく時間をおいてから再度お試しください。",
        )
    elif "HttpError on" in error_message:
        await send_push_message(
            line_user_id,
            "申し訳ありません。指定されたURLにアクセスできませんでした。URLが正しいか確認してください。",
        )
    elif "Property name not found" in error_message:
        await send_push_message(
            line_user_id,
            "申し訳ありません。スクレイピング中にエラーが発生しました。後でもう一度お試しください。",
        )
    elif (
        "ValidationError" in error_message
        or "pydantic_core._pydantic_core.ValidationError" in error_message
    ):
        await send_push_message(
            line_user_id,
            "申し訳ありません。スクレイピング中にエラーが発生しました。後でもう一度お試しください。",
        )
    elif "DNSLookupError" in error_message:
        await send_push_message(
            line_user_id,
            "申し訳ありません。ドメイン名を解決できませんでした。インターネット接続を確認してください。",
        )
    elif "TimeoutError" in error_message:
        await send_push_message(
            line_user_id,
            "申し訳ありません。リクエストがタイムアウトしました。サーバーが混雑している可能性があります。後でもう一度お試しください。",
        )
    else:
        await send_push_message(
            line_user_id,
            "スクレイピング中にエラーが発生しました。後でもう一度お試しください。",
        )


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
    path = parsed_url.path.lower()

    # List of known property listing domains
    property_domains = [
        "suumo.jp",
        # "homes.co.jp",
        # "athome.co.jp",
        # "chintai.net",
    ]

    # Check if the domain is in our list of property listing sites
    if not any(prop_domain in domain for prop_domain in property_domains):
        return False

    # TODO: For now, we only support SUUMO ms
    # For SUUMO, check if it's a valid property listing path
    if "suumo.jp" in domain:
        # Valid SUUMO property paths typically include:
        # - /ms/ (mansion/apartment)
        # - /chintai/ (rental)
        # - /chuko/ (used)
        # - /kodate/ (house)
        valid_path_patterns = [
            "/ms/",  # Mansion/apartment
            # "/chintai/",  # Rental
            # "/chuko/",  # Used
            # "/kodate/",  # House
        ]
        return any(pattern in path for pattern in valid_path_patterns)

    # For other domains, we'll add specific validation later
    return True


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


async def send_push_message(user_id: str, message: str) -> None:
    """
    Send a push message to the user.

    This is used when we can't use a reply token (e.g., it's already been used or expired).

    Args:
        user_id: The LINE user ID to send the message to
        message: The message to send
    """
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message_with_http_info(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessageSend(text=message, type="text")],
                )
            )
    except Exception as e:
        logger.error(f"Error sending push message: {str(e)}")


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

        # Send welcome message to new user
        welcome_message = (
            "ようこそ！マンションウォッチへ！\n"
            "SUUMOの物件URLを送っていただければ、情報を取得します。"
        )
        await send_push_message(line_user_id, welcome_message)

    except Exception as e:
        logger.error(f"Error processing follow event: {str(e)}")
        # Consider implementing a retry mechanism or error notification system


async def handle_message_error(event: MessageEvent, error: Exception) -> None:
    """
    Handle errors that occur during message processing.

    Args:
        event: The LINE message event
        error: The exception that occurred
    """
    logger.error(f"Error processing text message: {str(error)}")
    try:
        # For events without a reply token, use push message
        if event.reply_token is None:
            await send_push_message(
                event.source.user_id,
                "申し訳ありません。メッセージの処理中にエラーが発生しました。",
            )
            return

        # For invalid events with a reply token, don't try to send any messages
        if not is_valid_message_event(event):
            return

        # For valid events with a reply token, try to use it
        try:
            await send_reply(
                event.reply_token,
                "申し訳ありません。メッセージの処理中にエラーが発生しました。",
            )
        except Exception:
            # If reply fails, fall back to push message
            await send_push_message(
                event.source.user_id,
                "申し訳ありません。メッセージの処理中にエラーが発生しました。",
            )
    except Exception as inner_e:
        logger.error(f"Failed to send error message: {str(inner_e)}")
