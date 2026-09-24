import uuid
import random
from decimal import Decimal
from typing import Optional, Dict, Any
from apps.providers.base import BaseFulfillmentProvider, ProviderOrderResult

class MockFulfillmentProvider(BaseFulfillmentProvider):
    """
    Mock / Simulator provider for zero-risk local testing.
    Generates realistic license keys, serials, and mock responses.
    """

    def create_order(
        self, 
        external_service_id: str, 
        quantity: int = 1, 
        customer_input: str = "", 
        custom_params: Optional[Dict[str, Any]] = None
    ) -> ProviderOrderResult:
        """Simulate creating an external API order."""
        fake_remote_id = f"EXT-{random.randint(100000, 999999)}"
        
        # Generate simulated serial / license key
        generated_keys = [
            f"KEY-{uuid.uuid4().hex[:8].upper()}-{uuid.uuid4().hex[:8].upper()}" 
            for _ in range(quantity)
        ]
        delivered_str = "\n".join(generated_keys)

        return ProviderOrderResult(
            success=True,
            provider_order_id=fake_remote_id,
            delivered_payload=delivered_str,
            raw_response={"status": "success", "order_id": fake_remote_id, "keys": generated_keys}
        )

    def get_order_status(self, provider_order_id: str) -> ProviderOrderResult:
        """Simulate polling order status."""
        return ProviderOrderResult(
            success=True,
            provider_order_id=provider_order_id,
            raw_response={"status": "completed"}
        )

    def get_balance(self) -> Decimal:
        """Simulate fetching balance."""
        return Decimal('1000.00')
