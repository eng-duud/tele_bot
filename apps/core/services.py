from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple
from apps.core.models import ExchangeRate

class CurrencyService:
    """Service to handle multi-currency conversions and localized formatting."""

    @staticmethod
    def get_rate(source_curr: str = 'USD', target_curr: str = 'YER') -> Decimal:
        """Fetch current exchange rate."""
        if source_curr == target_curr:
            return Decimal('1.0')
        return ExchangeRate.get_usd_to_yer_rate()

    @classmethod
    def convert(cls, amount: Decimal, from_curr: str, to_curr: str) -> Decimal:
        """Convert amount between USD and YER."""
        if amount is None:
            return Decimal('0')
        if from_curr == to_curr:
            return Decimal(str(amount))
        
        rate = cls.get_rate('USD', 'YER')
        if from_curr == 'USD' and to_curr == 'YER':
            converted = Decimal(str(amount)) * rate
            return converted.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        elif from_curr == 'YER' and to_curr == 'USD':
            if rate == 0:
                return Decimal('0.00')
            converted = Decimal(str(amount)) / rate
            return converted.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Decimal(str(amount))

    @classmethod
    def format_dual_price(cls, amount_yer: Decimal, preferred_currency: str = 'YER') -> str:
        """
        Format price clearly showing preferred currency first, followed by the secondary.
        e.g. "5,500 ر.ي ($10.00)" or "$10.00 (5,500 ر.ي)"
        """
        amount_yer = Decimal(str(amount_yer))
        amount_usd = cls.convert(amount_yer, from_curr='YER', to_curr='USD')

        yer_str = f"{amount_yer:,.0f} ر.ي"
        usd_str = f"${amount_usd:,.2f}"

        if preferred_currency == 'USD':
            return f"{usd_str} ({yer_str})"
        return f"{yer_str} ({usd_str})"

    @classmethod
    def format_price_single(cls, amount_yer: Decimal, preferred_currency: str = 'YER') -> str:
        """Format price strictly in user's preferred currency."""
        amount_yer = Decimal(str(amount_yer))
        if preferred_currency == 'USD':
            amount_usd = cls.convert(amount_yer, from_curr='YER', to_curr='USD')
            return f"${amount_usd:,.2f}"
        return f"{amount_yer:,.0f} YER"

    @classmethod
    def format_button_price(cls, amount_yer: Decimal, preferred_currency: str = 'YER') -> str:
        """Short price format for inline buttons."""
        return cls.format_price_single(amount_yer, preferred_currency)

    @classmethod
    def get_base_currency(cls) -> str:
        """Get official base currency from dynamic system settings."""
        from django.conf import settings
        return SystemSettingService.get_setting('BASE_CURRENCY', getattr(settings, 'BASE_CURRENCY', 'YER')).upper()

    @classmethod
    def set_base_currency(cls, currency: str):
        """Update official base currency."""
        SystemSettingService.set_setting('BASE_CURRENCY', currency.upper(), "العملة الرسمية الأساسية للمتجر")


class SystemSettingService:
    """Service to manage SaaS dynamic configuration settings with in-memory caching."""

    _CACHE = {}
    _LAST_LOAD = 0.0
    _CACHE_TTL = 30.0  # seconds

    DEFAULTS = {
        'STORE_NAME': 'المتجر الرقمي',
        'SUPPORT_USERNAME': '',
        'SUPPORT_ENABLED': 'true',
        'REFERRAL_BONUS_YER': '50',
        'REFERRAL_ENABLED': 'true',
        'WELCOME_MESSAGE': 'أهلاً بك في منصة المتجر الرقمي 🛍️✨',
        'BASE_CURRENCY': 'YER',
        'SUCCESS_CHANNEL_ID': '@duudsuccess',
        'SUCCESS_CHANNEL_URL': 'https://t.me/duudsuccess',
        'SUCCESS_CHANNEL_TITLE': 'قناة التفعيلات المباشرة',
        'SUCCESS_CHANNEL_ENABLED': 'true',
        'MANDATORY_SUBSCRIPTION_ENABLED': 'true',
        'REQUIRED_CHANNEL_ID': '-1004465247788',
        'REQUIRED_CHANNEL_URL': 'https://t.me/al3rtat_store',
        'REQUIRED_CHANNEL_TITLE': 'قناة المتجر الرسمية',
        'BACKUP_CHANNEL_ID': '',
        'BACKUP_AUTO_ENABLED': 'true',
        'LAST_BACKUP_TIME': '',
    }

    @classmethod
    def _refresh_cache_if_needed(cls):
        import time
        from apps.core.models import SystemSetting
        now = time.time()
        if not cls._CACHE or (now - cls._LAST_LOAD > cls._CACHE_TTL):
            try:
                settings_qs = SystemSetting.objects.all()
                cls._CACHE = {s.key: s.value for s in settings_qs}
                cls._LAST_LOAD = now
            except Exception:
                pass

    @classmethod
    def clear_cache(cls):
        cls._CACHE.clear()
        cls._LAST_LOAD = 0.0

    @classmethod
    def get_setting(cls, key: str, default: str = None) -> str:
        """Fetch setting value as string."""
        cls._refresh_cache_if_needed()
        if key in cls._CACHE:
            return cls._CACHE[key]
        if default is not None:
            return default
        return cls.DEFAULTS.get(key, '')

    @classmethod
    def get_bool(cls, key: str, default: bool = False) -> bool:
        """Fetch setting value as boolean."""
        val = cls.get_setting(key, str(default).lower()).strip().lower()
        return val in ('true', '1', 'yes', 'on', 'نعم')

    @classmethod
    def get_decimal(cls, key: str, default: Decimal = Decimal('0')) -> Decimal:
        """Fetch setting value as Decimal."""
        val = cls.get_setting(key, str(default))
        try:
            return Decimal(str(val).replace(',', ''))
        except Exception:
            return default

    @classmethod
    def get_int(cls, key: str, default: int = 0) -> int:
        """Fetch setting value as integer."""
        val = cls.get_setting(key, str(default))
        try:
            return int(float(str(val)))
        except Exception:
            return default

    @classmethod
    def set_setting(cls, key: str, value: str, description: str = ""):
        """Create or update setting and bust cache."""
        from apps.core.models import SystemSetting
        SystemSetting.objects.update_or_create(
            key=key,
            defaults={'value': str(value), 'description': description}
        )
        cls._CACHE[key] = str(value)

