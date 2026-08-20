from fastapi import FastAPI
from actions.deployment_manager.schemas import DeploymentResponse
from actions.deployment_manager.deployment_manager import DeploymentManager

app = FastAPI(title="Rob AI Studio - Deployment Manager")
manager = DeploymentManager()

@app.post("/deploy", response_model=DeploymentResponse)
async def trigger_deployment():
    # 1. Generiraj compose
    manager.generate_docker_compose()
    # 2. Posodobi API Gateway
    gateway_ok = manager.update_gateway_routes()
    # 3. Zaženi Docker v ozadju
    exit_code = await manager.run_deployment()
    
    return DeploymentResponse(
        status="DEPLOYED" if exit_code == 0 else "FAILED",
        services_detected=len(manager.get_services()),
        gateway_updated=gateway_ok,
        docker_exit_code=exit_code
    )
