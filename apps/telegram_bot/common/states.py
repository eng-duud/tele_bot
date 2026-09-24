from aiogram.fsm.state import State, StatesGroup

class DepositStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_tx_number = State()
    waiting_for_proof_photo = State()

class PurchaseStates(StatesGroup):
    waiting_for_quantity = State()
    waiting_for_customer_input = State()
    confirm_purchase = State()

class ServiceOrderStates(StatesGroup):
    waiting_for_notes = State()
    waiting_for_attachment = State()

class AdminExchangeRateStates(StatesGroup):
    waiting_for_rate = State()

class AdminStockAddStates(StatesGroup):
    waiting_for_product_selection = State()
    waiting_for_items_text = State()

class AdminAddCategoryStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_icon = State()

class AdminAddProductStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_name = State()
    waiting_for_desc = State()
    waiting_for_price = State()
    waiting_for_stock_type = State()
    waiting_for_customer_input_flag = State()

class AdminAddPaymentMethodStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_account = State()
    waiting_for_account_name = State()
    waiting_for_instructions = State()

class AdminBroadcastStates(StatesGroup):
    waiting_for_text = State()

class AdminEditProductPriceStates(StatesGroup):
    waiting_for_new_price = State()

class AdminCustomerSearchStates(StatesGroup):
    waiting_for_query = State()

class AdminManualWalletStates(StatesGroup):
    waiting_for_amount = State()

class AdminAddChannelStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_channel_id = State()
    waiting_for_invite_link = State()
