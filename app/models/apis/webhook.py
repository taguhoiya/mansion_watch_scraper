from pydantic import BaseModel


class WebhookResponse(BaseModel):
    """Response model for webhook endpoint"""

    message: str
