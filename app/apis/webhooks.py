import asyncio
import logging
import os
import re
from typing import List, NamedTuple, Optional, Protocol
from urllib.parse import urlparse

from bson import ObjectId
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
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.apis.scrape import ScrapeRequest, queue_scraping
from app.db.session import get_db
from app.models.apis.webhook import WebhookResponse
from app.services.dates import get_current_time

router = APIRouter()
logger = logging.getLogger(__name__)

# Configure LINE messaging API client
line_config = Configuration(access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN", ""))
line_handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET", ""))


class PropertyStatus(NamedTuple):
    exists: bool
    user_has_access: bool
    property_id: Optional[ObjectId] = None


class DatabaseProtocol(Protocol):
    """Protocol for database operations."""

    async def get_property_status(
        self, url: str, line_user_id: str
    ) -> PropertyStatus: ...

    async def add_user_property(
        self, property_id: ObjectId, line_user_id: str
    ) -> None: ...
    async def create_or_update_user(self, line_user_id: str) -> None: ...


async def get_database_collections() -> (
    tuple[AsyncIOMotorCollection, AsyncIOMotorCollection, AsyncIOMotorCollection]
):
    """Get database collections."""
    db: AsyncIOMotorDatabase = get_db()
    properties_collection = db[os.getenv("COLLECTION_PROPERTIES", "properties")]
    user_properties_collection = db[
        os.getenv("COLLECTION_USER_PROPERTIES", "user_properties")
    ]
    users_collection = db[os.getenv("COLLECTION_USERS", "users")]
    return properties_collection, user_properties_collection, users_collection


async def get_property_status(
    url: str,
    line_user_id: str,
    collections: tuple[
        AsyncIOMotorCollection, AsyncIOMotorCollection, AsyncIOMotorCollection
    ] = None,
) -> PropertyStatus:
    """Get property existence and user access status."""
    if collections is None:
        collections = await get_database_collections()

    properties_collection, user_properties_collection, _ = collections

    existing_property = await properties_collection.find_one({"url": url})
    if not existing_property:
        return PropertyStatus(exists=False, user_has_access=False)

    has_access = bool(
        await user_properties_collection.find_one(
            {"property_id": existing_property["_id"], "line_user_id": line_user_id}
        )
    )

    return PropertyStatus(
        exists=True,
        user_has_access=has_access,
        property_id=existing_property["_id"],
    )


async def add_user_property(
    property_id: ObjectId,
    line_user_id: str,
    collections: tuple[
        AsyncIOMotorCollection, AsyncIOMotorCollection, AsyncIOMotorCollection
    ] = None,
) -> None:
    """Add a property to user's watchlist."""
    if collections is None:
        collections = await get_database_collections()

    _, user_properties_collection, _ = collections
    current_time = get_current_time()

    await user_properties_collection.insert_one(
        {
            "property_id": property_id,
            "line_user_id": line_user_id,
            "created_at": current_time,
            "updated_at": current_time,
        }
    )
    logger.info(f"User property added: {property_id} for {line_user_id}")


async def create_or_update_user(
    line_user_id: str,
    collections: tuple[
        AsyncIOMotorCollection, AsyncIOMotorCollection, AsyncIOMotorCollection
    ] = None,
) -> None:
    """Create or update user record."""
    if collections is None:
        collections = await get_database_collections()

    _, _, users_collection = collections

    existing_user = await users_collection.find_one({"line_user_id": line_user_id})
    if existing_user:
        logger.info(f"User already exists: {line_user_id}")
        return

    current_time = get_current_time()
    await users_collection.insert_one(
        {
            "line_user_id": line_user_id,
            "created_at": current_time,
            "updated_at": current_time,
        }
    )
    logger.info(f"New user created: {line_user_id}")


@router.post(
    "/webhook",
    summary="Process LINE webhook events",
    response_description="Webhook processing status",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
)
async def webhook_message_handler(request: Request) -> WebhookResponse:
    """Process incoming LINE webhook events."""
    signature = request.headers.get("X-Line-Signature")
    if not signature:
        logger.error("Missing X-Line-Signature header")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature header"
        )

    body = await request.body()
    body_text = body.decode("utf-8")

    try:
        line_handler.handle(body_text, signature)
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


@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event: MessageEvent) -> None:
    """Handle text message events from LINE."""
    asyncio.create_task(process_text_message(event))


def extract_suumo_url(text: str) -> str:
    """Extract a SUUMO property URL from text."""
    urls = extract_urls(text)
    return next(
        (url for url in urls if is_valid_property_url(url) and "suumo.jp" in url), ""
    )


