from django.db import models
from django.contrib.auth.models import User
from dateutil.relativedelta import relativedelta
from django.db.models import Sum

# --- 1. نظام التجار والشركاء ---
class Contact(models.Model):
    name = models.CharField(max_length=200, verbose_name="اسم التاجر")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="رقم التليفون")
    notes = models.TextField(blank=True, null=True, verbose_name="ملاحظات")
    
    class Meta:
        verbose_name = "التاجر"
        verbose_name_plural = "التجار"

    def __str__(self):
        return self.name

# --- 2. نظام المخزن والمنتجات ---
class Product(models.Model):
    name = models.CharField(max_length=100, verbose_name="اسم المنتج")
    quantity_available = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="الكمية المتاحة (كيلو)")
    purchase_price_per_kg = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="سعر شراء الكيلو")
    selling_price_per_kg = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="سعر بيع الكيلو")

    class Meta:
        verbose_name = "المخزن"
        verbose_name_plural = "المخازن"

    def __str__(self):
        return self.name

# --- 3. نظام العمليات اليومية (وارد وصادر) ---
class DailyTransaction(models.Model):
    TRANSACTION_TYPES = (('in', 'وارد'), ('out', 'صادر'))
    
    date = models.DateField(verbose_name="التاريخ")
    transaction_type = models.CharField(max_length=3, choices=TRANSACTION_TYPES, verbose_name="النوع (وارد/صادر)")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="اسم المنتج")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, verbose_name="اسم التاجر")
    weight = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="الوزن")
    price_per_kg = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="السعر للكيلو")
    total_price = models.DecimalField(max_digits=12, decimal_places=2, editable=False, verbose_name="السعر المستحق الكلى")
    notes = models.TextField(blank=True, null=True, verbose_name="ملاحظات")

    class Meta:
        verbose_name = "حركة يومية"
        verbose_name_plural = "اليومية (وارد وصادر)"

    def save(self, *args, **kwargs):
        # حساب السعر الكلي قبل الحفظ
        self.total_price = self.weight * self.price_per_kg
        
        # تحديث كمية المخزن
        prod = self.product
        if self.transaction_type == 'in':
            prod.quantity_available += self.weight
        else:
            prod.quantity_available -= self.weight
        prod.save()
        
        super().save(*args, **kwargs)

# --- 4. السجلات المالية للمبيعات والمشتريات ---
class FinancialRecord(models.Model):
    transaction = models.OneToOneField(DailyTransaction, on_delete=models.CASCADE, verbose_name="الحركة المرتبطة")
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="المبلغ المدفوع")
    
    @property
    def remaining_amount(self):
        return self.transaction.total_price - self.amount_paid

    @property
    def is_fully_paid(self):
        return self.remaining_amount <= 0

    class Meta:
        verbose_name = "السجل المالي"
        verbose_name_plural = "المبالغ المستحقة (لينا وعلينا)"

    def __str__(self):
        tipo = "علينا" if self.transaction.transaction_type == 'in' else "لينا"
        return f"مبلغ {tipo} لـ {self.transaction.contact.name} - المتبقي: {self.remaining_amount}"

class PaymentInstallment(models.Model):
    financial_record = models.ForeignKey(FinancialRecord, on_delete=models.CASCADE, related_name="installments", verbose_name="السجل المالي")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="قيمة الدفعة")
    date_paid = models.DateField(auto_now_add=True, verbose_name="تاريخ الدفع")
    notes = models.TextField(blank=True, null=True, verbose_name="ملاحظات")

    class Meta:
        verbose_name = "دفعة سداد"
        verbose_name_plural = "أقساط السداد"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # تحديث المبلغ المدفوع في السجل المالي تلقائياً عند إضافة قسط
        record = self.financial_record
        total_installments = record.installments.aggregate(Sum('amount'))['amount__sum'] or 0
        record.amount_paid = total_installments
        record.save()

# --- 5. نظام البنك (المعدل: حساب آلي شامل الرسوم والتقريب) ---

class BankLoan(models.Model):
    bank_name = models.CharField(max_length=200, verbose_name="اسم البنك")
    loan_type = models.CharField(max_length=100, default="قرض عادي", verbose_name="نوع القرض")
    total_loan_amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="إجمالي مبلغ القرض (الأصل)")
    interest_rate_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة الفائدة (%)")
    loan_period_months = models.IntegerField(verbose_name="مدة القرض (بالشهور)")
    start_date = models.DateField(verbose_name="تاريخ بداية القرض")
    is_active = models.BooleanField(default=True, verbose_name="قرض نشط")

    class Meta:
        verbose_name = "قرض بنكي"
        verbose_name_plural = "قروض البنك"

    def __str__(self):
        return f"قرض {self.bank_name} - {self.total_loan_amount}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            total_interest = (self.total_loan_amount * self.interest_rate_percentage) / 100            
            principal_per_month = round(self.total_loan_amount / self.loan_period_months)
            interest_per_month = round(total_interest / self.loan_period_months)
            
            for i in range(self.loan_period_months):
                installment_date = self.start_date + relativedelta(months=i)
                
                BankInstallment.objects.create(
                    loan=self,
                    due_date=installment_date,
                    # الإجمالي المبدئي (سيتم تحديثه في دالة save الخاصة بالقسط)
                    total_installment_amount=principal_per_month + interest_per_month,
                    interest_component=interest_per_month,
                    principal_component=principal_per_month,
                    extra_charges=0,
                    is_paid=False
                )

class BankInstallment(models.Model):
    loan = models.ForeignKey(BankLoan, on_delete=models.CASCADE, related_name="installments", verbose_name="القرض المرتبط")
    due_date = models.DateField(verbose_name="تاريخ استحقاق القسط")
    total_installment_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="إجمالي القسط الشهرى")
    interest_component = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="قيمة الفائدة")
    principal_component = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="أصل المبلغ")
    extra_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="مصاريف إضافية")
    is_paid = models.BooleanField(default=False, verbose_name="تم الدفع")
    actual_payment_date = models.DateField(blank=True, null=True, verbose_name="تاريخ الدفع الفعلي")

    class Meta:
        verbose_name = "قسط بنكي"
        verbose_name_plural = "جدول أقساط البنك"
        ordering = ['due_date']

    def __str__(self):
        return f"قسط شهر {self.due_date.month} - {self.total_installment_amount}"

    def save(self, *args, **kwargs):
        self.principal_component = round(self.principal_component)
        self.interest_component = round(self.interest_component)
        self.extra_charges = round(self.extra_charges)        
        self.total_installment_amount = self.principal_component + self.interest_component + self.extra_charges        
        if self.is_paid and not self.actual_payment_date:
            from django.utils import timezone
            self.actual_payment_date = timezone.now().date()
        
        super().save(*args, **kwargs)