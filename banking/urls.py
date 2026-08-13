from django.urls import path

from banking import views


app_name = 'banking'

urlpatterns = [
    path('', views.BankListView.as_view(), name='list'),
    path('create/', views.BankCreateView.as_view(), name='create'),
    path('<int:pk>/', views.BankDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.BankUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.BankDeleteView.as_view(), name='delete'),
    path('accounts/create/', views.BankAccountCreateView.as_view(), name='account_create'),
    path('accounts/<int:pk>/edit/', views.BankAccountUpdateView.as_view(), name='account_update'),
    path('accounts/<int:pk>/delete/', views.BankAccountDeleteView.as_view(), name='account_delete'),
    path('debit-cards/create/', views.DebitCardCreateView.as_view(), name='debit_card_create'),
    path('debit-cards/<int:pk>/edit/', views.DebitCardUpdateView.as_view(), name='debit_card_update'),
    path('debit-cards/<int:pk>/delete/', views.DebitCardDeleteView.as_view(), name='debit_card_delete'),
    path('credit-cards/create/', views.CreditCardCreateView.as_view(), name='credit_card_create'),
    path('credit-cards/<int:pk>/edit/', views.CreditCardUpdateView.as_view(), name='credit_card_update'),
    path('credit-cards/<int:pk>/delete/', views.CreditCardDeleteView.as_view(), name='credit_card_delete'),
    path('loyalty/create/', views.LoyaltyProgramCreateView.as_view(), name='program_create'),
    path('loyalty/<int:pk>/edit/', views.LoyaltyProgramUpdateView.as_view(), name='program_update'),
    path('loyalty/<int:pk>/delete/', views.LoyaltyProgramDeleteView.as_view(), name='program_delete'),
    path('transfers/create/', views.BankTransferCreateView.as_view(), name='transfer_create'),
    path('loyalty-entries/create/', views.LoyaltyEntryCreateView.as_view(), name='entry_create'),
    path('loyalty-entries/<int:pk>/edit/', views.LoyaltyEntryUpdateView.as_view(), name='entry_update'),
    path('loyalty-entries/<int:pk>/delete/', views.LoyaltyEntryDeleteView.as_view(), name='entry_delete'),
    path('rewards/redeem/', views.RewardRedemptionCreateView.as_view(), name='redemption_create'),
    path('exchange-rates/', views.ExchangeRateListView.as_view(), name='exchange_rates'),
    path('exchange-rates/create/', views.ExchangeRateCreateView.as_view(), name='exchange_rate_create'),
]
