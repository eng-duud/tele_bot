from apps.catalog.models import Product
from apps.providers.base import BaseFulfillmentProvider, ProviderOrderResult
from apps.providers.mock_provider import MockFulfillmentProvider
from apps.providers.models import ApiProvider, ProviderProductMapping

class ProviderDispatcherService:
    """Factory and dispatcher for external provider communications."""

    @staticmethod
    def get_adapter(provider: ApiProvider) -> BaseFulfillmentProvider:
        """Instantiate the correct provider adapter."""
        api_key = provider.get_api_key()
        api_secret = provider.get_api_secret()

        if provider.provider_type == 'MOCK':
            return MockFulfillmentProvider(api_key=api_key, api_secret=api_secret, base_url=provider.base_url)
        
        # Extensible for future real integrations
        return MockFulfillmentProvider(api_key=api_key, api_secret=api_secret, base_url=provider.base_url)

    @classmethod
    def execute_provider_order(cls, product: Product, quantity: int = 1, customer_input: str = "") -> ProviderOrderResult:
        """Execute automated order against mapped external provider."""
        mapping = ProviderProductMapping.objects.filter(product=product).select_related('provider').first()
        if not mapping:
            return ProviderOrderResult(
                success=False,
                error_message=f"المنتج {product.name} غير مربوط بأي مزود خارجي."
            )

        if not mapping.provider.is_active:
            return ProviderOrderResult(
                success=False,
                error_message=f"المزود {mapping.provider.name} معطل حالياً."
            )

        adapter = cls.get_adapter(mapping.provider)
        return adapter.create_order(
            external_service_id=mapping.external_service_id,
            quantity=quantity,
            customer_input=customer_input,
            custom_params=mapping.custom_parameters
        )
