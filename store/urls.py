from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # --- 1. المسارات الأساسية ---
    path('', views.dashboard, name='dashboard'),
    path('transactions/', views.transactions_list, name='transactions_list'),
    path('contact/<int:pk>/', views.contact_detail, name='contact_detail'),
    
    # إضافة حركة (يومية) مباشرة من بروفايل التاجر أو لوحة التحكم
    path('contact/add-transaction/', views.add_transaction_direct, name='add_transaction_direct'),
    
    # --- 2. مسارات الحسابات والدخول ---
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    
    # --- 3. مسارات الإدارة المالية (للمسؤول فقط) ---
    path('update-paid/<int:record_id>/', views.update_paid_amount, name='update_paid_amount'),
    path('admin-logs/', views.admin_logs_dashboard, name='admin_logs'),

    # --- 4. مسارات قسم البنك ---
    path('bank/statement/', views.bank_statement, name='bank_statement'),
    path('bank/add-installment/', views.add_bank_installment, name='add_bank_installment'),
    path('bank/installment/update-charges/<int:inst_id>/', views.update_installment_charges, name='update_installment_charges'),
    path('bank/installment/toggle/<int:inst_id>/', views.toggle_installment_status, name='toggle_installment_status'),

    # --- 5. مسارات "مصروف البيت" وإدارة الخزنة (الجديدة) ---
    # مسار سريع لإضافة مصروف بيت جديد مباشرة من التقرير
    path('home-expenses/add/', lambda r: redirect('/admin/store/homeexpense/add/'), name='add_home_expense'),
    
    # مسار سريع لتعديل رأس المال أو الخزنة يدوياً عند الضرورة
    path('capital/update/', lambda r: redirect('/admin/store/capital/'), name='update_capital'),
]