import pytest
from fastapi.testclient import TestClient
from actions.nexus_command_deck.main import app, orchestrator

client = TestClient(app)

def test_frontend_renders():
    response = client.get("/")
    assert response.status_code == 200
    assert "NEXUS // COMMAND DECK" in response.text
    assert "pitch black" not in response.text # Just ensuring it rendered HTML

def test_websocket_orchestration_text():
    # Mokiramo z TestClient.websocket_connect
    with client.websocket_connect("/ws/nexus") as websocket:
        # Pošlji tekst (Gre na Anthropic po default_route)
        websocket.send_json({"content": "Analiziraj to strategijo", "content_type": "text"})
        
        # Prejmi processing status
        status = websocket.receive_json()
        assert "[...] Obdelujem" in status["content"]
        
        # Prejmi končni LLM odgovor
        response = websocket.receive_json()
        assert "Anthropic Claude" in response["content"]
        assert response["provider"] == "Anthropic"
        assert response["latency_ms"] > 0
        assert response["is_fallback"] is False

def test_websocket_orchestration_failover():
    # Vsilimo napako na primarnem providerju
    orchestrator.primary_fail_sim = True
    
    with client.websocket_connect("/ws/nexus") as websocket:
        # Pošlji audio (Gre na Gemini, a bo padel, zato fallback na OpenAI)
        websocket.send_json({"content": "Audio Data", "content_type": "audio"})
        websocket.receive_json() # Skip processing msg
        
        response = websocket.receive_json()
        assert "OpenAI Fallback" in response["content"]
        assert response["provider"] == "OpenAI"
        assert response["is_fallback"] is True
        
    # Reset za nadaljnje teste
    orchestrator.primary_fail_sim = False
