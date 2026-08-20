import re
import asyncio
from pathlib import Path
from typing import Dict

class DeploymentManager:
    # Moduli, ki so samo CI/knjižnice in se NE deployajo kot runtime storitve.
    # Trenutno prazen — contract_testing je bil združen v contract_schema_engine,
    # ki je runtime storitev (JSON Schema validacija). Mehanizem ostaja za prihodnost.
    CI_ONLY_MODULES = set()

    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.actions_dir = self.base_dir / "actions"

    @classmethod
    def _is_deployable(cls, d) -> bool:
        """
        Ali je direktorij veljaven deployabl modul.

        Izloči:
        - nedirektorije,
        - skrite run-time artefakte (`.pytest_cache`, `.git`, ...),
        - Python meta-mape (`__pycache__`, ...),
        - CI-only module (ki se ne deployajo kot storitve).
        """
        if not d.is_dir():
            return False
        name = d.name
        if name.startswith(".") or name.startswith("__"):
            return False
        if name in cls.CI_ONLY_MODULES:
            return False
        return True

    def get_services(self) -> Dict[str, int]:
        services = {}
        # Zaklenjeni porti za kritično infrastrukturo
        fixed_ports = {
            "api_gateway": 8000,
            "nexus_command_deck": 8010,
            "observability_metrics": 9090
        }
        current_port = 8001

        if self.actions_dir.exists():
            for d in sorted(self.actions_dir.iterdir()):
                if not self._is_deployable(d):
                    continue
                if d.name in fixed_ports:
                    services[d.name] = fixed_ports[d.name]
                else:
                    while current_port in fixed_ports.values():
                        current_port += 1
                    services[d.name] = current_port
                    current_port += 1
        return services

    def generate_docker_compose(self) -> str:
        services = self.get_services()
        lines = [
            "version: '3.8'",
            "",
            "x-service-defaults: &service-defaults",
            "  build: .",
            "  restart: always",
            "  env_file: .env",
            "  volumes:",
            "    - ./.rob_ai:/app/.rob_ai",
            "",
            "services:"
        ]
        
        for name, port in services.items():
            lines.append(f"  {name.replace('_', '-')}:")
            lines.append(f"    <<: *service-defaults")
            lines.append(f"    container_name: rob_{name}")
            lines.append(f"    command: uvicorn actions.{name}.main:app --host 0.0.0.0 --port {port}")
            lines.append(f"    ports: [\"{port}:{port}\"]")
            lines.append("")

        content = "\n".join(lines)
        (self.base_dir / "docker-compose.yml").write_text(content, encoding="utf-8")
        return content

    def update_gateway_routes(self) -> bool:
        services = self.get_services()
        gateway_main = self.actions_dir / "api_gateway" / "main.py"

        if not gateway_main.exists():
            return False

        content = gateway_main.read_text(encoding="utf-8")
        routes = []
        
        for name, port in services.items():
            if name == "api_gateway":
                continue
            
            # Generiranje route identifikatorjev
            r_id = name
            prefix = f"/api/{r_id}"
            # Zavarujemo specifične module z Auth ključem
            req_auth = "True" if name in ["audit_trail", "cache_layer"] else "False"
            
            routes.append(f'    ("{r_id}", "{prefix}", "http://127.0.0.1:{port}", {req_auth}),')

        routes_str = "ROUTES = [\n" + "\n".join(routes) + "\n]"
        
        # Varno zamenja staro konfiguracijo z novo z uporabo Regexa
        new_content = re.sub(r'ROUTES\s*=\s*\[.*?\]', routes_str, content, flags=re.DOTALL)
        gateway_main.write_text(new_content, encoding="utf-8")
        return True

    async def run_deployment(self) -> int:
        process = await asyncio.create_subprocess_shell(
            "docker-compose up -d --build",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(self.base_dir)
        )
        await process.wait()
        return process.returncode if process.returncode is not None else 1
