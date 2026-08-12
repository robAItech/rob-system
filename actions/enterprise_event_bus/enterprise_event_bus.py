"""Core EventBus implementation for internal Pub/Sub messaging."""
import asyncio
import logging
import threading
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set
from datetime import datetime, timezone

from actions.enterprise_event_bus.schemas import EventMessage

logger = logging.getLogger(__name__)


class EventBus:
    """A thread-safe internal Pub/Sub message broker."""

    def __init__(self) -> None:
        """Initialize the EventBus with empty topics and subscribers."""
        self._topics: Dict[str, List[EventMessage]] = defaultdict(list)
        self._subscribers: Dict[str, Set[Callable]] = defaultdict(set)
        self._lock = threading.RLock()

    def create_topic(self, topic: str) -> None:
        """Create a new topic if it doesn't exist."""
        with self._lock:
            if topic not in self._topics:
                self._topics[topic] = []
                self._subscribers[topic] = set()

    def delete_topic(self, topic: str) -> bool:
        """Delete a topic and all its messages and subscribers."""
        with self._lock:
            if topic in self._topics:
                del self._topics[topic]
                del self._subscribers[topic]
                return True
            return False

    def publish(self, topic: str, payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> None:
        """Publish a message to a topic and notify all subscribers."""
        message = EventMessage(
            payload=payload,
            metadata=metadata or {}
        )
        
        with self._lock:
            if topic not in self._topics:
                self._topics[topic] = []
                self._subscribers[topic] = set()
            
            self._topics[topic].append(message)
            subscribers = list(self._subscribers.get(topic, set()))
        
        # Notify subscribers outside the lock to avoid deadlocks
        for subscriber in subscribers:
            try:
                subscriber(message)
            except Exception as e:
                logger.error(f"Subscriber error on topic {topic}: {e}")

    def subscribe(self, topic: str, callback: Callable[[EventMessage], None]) -> None:
        """Subscribe a callback to a topic."""
        with self._lock:
            if topic not in self._topics:
                self._topics[topic] = []
            self._subscribers[topic].add(callback)

    def unsubscribe(self, topic: str, callback: Callable[[EventMessage], None]) -> bool:
        """Unsubscribe a callback from a topic."""
        with self._lock:
            if topic in self._subscribers and callback in self._subscribers[topic]:
                self._subscribers[topic].remove(callback)
                return True
            return False

    def get_topics(self) -> List[str]:
        """Get all topic names."""
        with self._lock:
            return list(self._topics.keys())

    def get_topic_messages(self, topic: str) -> List[Dict[str, Any]]:
        """Get all messages for a topic."""
        with self._lock:
            if topic not in self._topics:
                return []
            return [msg.model_dump() for msg in self._topics[topic]]

    def clear_topic(self, topic: str) -> bool:
        """Clear all messages from a topic."""
        with self._lock:
            if topic in self._topics:
                self._topics[topic] = []
                return True
            return False

    def get_subscriber_count(self, topic: str) -> int:
        """Get the number of subscribers for a topic."""
        with self._lock:
            return len(self._subscribers.get(topic, set()))

    def has_topic(self, topic: str) -> bool:
        """Check if a topic exists."""
        with self._lock:
            return topic in self._topics