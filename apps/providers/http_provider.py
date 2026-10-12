import logging
import requests
import ipaddress
import socket
from urllib.parse import urlparse
from decimal import Decimal
from typing import Optional, Dict, Any
from apps.providers.base import BaseFulfillmentProvider, ProviderOrderResult

logger = logging.getLogger(__name__)


def validate_provider_url(url: str) -> str:
    """Allow only external HTTPS endpoints and reject SSRF targets."""
    parsed = urlparse((url or '').strip())
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('رابط مزود API يجب أن يكون HTTPS خارجياً صالحاً.')
    host = parsed.hostname.rstrip('.').lower()
    if host in {'localhost', 'localhost.localdomain'}:
        raise ValueError('لا يسمح باستخدام localhost كمزود API.')
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, None)}
        except OSError as exc:
            raise ValueError('تعذر التحقق من عنوان مزود API.') from exc
    if any(addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast for addr in addresses):
        raise ValueError('لا يسمح لمزود API بالإشارة إلى شبكة داخلية أو عنوان محلي.')
    return url.strip()

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
        custom_params: Optional[Dict[str, Any]] = None,
        idempotency_key: str = ""
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
        if idempotency_key:
            headers['Idempotency-Key'] = idempotency_key
        
        # Custom authorization header if configured
        auth_header = custom_params.get('auth_header')
        if auth_header:
            headers['Authorization'] = auth_header.replace('{api_key}', self.api_key)

        try:
            endpoint = validate_provider_url(self.base_url)
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
                response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout, allow_redirects=False)
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
                response = requests.post(endpoint, data=payload, headers=headers, timeout=timeout, allow_redirects=False)

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
            resp = requests.post(validate_provider_url(self.base_url), data=payload, timeout=15, allow_redirects=False)
            data = resp.json()
            return ProviderOrderResult(success=True, provider_order_id=provider_order_id, raw_response=data)
        except Exception as e:
            return ProviderOrderResult(success=False, error_message=str(e))

    def get_balance(self) -> Decimal:
        """Query account balance on remote provider."""
        try:
            payload = {'key': self.api_key, 'action': 'balance'}
            resp = requests.post(validate_provider_url(self.base_url), data=payload, timeout=15, allow_redirects=False)
            data = resp.json()
            val = data.get('balance', '0')
            return Decimal(str(val))
        except Exception:
            return Decimal('0.00')