def find_valid_suumo_url(urls: List[str]) -> Optional[str]:
    """Find the first valid SUUMO property URL from a list of URLs."""
    return next(
        (url for url in urls if is_valid_property_url(url) and "suumo.jp" in url), None
    )


def is_valid_message_event(event: MessageEvent) -> bool:
    """Check if the event is a valid message event."""
    return bool(
        hasattr(event, "message")
        and isinstance(event.message, TextMessageContent)
        and hasattr(event, "source")
        and hasattr(event.source, "user_id")
        and hasattr(event, "reply_token")
        and event.reply_token is not None
    )


def get_message_info(event: MessageEvent) -> tuple[str, str, str]:
    """Extract message information from the event."""
    return (
        event.message.text,
        event.source.user_id,
        event.reply_token,
    )


async def send_inquiry_response(reply_token: str) -> None:
    """Send the inquiry response message."""
    await send_reply(
        reply_token,
        "お問い合わせありがとうございます！\nSUUMOの物件URLを送っていただければ、情報を取得いたします。",
    )


async def send_invalid_url_response(reply_token: str) -> None:
    """Send the invalid URL response message."""
    await send_reply(
        reply_token,
        "SUUMOの物件ページURLを送信してください",
    )


async def process_text_message(
    event: MessageEvent,
    collections: tuple[
        AsyncIOMotorCollection, AsyncIOMotorCollection, AsyncIOMotorCollection
    ] = None,
) -> None:
    """Process a text message from a LINE user."""
    if not is_valid_message_event(event):
        return

    if collections is None:
        collections = await get_database_collections()

    try:
        message_text, line_user_id, reply_token = get_message_info(event)
        logger.info(f"Processing message from {line_user_id}: {message_text}")

        urls = extract_urls(message_text)
        if not urls:
            await send_inquiry_response(reply_token)
            return

        valid_suumo_url = find_valid_suumo_url(urls)
        if not valid_suumo_url:
            await send_invalid_url_response(reply_token)
            return

        await handle_scraping(reply_token, valid_suumo_url, line_user_id, collections)
    except Exception as e:
        await handle_message_error(event, e)


async def handle_scraping(
    reply_token: str,
    url: str,
    line_user_id: str,
    collections: tuple[
        AsyncIOMotorCollection, AsyncIOMotorCollection, AsyncIOMotorCollection
    ] = None,
) -> None:
    """Handle property scraping and user notification process."""
    if not url or not line_user_id:
        logger.error("Missing required parameters")
        return

    if collections is None:
        collections = await get_database_collections()

    try:
        property_status = await get_property_status(url, line_user_id, collections)
        await handle_property_status(
            reply_token, url, line_user_id, property_status, collections
        )
    except Exception as e:
        logger.error(f"Error in handle_scraping: {str(e)}")
        await send_push_message(
            line_user_id,
            "申し訳ありません。リクエストの処理中にエラーが発生しました。後でもう一度お試しください。",
        )


async def handle_property_status(
    reply_token: str,
    url: str,
    line_user_id: str,
    property_status: PropertyStatus,
    collections: tuple[
        AsyncIOMotorCollection, AsyncIOMotorCollection, AsyncIOMotorCollection
    ] = None,
) -> None:
    """Handle property based on its status."""
    if collections is None:
        collections = await get_database_collections()

    if property_status.user_has_access:
        await send_reply(
            reply_token,
            "この物件は既にウォッチリストに追加されています！\n左下のメニューからご確認ください😊",
        )
        return

    await send_reply(
        reply_token,
        "ウォッチリストに追加されました！\n左下のメニューからご確認ください😊\n(反映には1分ほどかかる場合があります)",
    )
    logger.info(f"Property status: {property_status}")

    if not property_status.user_has_access and property_status.exists:
        await add_user_property(property_status.property_id, line_user_id, collections)
    else:
        await handle_new_property(url, line_user_id)


async def handle_new_property(url: str, line_user_id: str) -> None:
    """Handle scraping of a new property."""
    try:
        scrape_request = ScrapeRequest(
            url=url, line_user_id=line_user_id, timestamp=get_current_time()
        )
        result = await queue_scraping(scrape_request)

        if result.get("status") != "queued":
            await send_error_message(line_user_id)
    except HTTPException as e:
        await handle_http_exception(e, line_user_id)
    except Exception as e:
        logger.error(f"Error in scraping process: {str(e)}")
        await send_error_message(line_user_id)


