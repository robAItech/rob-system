"""
Core GatewayRouter implementation for the Enterprise Unified Gateway.
"""

import logging
from typing import Any, Callable, Dict, Optional

from actions.enterprise_unified_gateway.schemas import RoutePayload, RouteResponse

logger = logging.getLogger(__name__)


class GatewayRouter:
    """
    A unified gateway router that registers and routes requests to virtual microservices.
    """

    def __init__(self) -> None:
        """
        Initialize the GatewayRouter with an empty service registry.
        """
        self._services: Dict[str, Callable[[RoutePayload], Dict[str, Any]]] = {}

    def register_service(
        self,
        service_name: str,
        handler: Callable[[RoutePayload], Dict[str, Any]],
    ) -> None:
        """
        Register a virtual microservice with the gateway.

        Args:
            service_name: Unique name of the service to register.
            handler: Callable that processes the RoutePayload and returns a response dict.

        Raises:
            ValueError: If the service name is already registered.
        """
        if service_name in self._services:
            raise ValueError(f"Service '{service_name}' is already registered")

        self._services[service_name] = handler
        logger.info("Registered service: %s", service_name)

    def unregister_service(self, service_name: str) -> bool:
        """
        Unregister a virtual microservice from the gateway.

        Args:
            service_name: Name of the service to unregister.

        Returns:
            True if the service was removed, False if it didn't exist.
        """
        if service_name in self._services:
            del self._services[service_name]
            logger.info("Unregistered service: %s", service_name)
            return True
        return False

    def route(self, payload: RoutePayload) -> RouteResponse:
        """
        Route a request to the appropriate virtual microservice.

        Args:
            payload: The RoutePayload containing routing information.

        Returns:
            RouteResponse with the result of the routing operation.
        """
        service_name = payload.service_name

        if service_name not in self._services:
            logger.warning("Service not found: %s", service_name)
            return RouteResponse(
                success=False,
                service_name=service_name,
                status_code=404,
                error=f"Service '{service_name}' not found",
            )

        try:
            handler = self._services[service_name]
            result = handler(payload)
            return RouteResponse(
                success=True,
                service_name=service_name,
                status_code=200,
                data=result,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Error routing to service %s: %s", service_name, exc)
            return RouteResponse(
                success=False,
                service_name=service_name,
                status_code=500,
                error=f"Internal error routing to service '{service_name}': {str(exc)}",
            )

    def get_registered_services(self) -> list[str]:
        """
        Get a list of all registered service names.

        Returns:
            List of registered service names.
        """
        return list(self._services.keys())

    def is_service_registered(self, service_name: str) -> bool:
        """
        Check if a service is registered.

        Args:
            service_name: Name of the service to check.

        Returns:
            True if the service is registered, False otherwise.
        """
        return service_name in self._services