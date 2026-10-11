import logging
import requests
from decimal import Decimal
from typing import Optional, Dict, Any
from apps.providers.base import BaseFulfillmentProvider, ProviderOrderResult

logger = logging.getLogger(__name__)

class HttpFulfillmentProvider(BaseFulfillmentProvider):
    """
    Generic HTTP / REST / SMM Provider Adapter.
    Supports both standard SMM API v2 formats and custom JSON REST APIs.
    """

    def create_order(
        self, 
        external_service_id: str, 
        quantity: int = 1, 
        customer_input: str = "", 
        custom_params: Optional[Dict[str, Any]] = None
    ) -> ProviderOrderResult:
        """
        Send order to external provider.
        Supports:
        1. SMM Panel standard: {key, action: 'add', service, link, quantity}
        2. Generic JSON REST: custom parameters merged with customer_input
        """
        custom_params = custom_params or {}
        api_format = custom_params.get('format', 'smm').lower()
        timeout = int(custom_params.get('timeout', 30))

        headers = {
            'User-Agent': 'TeleBot-Fulfillment/1.0',
            'Accept': 'application/json',
        }
        
        # Custom authorization header if configured
        auth_header = custom_params.get('auth_header')
        if auth_header:
            headers['Authorization'] = auth_header.replace('{api_key}', self.api_key)

        try:
            if api_format == 'json':
                # Generic JSON POST
                payload = {
                    'service_id': external_service_id,
                    'quantity': quantity,
                    'customer_data': customer_input,
                    **custom_params.get('extra_fields', {})
                }
                if not auth_header and self.api_key:
                    payload['api_key'] = self.api_key

                headers['Content-Type'] = 'application/json'
                response = requests.post(self.base_url, json=payload, headers=headers, timeout=timeout)
            else:
                # Default: Standard SMM Panel / Form-encoded API v2
                payload = {
                    'key': self.api_key,
                    'action': 'add',
                    'service': external_service_id,
                    'link': customer_input,
                    'quantity': quantity,
                    **custom_params.get('extra_fields', {})
                }
                response = requests.post(self.base_url, data=payload, headers=headers, timeout=timeout)

            # Parse response
            try:
                data = response.json()
            except Exception:
                data = {'raw_text': response.text}

            if response.status_code in (200, 201):
                # Standard SMM response: {'order': 12345}
                order_id = str(data.get('order') or data.get('order_id') or data.get('id') or '')
                error = data.get('error') or data.get('message') if ('error' in data or data.get('status') == 'error') else None

                if error:
                    return ProviderOrderResult(
                        success=False,
                        error_message=f"المزود الخارجي رفض الطلب: {error}",
                        raw_response=data
                    )

                delivered = str(data.get('keys') or data.get('pin') or data.get('delivered') or f"تم تنفيذ الطلب بنجاح لدى المزود. رقم العملية: {order_id}")
                return ProviderOrderResult(
                    success=True,
                    provider_order_id=order_id,
                    delivered_payload=delivered,
                    raw_response=data
                )
            else:
                return ProviderOrderResult(
                    success=False,
                    error_message=f"خطأ اتصال بالمزود (HTTP {response.status_code}): {response.text[:200]}",
                    raw_response=data
                )

        except requests.Timeout:
            return ProviderOrderResult(
                success=False,
                error_message="انتهت مهلة الاتصال بمزود الخدمة (Timeout)."
            )
        except Exception as exc:
            logger.error(f"HTTP Provider order failed: {exc}", exc_info=True)
            return ProviderOrderResult(
                success=False,
                error_message=f"فشل الاتصال بمزود الخدمة: {str(exc)}"
            )

    def get_order_status(self, provider_order_id: str) -> ProviderOrderResult:
        """Query remote order status."""
        try:
            payload = {'key': self.api_key, 'action': 'status', 'order': provider_order_id}
            resp = requests.post(self.base_url, data=payload, timeout=15)
            data = resp.json()
            return ProviderOrderResult(success=True, provider_order_id=provider_order_id, raw_response=data)
        except Exception as e:
            return ProviderOrderResult(success=False, error_message=str(e))

    def get_balance(self) -> Decimal:
        """Query account balance on remote provider."""
        try:
            payload = {'key': self.api_key, 'action': 'balance'}
            resp = requests.post(self.base_url, data=payload, timeout=15)
            data = resp.json()
            val = data.get('balance', '0')
            return Decimal(str(val))
        except Exception:
            return Decimal('0.00')
