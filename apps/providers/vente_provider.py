import logging
import requests
from decimal import Decimal
from typing import Optional, Dict, Any, List
from apps.providers.base import BaseFulfillmentProvider, ProviderOrderResult

logger = logging.getLogger(__name__)

class VenteBotProvider(BaseFulfillmentProvider):
    """
    Dedicated integration adapter for Vente Telegram Bot Railway API.
    Handles multi-scheme authentication, order placement, status querying, and balance checks.
    """

    def __init__(self, api_key: str, api_secret: str = "", base_url: str = ""):
        clean_url = (base_url or "https://ventetelegrambotrailway-production.up.railway.app").rstrip('/')
        super().__init__(api_key=api_key, api_secret=api_secret, base_url=clean_url)

    def _get_auth_headers_list(self) -> List[Dict[str, str]]:
        """List of standard auth schemes to try in order."""
        return [
            {
                'Authorization': f'Bearer {self.api_key}',
                'X-API-Key': self.api_key,
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'TeleBot-VenteAdapter/1.0',
            },
            {
                'Authorization': f'Token {self.api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'TeleBot-VenteAdapter/1.0',
            },
            {
                'Authorization': f'Api-Key {self.api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'TeleBot-VenteAdapter/1.0',
            },
            {
                'Authorization': self.api_key,
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'TeleBot-VenteAdapter/1.0',
            },
        ]

    def _make_request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """Execute HTTP request trying multiple auth schemes if 401/403 returned."""
        auth_schemes = self._get_auth_headers_list()
        last_resp = None

        for headers in auth_schemes:
            call_kwargs = dict(kwargs)
            call_kwargs['headers'] = {**headers, **call_kwargs.get('headers', {})}
            try:
                resp = requests.request(method, url, **call_kwargs)
                last_resp = resp
                if resp.status_code not in (401, 403):
                    return resp
            except Exception as exc:
                logger.debug(f"Request failed for scheme: {exc}")
                continue

        # Try query parameter fallback ?api_key=
        try:
            call_kwargs = dict(kwargs)
            params = dict(call_kwargs.get('params') or {})
            params['api_key'] = self.api_key
            call_kwargs['params'] = params
            resp = requests.request(method, url, **call_kwargs)
            return resp
        except Exception:
            return last_resp

    def create_order(
        self, 
        external_service_id: str, 
        quantity: int = 1, 
        customer_input: str = "", 
        custom_params: Optional[Dict[str, Any]] = None
    ) -> ProviderOrderResult:
        """
        Submit a purchase order to Vente API.
        Attempts primary order creation endpoints.
        """
        custom_params = custom_params or {}
        
        endpoints = [
            f"{self.base_url}/api/orders/",
            f"{self.base_url}/api/buy/",
            f"{self.base_url}/api/purchase/",
            f"{self.base_url}/api/v1/orders/",
        ]

        payload = {
            'product_id': external_service_id,
            'service_id': external_service_id,
            'quantity': quantity,
            'player_id': customer_input,
            'account_id': customer_input,
            'customer_input': customer_input,
            'target': customer_input,
            **custom_params
        }

        last_error = ""
        for url in endpoints:
            try:
                logger.info(f"Submitting order to Vente API: {url} with product {external_service_id}")
                resp = self._make_request('POST', url, json=payload, timeout=30)
                if resp is None:
                    continue

                if resp.status_code == 404:
                    continue

                try:
                    data = resp.json()
                except Exception:
                    data = {'raw_text': resp.text}

                if resp.status_code in (200, 201):
                    is_error = data.get('error') or data.get('detail') if resp.status_code >= 400 or data.get('status') == 'error' else None
                    if is_error:
                        return ProviderOrderResult(
                            success=False,
                            error_message=f"رفض مزود Vente الطلب: {is_error}",
                            raw_response=data
                        )

                    order_id = str(data.get('order_id') or data.get('id') or data.get('order') or '')
                    delivered_data = (
                        str(data.get('keys') or data.get('pin') or data.get('code') or 
                            data.get('delivered_data') or data.get('message') or 
                            f"تم شحن الطلب بنجاح عبر المزود (رقم العملية: {order_id})")
                    )

                    return ProviderOrderResult(
                        success=True,
                        provider_order_id=order_id,
                        delivered_payload=delivered_data,
                        raw_response=data
                    )
                else:
                    err_msg = data.get('detail') or data.get('error') or data.get('message') or resp.text[:200]
                    last_error = f"خطأ من المزود (HTTP {resp.status_code}): {err_msg}"
                    return ProviderOrderResult(
                        success=False,
                        error_message=last_error,
                        raw_response=data
                    )

            except requests.Timeout:
                return ProviderOrderResult(
                    success=False,
                    error_message="انتهت مهلة انتظار الرد من مزود Vente (Timeout)."
                )
            except Exception as e:
                last_error = str(e)

        return ProviderOrderResult(
            success=False,
            error_message=last_error or "تعذر العثور على مسار تنفيذ الطلب في مزود Vente."
        )

    def get_order_status(self, provider_order_id: str) -> ProviderOrderResult:
        """Query status of an order."""
        endpoints = [
            f"{self.base_url}/api/orders/{provider_order_id}/",
            f"{self.base_url}/api/order-status/{provider_order_id}/",
        ]
        for url in endpoints:
            try:
                resp = self._make_request('GET', url, timeout=15)
                if resp and resp.status_code == 200:
                    data = resp.json()
                    return ProviderOrderResult(success=True, provider_order_id=provider_order_id, raw_response=data)
            except Exception:
                pass
        return ProviderOrderResult(success=False, error_message="تعذر جلب حالة الطلب.")

    def get_balance(self) -> Decimal:
        """Query current wallet balance at Vente."""
        endpoints = [
            f"{self.base_url}/api/wallet/balance/",
            f"{self.base_url}/api/wallet/",
            f"{self.base_url}/api/balance/",
            f"{self.base_url}/api/user/balance/",
            f"{self.base_url}/api/users/balance/",
            f"{self.base_url}/api/users/me/",
            f"{self.base_url}/api/user/profile/",
            f"{self.base_url}/api/user/",
            f"{self.base_url}/api/profile/",
            f"{self.base_url}/api/me/",
            f"{self.base_url}/api/account/",
            f"{self.base_url}/api/v1/wallet/",
            f"{self.base_url}/api/v1/balance/",
        ]
        for url in endpoints:
            try:
                resp = self._make_request('GET', url, timeout=10)
                if resp and resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception:
                        continue
                    logger.info(f"Balance check from {url}: {data}")
                    # Search common balance keys
                    for k in ('balance', 'wallet_balance', 'funds', 'credit', 'amount', 'balance_yer', 'balance_usd', 'current_balance'):
                        if k in data and data[k] is not None:
                            try:
                                return Decimal(str(data[k]))
                            except Exception:
                                pass
                    # Search nested dicts
                    for sub in ('wallet', 'user', 'profile', 'data', 'account'):
                        if isinstance(data.get(sub), dict):
                            for k in ('balance', 'wallet_balance', 'funds', 'credit', 'amount'):
                                if k in data[sub] and data[sub][k] is not None:
                                    try:
                                        return Decimal(str(data[sub][k]))
                                    except Exception:
                                        pass
            except Exception as e:
                logger.debug(f"Error checking balance on {url}: {e}")
        return Decimal('0.00')

    def fetch_available_services(self) -> List[Dict[str, Any]]:
        """Fetch list of products/services offered by the remote provider."""
        endpoints = [
            f"{self.base_url}/api/products/",
            f"{self.base_url}/api/services/",
            f"{self.base_url}/api/catalog/products/",
            f"{self.base_url}/api/shop/products/",
            f"{self.base_url}/api/items/",
            f"{self.base_url}/api/v1/products/",
            f"{self.base_url}/api/v1/services/",
        ]
        for url in endpoints:
            try:
                resp = self._make_request('GET', url, timeout=15)
                if resp and resp.status_code == 200:
                    data = resp.json()
                    logger.info(f"Fetched services from {url}: {type(data)}")
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict):
                        if 'results' in data and isinstance(data['results'], list):
                            return data['results']
                        if 'data' in data and isinstance(data['data'], list):
                            return data['data']
                        if 'products' in data and isinstance(data['products'], list):
                            return data['products']
                        if 'services' in data and isinstance(data['services'], list):
                            return data['services']
            except Exception as e:
                logger.error(f"Error fetching services from {url}: {e}")
        return []
