from fastapi import FastAPI, HTTPException, status, BackgroundTasks
from typing import Optional, Dict
from actions.enterprise_webhook_dispatcher.schemas import WebhookEndpoint, WebhookEvent, DeliveryResult
from actions.enterprise_webhook_dispatcher.enterprise_webhook_dispatcher import EnterpriseWebhookDispatcher

app = FastAPI(title="Rob AI Studio - Enterprise Webhook Dispatcher API")
dispatcher = EnterpriseWebhookDispatcher()

@app.post("/endpoints", status_code=status.HTTP_201_CREATED)
async def create_endpoint(endpoint: WebhookEndpoint):
    dispatcher.register_endpoint(endpoint)
    return {"status": "REGISTERED", "endpoint_id": endpoint.id}

@app.post("/dispatch/{endpoint_id}", response_model=Dict[str, str])
async def dispatch_webhook(endpoint_id: str, event: WebhookEvent, background_tasks: BackgroundTasks):
    if endpoint_id not in dispatcher.endpoints:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    
    # Send webhook asynchronously in the background
    background_tasks.add_task(dispatcher.dispatch, endpoint_id, event)
    return {"status": "DISPATCH_QUEUED", "event_id": event.event_id}

@app.get("/results/{event_id}/{endpoint_id}", response_model=DeliveryResult)
async def get_delivery_result(event_id: str, endpoint_id: str):
    key = f"{event_id}_{endpoint_id}"
    result = dispatcher.results.get(key)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found or pending")
    return result
