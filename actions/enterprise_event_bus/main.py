"""FastAPI application for the Enterprise Event Bus."""
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import ValidationError

from actions.enterprise_event_bus.enterprise_event_bus import EventBus
from actions.enterprise_event_bus.schemas import EventMessage, PublishRequest

app = FastAPI(
    title="Enterprise Event Bus",
    description="Internal Pub/Sub message broker",
    version="1.0.0"
)

# Global EventBus instance
event_bus = EventBus()


@app.post("/publish/{topic}", status_code=status.HTTP_200_OK)
async def publish_message(topic: str, request: PublishRequest) -> Dict[str, Any]:
    """Publish a message to a topic."""
    try:
        # Validate the request
        validated = PublishRequest(**request.model_dump())
        event_bus.publish(topic, validated.payload, validated.metadata)
        return {
            "status": "success",
            "topic": topic,
            "message": "Message published successfully"
        }
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )


@app.get("/topics", response_model=List[str])
async def get_topics() -> List[str]:
    """Get all available topics."""
    return event_bus.get_topics()


@app.get("/topics/{topic}/messages", response_model=List[Dict[str, Any]])
async def get_topic_messages(topic: str) -> List[Dict[str, Any]]:
    """Get all messages for a specific topic."""
    if not event_bus.has_topic(topic):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic '{topic}' not found"
        )
    return event_bus.get_topic_messages(topic)


@app.delete("/topics/{topic}/messages", status_code=status.HTTP_200_OK)
async def clear_topic_messages(topic: str) -> Dict[str, Any]:
    """Clear all messages from a topic."""
    if not event_bus.has_topic(topic):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic '{topic}' not found"
        )
    event_bus.clear_topic(topic)
    return {
        "status": "success",
        "topic": topic,
        "message": "Topic messages cleared successfully"
    }


@app.delete("/topics/{topic}", status_code=status.HTTP_200_OK)
async def delete_topic(topic: str) -> Dict[str, Any]:
    """Delete a topic and all its data."""
    if not event_bus.has_topic(topic):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic '{topic}' not found"
        )
    event_bus.delete_topic(topic)
    return {
        "status": "success",
        "topic": topic,
        "message": "Topic deleted successfully"
    }