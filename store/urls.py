from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # المسارات الأساسية
    path('', views.dashboard, name='dashboard'),
    path('transactions/', views.transactions_list, name='transactions_list'),
    path('contact/<int:pk>/', views.contact_detail, name='contact_detail'),
    
    # مسارات الحسابات والدخول
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    
    # مسار تعديل المبالغ المدفوعة (للمسؤول فقط)
    path('update-paid/<int:record_id>/', views.update_paid_amount, name='update_paid_amount'),

    # --- مسارات قسم البنك الجديدة ---
    # مسار عرض كشف حساب البنك (الجدول العربي الذي صممناه)
    path('bank/statement/', views.bank_statement, name='bank_statement'),
    
    # مسار تسجيل قسط بنكي جديد (اختياري إذا أردت صفحة مخصصة خارج الإدارة)
    path('bank/add-installment/', views.add_bank_installment, name='add_bank_installment'),
    path('bank/installment/update-charges/<int:inst_id>/', views.update_installment_charges, name='update_installment_charges'),
    path('bank/installment/toggle/<int:inst_id>/', views.toggle_installment_status, name='toggle_installment_status'),
]