async def handle_http_exception(e: HTTPException, line_user_id: str) -> None:
    """Handle HTTP exceptions during scraping."""
    logger.error(f"Error in scraping process: {str(e)}")
    if e.status_code == 404 or "Property not found" in str(e):
        await send_push_message(
            line_user_id,
            "指定された物件は見つかりませんでした。URLが正しいか、または物件が削除されていないか確認してください。",
        )
    else:
        await send_error_message(line_user_id)


async def send_error_message(line_user_id: str) -> None:
    """Send a generic error message to the user."""
    await send_push_message(
        line_user_id,
        "申し訳ありません。リクエストの処理中にエラーが発生しました。後でもう一度お試しください。",
    )


def extract_urls(text: str) -> list[str]:
    """Extract URLs from text using regex."""
    url_pattern = r"(https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[-\w%/.~_]*)?(?:\?[-\w%&=.;]*)?(?:#[-\w%]*)?)"
    return re.findall(url_pattern, text)


def is_valid_property_url(url: str) -> bool:
    """Check if a URL is likely to be a property listing."""
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower()
    path = parsed_url.path.lower()

    property_domains = ["suumo.jp"]
    if not any(prop_domain in domain for prop_domain in property_domains):
        return False

    if "suumo.jp" in domain:
        valid_path_patterns = ["/ms/"]
        return any(pattern in path for pattern in valid_path_patterns)

    return True


async def send_reply(reply_token: str, message: str) -> None:
    """
    Send a reply message using the LINE Messaging API.

    Args:
        reply_token (str): The reply token to use
        message (str): The message to send
    """
    try:
        api_client = ApiClient(line_config)
        messaging_api = MessagingApi(api_client)
        messaging_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessageSend(text=message, type="text")],
            )
        )
    except Exception as e:
        error_msg = "Unknown error"
        if e is not None:
            try:
                error_msg = str(e)
            except Exception:
                pass
        logger.error(f"Error sending reply: {error_msg}")


async def send_push_message(user_id: str, message: str) -> None:
    """
    Send a push message using the LINE Messaging API.

    Args:
        user_id (str): The user ID to send the message to
        message (str): The message to send
    """
    try:
        api_client = ApiClient(line_config)
        messaging_api = MessagingApi(api_client)
        messaging_api.push_message_with_http_info(
            PushMessageRequest(
                to=user_id,
                messages=[TextMessageSend(text=message, type="text")],
            )
        )
    except Exception as e:
        error_msg = "Unknown error"
        if e is not None:
            try:
                error_msg = str(e)
            except Exception:
                pass
        logger.error(f"Error sending push message: {error_msg}")


@line_handler.add(FollowEvent)
def handle_follow_event(event: FollowEvent) -> None:
    """Handle follow events from LINE."""
    asyncio.create_task(process_follow_event(event))


async def process_follow_event(
    event: FollowEvent,
    collections: tuple[
        AsyncIOMotorCollection, AsyncIOMotorCollection, AsyncIOMotorCollection
    ] = None,
) -> None:
    """Process a follow event asynchronously."""
    if collections is None:
        collections = await get_database_collections()

    try:
        line_user_id = event.source.user_id
        logger.info(f"Processing new follower: {line_user_id}")

        # Check if user exists before creating/updating
        users_collection = collections[0]
        existing_user = await users_collection.find_one({"line_user_id": line_user_id})

        await create_or_update_user(line_user_id, collections)

        # Only send welcome message to new users
        if not existing_user:
            welcome_message = (
                "ようこそ！マンションウォッチへ！\n"
                "SUUMOの物件URLを送っていただければ、情報を取得します。"
            )
            await send_push_message(line_user_id, welcome_message)

    except Exception as e:
        logger.error(f"Error processing follow event: {str(e)}")


async def handle_message_error(event: MessageEvent, error: Exception) -> None:
    """Handle errors that occur during message processing."""
    logger.error(f"Error processing text message: {str(error)}")
    try:
        if not event.reply_token:
            await send_push_message(
                event.source.user_id,
                "申し訳ありません。メッセージの処理中にエラーが発生しました。",
            )
            return

        if not is_valid_message_event(event):
            return

        try:
            await send_reply(
                event.reply_token,
                "申し訳ありません。メッセージの処理中にエラーが発生しました。",
            )
        except Exception:
            await send_push_message(
                event.source.user_id,
                "申し訳ありません。メッセージの処理中にエラーが発生しました。",
            )
    except Exception as inner_e:
        logger.error(f"Failed to send error message: {str(inner_e)}")
