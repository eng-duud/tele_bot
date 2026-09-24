from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict, Any

@dataclass
class ProviderOrderResult:
    """Unified result contract returned by any fulfillment provider adapter."""
    success: bool
    provider_order_id: str = ""
    delivered_payload: str = ""
    raw_response: Optional[Dict[str, Any]] = None
    error_message: str = ""


class BaseFulfillmentProvider(ABC):
    """Abstract interface that all external provider integrations must implement."""

    def __init__(self, api_key: str, api_secret: str = "", base_url: str = ""):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url

    @abstractmethod
    def create_order(
        self, 
        external_service_id: str, 
        quantity: int = 1, 
        customer_input: str = "", 
        custom_params: Optional[Dict[str, Any]] = None
    ) -> ProviderOrderResult:
        """Submit a purchase order to the external provider API."""
        pass

    @abstractmethod
    def get_order_status(self, provider_order_id: str) -> ProviderOrderResult:
        """Query the remote status of a previously submitted order."""
        pass

    @abstractmethod
    def get_balance(self) -> Decimal:
        """Fetch our remaining account balance on the provider's platform."""
        pass
