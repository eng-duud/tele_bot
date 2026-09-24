from django.contrib import admin
from apps.wallet.models import Wallet, WalletTransaction

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('profile', 'balance_yer', 'is_locked', 'updated_at')
    search_fields = ('profile__telegram_id', 'profile__username')
    list_filter = ('is_locked',)
    readonly_fields = ('balance_yer',)

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ('wallet', 'tx_type', 'amount', 'balance_after', 'reference_id', 'created_at')
    list_filter = ('tx_type', 'created_at')
    search_fields = ('wallet__profile__telegram_id', 'reference_id', 'idempotency_key')
    readonly_fields = ('wallet', 'tx_type', 'amount', 'balance_before', 'balance_after', 'reference_id', 'idempotency_key', 'description')
