from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Contact, Product, DailyTransaction, FinancialRecord, 
    PaymentInstallment, BankLoan, BankInstallment, Capital, 
    HomeExpense, ContactExpense, IncomeRecord  # إضافة الموديل الجديد هنا
)

# --- 1. إعدادات أقساط الموردين والتجار (Inline) ---
class PaymentInstallmentInline(admin.TabularInline):
    model = PaymentInstallment
    extra = 0
    readonly_fields = ['date_paid']
    can_delete = True
    verbose_name = "دفعة سداد نقدية"
    verbose_name_plural = "سجل الدفعات التفصيلي"

# --- 2. إعدادات أقساط البنك (Inline) ---
class BankInstallmentInline(admin.TabularInline):
    model = BankInstallment
    extra = 0 
    readonly_fields = ['due_date', 'total_installment_amount', 'interest_component', 'principal_component', 'actual_payment_date']
    fields = ['due_date', 'total_installment_amount', 'interest_component', 'principal_component', 'extra_charges', 'is_paid', 'actual_payment_date']
    verbose_name = "قسط شهري"
    verbose_name_plural = "جدول الأقساط الشهرية"

# --- 3. تسجيل الموديلات في لوحة الإدارة ---

@admin.register(IncomeRecord)
class IncomeRecordAdmin(admin.ModelAdmin):
    """إعدادات عرض المبالغ الواردة الأخرى (دخل إضافي)"""
    list_display = ['date', 'source', 'display_amount', 'notes']
    list_filter = ['date', 'source']
    search_fields = ['source', 'notes']
    date_hierarchy = 'date'

    def display_amount(self, obj):
        # تمييز مبالغ الدخل باللون الأخضر المشرق
        return format_html('<b style="color: #2ecc71; font-size: 14px;">+ {} ج.م</b>', obj.amount)
    display_amount.short_description = 'المبلغ الوارد'

@admin.register(ContactExpense)
class ContactExpenseAdmin(admin.ModelAdmin):
    list_display = ['date', 'contact', 'display_amount', 'payer_type_display', 'notes']
    list_filter = ['date', 'contact', 'payer_type']
    search_fields = ['contact__name', 'notes']

    def display_amount(self, obj):
        return format_html('<b style="color: #d63031;">{} ج.م</b>', obj.amount)
    display_amount.short_description = 'قيمة المصروف'

    def payer_type_display(self, obj):
        if obj.payer_type == 'us':
            return format_html('<span style="color: #0984e3;">نحن سددنا</span>')
        return format_html('<span style="color: #6c5ce7;">العميل سدد</span>')
    payer_type_display.short_description = 'الدافع'

@admin.register(HomeExpense)
class HomeExpenseAdmin(admin.ModelAdmin):
    list_display = ['date', 'description', 'display_amount']
    list_filter = ['date']
    search_fields = ['description']
    date_hierarchy = 'date'

    def display_amount(self, obj):
        return format_html('<b style="color: #e67e22; font-size: 14px;">{} ج.م</b>', obj.amount)
    display_amount.short_description = 'المبلغ المستهلك'

@admin.register(Capital)
class CapitalAdmin(admin.ModelAdmin):
    list_display = ['display_amount', 'last_updated']
    
    def display_amount(self, obj):
        return format_html('<b style="color: #28a745; font-size: 16px;">{} ج.م</b>', obj.initial_amount)
    display_amount.short_description = 'المبلغ الحالي في الخزنة'

    def has_add_permission(self, request):
        return not Capital.objects.exists()

@admin.register(BankLoan)
class BankLoanAdmin(admin.ModelAdmin):
    list_display = ['bank_name', 'loan_type', 'total_loan_amount', 'loan_period_months', 'is_active']
    list_filter = ['is_active', 'bank_name']
    inlines = [BankInstallmentInline]

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'notes']
    search_fields = ['name', 'phone']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'quantity_available_display', 'purchase_price_per_kg', 'selling_price_per_kg']
    search_fields = ['name']

    def quantity_available_display(self, obj):
        color = "red" if obj.quantity_available < 50 else "green"
        return format_html('<span style="color: {}; font-weight: bold;">{} كيلو</span>', color, obj.quantity_available)
    quantity_available_display.short_description = 'الكمية المتاحة'

@admin.register(DailyTransaction)
class DailyTransactionAdmin(admin.ModelAdmin):
    list_display = ['date', 'transaction_type_display', 'product', 'contact', 'weight', 'total_price_display']
    list_filter = ['transaction_type', 'date', 'product']
    search_fields = ['contact__name', 'product__name']
    date_hierarchy = 'date'

    def transaction_type_display(self, obj):
        bg_color = "#d4edda" if obj.transaction_type == 'out' else "#f8d7da"
        text_color = "#155724" if obj.transaction_type == 'out' else "#721c24"
        label = "صادر (بيع)" if obj.transaction_type == 'out' else "وارد (شراء)"
        return format_html('<span style="background: {}; color: {}; padding: 3px 10px; border-radius: 5px; font-weight: bold;">{}</span>', bg_color, text_color, label)
    transaction_type_display.short_description = 'النوع'

    def total_price_display(self, obj):
        return format_html('<b>{} ج.م</b>', obj.total_price)
    total_price_display.short_description = 'الإجمالي الكلي'

@admin.register(FinancialRecord)
class FinancialRecordAdmin(admin.ModelAdmin):
    list_display = ['get_date', 'get_contact', 'get_type', 'get_total', 'amount_paid', 'remaining_display', 'status_badge']
    list_filter = ['transaction__transaction_type', 'transaction__date']
    search_fields = ['transaction__contact__name']
    inlines = [PaymentInstallmentInline]
    readonly_fields = ['amount_paid']

    def get_date(self, obj): return obj.transaction.date
    get_date.short_description = 'التاريخ'

    def get_contact(self, obj): return obj.transaction.contact.name
    get_contact.short_description = 'التاجر'

    def get_type(self, obj):
        return "لنا (مبيعات)" if obj.transaction.transaction_type == 'out' else "علينا (مشتريات)"
    get_type.short_description = 'نوع الدين'

    def get_total(self, obj): return obj.transaction.total_price
    get_total.short_description = 'قيمة الفاتورة'

    def remaining_display(self, obj):
        color = "red" if obj.remaining_amount > 0 else "green"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.remaining_amount)
    remaining_display.short_description = 'المتبقي'

    def status_badge(self, obj):
        if obj.is_fully_paid:
            return format_html('<span style="color: white; background: #28a745; padding: 2px 8px; border-radius: 4px;">خالص</span>')
        return format_html('<span style="color: white; background: #ffc107; padding: 2px 8px; border-radius: 4px;">معلق</span>')
    status_badge.short_description = 'الحالة'

@admin.register(PaymentInstallment)
class PaymentInstallmentAdmin(admin.ModelAdmin):
    list_display = ['date_paid', 'get_contact', 'amount', 'get_product', 'notes']
    list_filter = ['date_paid', 'financial_record__transaction__contact']
    search_fields = ['financial_record__transaction__contact__name', 'notes']

    def get_contact(self, obj): 
        return obj.financial_record.transaction.contact.name if obj.financial_record else "حساب عام"
    get_contact.short_description = 'التاجر'

    def get_product(self, obj): 
        return obj.financial_record.transaction.product.name if obj.financial_record else "---"
    get_product.short_description = 'المنتج المرتبط'