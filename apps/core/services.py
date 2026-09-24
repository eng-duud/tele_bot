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
