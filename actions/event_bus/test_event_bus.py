"""Pytest tests for the Enterprise Event Bus."""
import asyncio
import threading
from typing import Any, Dict, List
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from actions.event_bus.event_bus import EventBus
from actions.event_bus.main import app, event_bus
from actions.event_bus.schemas import EventMessage, PublishRequest


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    # Clear the event bus before each test
    for topic in event_bus.get_topics():
        event_bus.delete_topic(topic)
    return TestClient(app)


@pytest.fixture
def bus():
    """Create a fresh EventBus instance for each test."""
    return EventBus()


# Unit tests for EventBus class

def test_subscribe_and_publish(bus):
    """Test subscribing to a topic and publishing a message."""
    received_messages = []
    
    def callback(message: EventMessage):
        received_messages.append(message)
    
    bus.subscribe("test_topic", callback)
    bus.publish("test_topic", {"data": "value"})
    
    assert len(received_messages) == 1
    assert received_messages[0].payload == {"data": "value"}
    assert received_messages[0].metadata == {}


def test_unsubscribe(bus):
    """Test unsubscribing from a topic."""
    received_messages = []
    
    def callback(message: EventMessage):
        received_messages.append(message)
    
    bus.subscribe("test_topic", callback)
    bus.publish("test_topic", {"data": "value1"})
    
    assert bus.unsubscribe("test_topic", callback) is True
    bus.publish("test_topic", {"data": "value2"})
    
    assert len(received_messages) == 1
    assert received_messages[0].payload == {"data": "value1"}


def test_unsubscribe_nonexistent(bus):
    """Test unsubscribing from a topic that doesn't exist."""
    def callback(message: EventMessage):
        pass
    
    assert bus.unsubscribe("nonexistent", callback) is False


def test_multiple_subscribers(bus):
    """Test multiple subscribers to the same topic."""
    received_messages_1 = []
    received_messages_2 = []
    
    def callback1(message: EventMessage):
        received_messages_1.append(message)
    
    def callback2(message: EventMessage):
        received_messages_2.append(message)
    
    bus.subscribe("test_topic", callback1)
    bus.subscribe("test_topic", callback2)
    bus.publish("test_topic", {"data": "value"})
    
    assert len(received_messages_1) == 1
    assert len(received_messages_2) == 1
    assert received_messages_1[0].payload == {"data": "value"}
    assert received_messages_2[0].payload == {"data": "value"}


def test_get_topics(bus):
    """Test getting all topics."""
    bus.publish("topic1", {"data": "value1"})
    bus.publish("topic2", {"data": "value2"})
    bus.publish("topic3", {"data": "value3"})
    
    topics = bus.get_topics()
    assert len(topics) == 3
    assert "topic1" in topics
    assert "topic2" in topics
    assert "topic3" in topics


def test_get_topic_messages(bus):
    """Test getting messages from a topic."""
    bus.publish("topic1", {"data": "value1"})
    bus.publish("topic1", {"data": "value2"})
    
    messages = bus.get_topic_messages("topic1")
    assert len(messages) == 2
    assert messages[0]["payload"] == {"data": "value1"}
    assert messages[1]["payload"] == {"data": "value2"}


def test_get_topic_messages_nonexistent(bus):
    """Test getting messages from a nonexistent topic."""
    messages = bus.get_topic_messages("nonexistent")
    assert messages == []


def test_clear_topic(bus):
    """Test clearing messages from a topic."""
    bus.publish("topic1", {"data": "value1"})
    bus.publish("topic1", {"data": "value2"})
    
    assert bus.clear_topic("topic1") is True
    messages = bus.get_topic_messages("topic1")
    assert messages == []


def test_clear_nonexistent_topic(bus):
    """Test clearing messages from a nonexistent topic."""
    assert bus.clear_topic("nonexistent") is False


# API endpoint tests

def test_publish_endpoint(client):
    """Test the publish endpoint."""
    response = client.post(
        "/publish/test_topic",
        json={"payload": {"data": "value"}}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["topic"] == "test_topic"


def test_publish_endpoint_invalid_payload(client):
    """Test the publish endpoint with invalid payload."""
    response = client.post(
        "/publish/test_topic",
        json={"invalid": "payload"}
    )
    assert response.status_code == 422


def test_get_topics_endpoint(client):
    """Test the get topics endpoint."""
    client.post("/publish/topic1", json={"payload": {"data": "value1"}})
    client.post("/publish/topic2", json={"payload": {"data": "value2"}})
    
    response = client.get("/topics")
    assert response.status_code == 200
    topics = response.json()
    assert "topic1" in topics
    assert "topic2" in topics


def test_get_topic_messages_endpoint(client):
    """Test the get topic messages endpoint."""
    client.post("/publish/topic1", json={"payload": {"a": 1}})
    client.post("/publish/topic1", json={"payload": {"b": 2}})
    
    response = client.get("/topics/topic1/messages")
    assert response.status_code == 200
    messages = response.json()
    assert len(messages) == 2
    assert messages[0]["payload"] == {"a": 1}
    assert messages[1]["payload"] == {"b": 2}


def test_get_topic_messages_not_found(client):
    """Test getting messages from a nonexistent topic."""
    response = client.get("/topics/nonexistent/messages")
    assert response.status_code == 404


def test_clear_topic_endpoint(client):
    """Test the clear topic endpoint."""
    client.post("/publish/topic1", json={"payload": {"data": "value1"}})
    
    response = client.delete("/topics/topic1/messages")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Verify messages are cleared
    response = client.get("/topics/topic1/messages")
    assert response.status_code == 200
    assert response.json() == []


def test_clear_topic_not_found(client):
    """Test clearing a nonexistent topic."""
    response = client.delete("/topics/nonexistent/messages")
    assert response.status_code == 404


def test_subscriber_error_handling(bus):
    """Test that subscriber errors don't break the event bus."""
    received_messages = []
    
    def failing_callback(message: EventMessage):
        raise Exception("Subscriber error")
    
    def working_callback(message: EventMessage):
        received_messages.append(message)
    
    bus.subscribe("test_topic", failing_callback)
    bus.subscribe("test_topic", working_callback)
    
    # This should not raise an exception
    bus.publish("test_topic", {"data": "value"})
    
    assert len(received_messages) == 1
    assert received_messages[0].payload == {"data": "value"}


def test_concurrent_publish(bus):
    """Test concurrent publishing to the same topic."""
    received_messages = []
    lock = threading.Lock()
    
    def callback(message: EventMessage):
        with lock:
            received_messages.append(message)
    
    bus.subscribe("test_topic", callback)
    
    def publish_messages():
        for i in range(10):
            bus.publish("test_topic", {"data": i})
    
    threads = []
    for _ in range(5):
        thread = threading.Thread(target=publish_messages)
        threads.append(thread)
        thread.start()
    
    for thread in threads:
        thread.join()
    
    assert len(received_messages) == 50
    assert len(bus.get_topic_messages("test_topic")) == 50