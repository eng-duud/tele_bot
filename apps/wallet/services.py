from decimal import Decimal
from typing import Optional, Tuple
from django.db import transaction
from apps.users.models import TelegramProfile
from apps.wallet.models import Wallet, WalletTransaction

class WalletError(Exception):
    """Base exception for wallet operations."""
    pass

class InsufficientBalanceError(WalletError):
    """Raised when customer balance is lower than purchase amount."""
    pass

class WalletLockedError(WalletError):
    """Raised when wallet is suspended/locked."""
    pass

class InvalidAmountError(WalletError):
    """Raised for non-positive or invalid transaction amounts."""
    pass


class WalletService:
    """
    Central Ledger Financial Engine.
    All balance mutations MUST go through this service inside atomic DB transactions
    with row-level locking (select_for_update) and idempotency verification.
    """

    @staticmethod
    def get_or_create_wallet(profile: TelegramProfile) -> Wallet:
        """Retrieve existing wallet or initialize a new zero-balance wallet."""
        wallet, _ = Wallet.objects.get_or_create(profile=profile)
        return wallet

    @classmethod
    def deposit(
        cls, 
        wallet: Wallet, 
        amount: Decimal, 
        reference_id: str = "", 
        description: str = "", 
        idempotency_key: Optional[str] = None
    ) -> Tuple[WalletTransaction, bool]:
        """
        Credit amount to wallet with strict idempotency and atomic locking.
        Returns: (WalletTransaction, created: bool)
        """
        amount = Decimal(str(amount))
        if amount <= 0:
            raise InvalidAmountError("مبلغ الإيداع يجب أن يكون أكبر من الصفر.")

        # Check idempotency first before acquiring lock
        if idempotency_key:
            existing = WalletTransaction.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing, False

        with transaction.atomic():
            # Row-level lock to prevent concurrent modifications
            locked_wallet = Wallet.objects.select_for_update().get(id=wallet.id)
            if locked_wallet.is_locked:
                raise WalletLockedError("المحفظة مجمدة حالياً، يرجى التواصل مع الدعم الفني.")

            # Double check idempotency under transaction lock
            if idempotency_key:
                existing = WalletTransaction.objects.filter(idempotency_key=idempotency_key).first()
                if existing:
                    return existing, False

            bal_before = locked_wallet.balance_yer
            bal_after = bal_before + amount

            locked_wallet.balance_yer = bal_after
            locked_wallet.save(update_fields=['balance_yer', 'updated_at'])

            tx = WalletTransaction.objects.create(
                wallet=locked_wallet,
                tx_type='DEPOSIT',
                amount=amount,
                balance_before=bal_before,
                balance_after=bal_after,
                reference_id=reference_id,
                idempotency_key=idempotency_key,
                description=description or f"إيداع رصيد بقيمة {amount:,.0f} YER"
            )

            return tx, True

    @classmethod
    def debit(
        cls, 
        wallet: Wallet, 
        amount: Decimal, 
        reference_id: str = "", 
        description: str = "", 
        idempotency_key: Optional[str] = None
    ) -> Tuple[WalletTransaction, bool]:
        """
        Debit amount from wallet. Fails atomically if balance is insufficient.
        """
        amount = Decimal(str(amount))
        if amount <= 0:
            raise InvalidAmountError("مبلغ الخصم يجب أن يكون أكبر من الصفر.")

        if idempotency_key:
            existing = WalletTransaction.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing, False

        with transaction.atomic():
            locked_wallet = Wallet.objects.select_for_update().get(id=wallet.id)
            if locked_wallet.is_locked:
                raise WalletLockedError("المحفظة مجمدة حالياً، لا يمكن إتمام عملية الشراء.")

            if locked_wallet.balance_yer < amount:
                raise InsufficientBalanceError(
                    f"رصيدك الحالي ({locked_wallet.balance_yer:,.0f} YER) غير كافٍ لإتمام العملية ({amount:,.0f} YER)."
                )

            if idempotency_key:
                existing = WalletTransaction.objects.filter(idempotency_key=idempotency_key).first()
                if existing:
                    return existing, False

            bal_before = locked_wallet.balance_yer
            bal_after = bal_before - amount

            locked_wallet.balance_yer = bal_after
            locked_wallet.save(update_fields=['balance_yer', 'updated_at'])

            tx = WalletTransaction.objects.create(
                wallet=locked_wallet,
                tx_type='PURCHASE',
                amount=-amount,
                balance_before=bal_before,
                balance_after=bal_after,
                reference_id=reference_id,
                idempotency_key=idempotency_key,
                description=description or f"شراء بقيمة {amount:,.0f} YER"
            )

            return tx, True

    @classmethod
    def refund(
        cls, 
        wallet: Wallet, 
        amount: Decimal, 
        reference_id: str = "", 
        description: str = "", 
        idempotency_key: Optional[str] = None
    ) -> Tuple[WalletTransaction, bool]:
        """
        Refund amount back to customer wallet (e.g. on fulfillment failure).
        """
        amount = Decimal(str(amount))
        if amount <= 0:
            raise InvalidAmountError("مبلغ الاسترجاع يجب أن يكون أكبر من الصفر.")

        if idempotency_key:
            existing = WalletTransaction.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing, False

        with transaction.atomic():
            locked_wallet = Wallet.objects.select_for_update().get(id=wallet.id)

            if idempotency_key:
                existing = WalletTransaction.objects.filter(idempotency_key=idempotency_key).first()
                if existing:
                    return existing, False

            bal_before = locked_wallet.balance_yer
            bal_after = bal_before + amount

            locked_wallet.balance_yer = bal_after
            locked_wallet.save(update_fields=['balance_yer', 'updated_at'])

            tx = WalletTransaction.objects.create(
                wallet=locked_wallet,
                tx_type='REFUND',
                amount=amount,
                balance_before=bal_before,
                balance_after=bal_after,
                reference_id=reference_id,
                idempotency_key=idempotency_key,
                description=description or f"استرجاع رصيد بقيمة {amount:,.0f} YER"
            )

            return tx, True
