from django.contrib import admin
from .models import (
    Contact, Product, DailyTransaction, FinancialRecord, 
    PaymentInstallment, BankLoan, BankInstallment
)

# --- 1. إعدادات أقساط الموردين والتجار ---
class PaymentInstallmentInline(admin.TabularInline):
    model = PaymentInstallment
    extra = 1
    readonly_fields = ['date_paid']

# --- 2. إعدادات أقساط البنك (تعديل للعرض الآلي) ---
class BankInstallmentInline(admin.TabularInline):
    model = BankInstallment
    # تم تقليل extra إلى 0 لأن الأقساط تنشأ تلقائياً الآن
    extra = 0 
    # جعل الحقول التي تحسب تلقائياً للقراءة فقط لضمان دقة البيانات
    # يمكنك إزالتها من readonly_fields إذا كنت ترغب في تعديلها يدوياً لاحقاً
    readonly_fields = ['due_date', 'total_installment_amount', 'interest_component', 'principal_component']
    fields = ['due_date', 'total_installment_amount', 'interest_component', 'principal_component', 'extra_charges', 'is_paid']
    verbose_name = "قسط بنكي"
    verbose_name_plural = "جدول الأقساط الشهرية الناتجة"

# --- 3. تسجيل الموديلات في لوحة الإدارة ---

@admin.register(BankLoan)
class BankLoanAdmin(admin.ModelAdmin):
    # إضافة interest_rate_percentage إلى القائمة
    list_display = ['bank_name', 'total_loan_amount', 'interest_rate_percentage', 'loan_period_months', 'start_date', 'is_active']
    # ترتيب الحقول عند إضافة قرض جديد
    fields = ['bank_name', 'loan_type', 'total_loan_amount', 'interest_rate_percentage', 'loan_period_months', 'start_date', 'is_active']
    inlines = [BankInstallmentInline] 

@admin.register(BankInstallment)
class BankInstallmentAdmin(admin.ModelAdmin):
    list_display = ['loan', 'due_date', 'total_installment_amount', 'interest_component', 'principal_component', 'is_paid']
    list_filter = ['is_paid', 'due_date', 'loan__bank_name']
    list_editable = ['is_paid'] 

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone']
    search_fields = ['name']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'quantity_available', 'purchase_price_per_kg', 'selling_price_per_kg']

@admin.register(DailyTransaction)
class DailyTransactionAdmin(admin.ModelAdmin):
    list_display = ['date', 'transaction_type', 'product', 'contact', 'weight', 'total_price']
    list_filter = ['transaction_type', 'date']
    search_fields = ['contact__name', 'product__name']

@admin.register(FinancialRecord)
class FinancialRecordAdmin(admin.ModelAdmin):
    list_display = ['transaction', 'get_contact', 'get_total', 'amount_paid', 'remaining_amount_display', 'is_fully_paid_status']
    list_filter = ['transaction__transaction_type', 'transaction__date']
    inlines = [PaymentInstallmentInline]

    def get_contact(self, obj):
        return obj.transaction.contact.name
    get_contact.short_description = 'التاجر'

    def get_total(self, obj):
        return obj.transaction.total_price
    get_total.short_description = 'الإجمالي'

    def remaining_amount_display(self, obj):
        return obj.remaining_amount
    remaining_amount_display.short_description = 'المبلغ المتبقي'

    def is_fully_paid_status(self, obj):
        return obj.is_fully_paid
    is_fully_paid_status.boolean = True
    is_fully_paid_status.short_description = 'تم التسديد بالكامل؟'

@admin.register(PaymentInstallment)
class PaymentInstallmentAdmin(admin.ModelAdmin):
    list_display = ['financial_record', 'amount', 'date_paid']