import logging
import os

from fastapi import APIRouter, HTTPException, Request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import TextMessage
from linebot.v3.webhooks import FollowEvent, MessageEvent

from app.db.session import get_db

router = APIRouter()
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
logger = logging.getLogger(__name__)


@router.post(
    "/webhook",
    summary="Get the webhook message information",
    response_description="The webhook message information",
    # response_model=List[Webhook],
    response_model_by_alias=False,
)
async def webhook_message_handler(request: Request):
    """
    Get the webhook message information.
    """
    # get X-Line-Signature header value
    signature = request.headers.get("X-Line-Signature")

    # get request body as text
    body = await request.body()
    body = body.decode("utf-8")

    # handle webhook body
    try:
        handler.handle(body, signature)

    except InvalidSignatureError:
        logging.error(
            "Invalid signature. Please check your channel access token/channel secret."
        )
        raise HTTPException(status_code=400, detail="Invalid signature.")

    return {"message": "Webhook message received!"}


@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    logging.info(f"Text: {event.message.text}")


@handler.add(FollowEvent)
def handle_follow_event(event):
    user_id = event.source.user_id
    logging.info(f"New follower: {user_id}")
    # Save the user_id to the database
    db = get_db()
    collection_users = db[os.getenv("COLLECTION_USERS")]
    if not collection_users.find_one({"user_id": user_id}):
        collection_users.insert_one({"user_id": user_id})
