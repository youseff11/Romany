from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Sum, Prefetch, F, ExpressionWrapper, DecimalField
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import DailyTransaction, Product, FinancialRecord, PaymentInstallment, Contact, BankLoan, BankInstallment 
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages

# --- 1. قسم الـ Signals ---

@receiver(post_save, sender=DailyTransaction)
def create_financial_record_and_installment(sender, instance, created, **kwargs):
    if created:
        financial_record, created_fr = FinancialRecord.objects.get_or_create(transaction=instance)
        
        PaymentInstallment.objects.create(
            financial_record=financial_record,
            amount=0,  
            notes="سجل دفع آلي (قيد الانتظار)"
        )

# --- 2. دالة تحديث المبلغ المدفوع (للمسؤول فقط) ---

@user_passes_test(lambda u: u.is_superuser)
def update_paid_amount(request, record_id):
    if request.method == 'POST':
        new_amount = request.POST.get('amount_paid')
        record = get_object_or_404(FinancialRecord, id=record_id)
        try:
            record.amount_paid = new_amount
            record.save()
            messages.success(request, "تم تحديث المبلغ المدفوع بنجاح.")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء التحديث: {e}")
    
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

# --- 3. دالة لوحة التحكم (Dashboard) ---

@login_required
def dashboard(request):
    period = request.GET.get('period', 'all')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    transactions_queryset = DailyTransaction.objects.all()
    today = timezone.now().date()

    # --- فلترة العمليات بناءً على الفترة ---
    if period == 'today':
        transactions_queryset = transactions_queryset.filter(date=today)
    elif period == 'week':
        transactions_queryset = transactions_queryset.filter(date__gte=today - timedelta(days=7))
    elif period == 'month':
        transactions_queryset = transactions_queryset.filter(date__gte=today - timedelta(days=30))
    elif period == 'custom' and start_date and end_date:
        transactions_queryset = transactions_queryset.filter(date__range=[start_date, end_date])

    # --- حسابات الإحصائيات ---
    total_sales = transactions_queryset.filter(transaction_type='out').aggregate(
        total=Sum('total_price'))['total'] or 0

    total_purchases = transactions_queryset.filter(transaction_type='in').aggregate(
        total=Sum('total_price'))['total'] or 0

    cost_of_goods_sold = transactions_queryset.filter(transaction_type='out').annotate(
        cost=ExpressionWrapper(
            F('weight') * F('product__purchase_price_per_kg'), 
            output_field=DecimalField()
        )
    ).aggregate(total=Sum('cost'))['total'] or 0

    net_profit = total_sales - cost_of_goods_sold
    
    inventory = Product.objects.all()
    
    # --- حساب المبالغ المستحقة (لينا) ---
    receivable_records = FinancialRecord.objects.filter(
        transaction__in=transactions_queryset.filter(transaction_type='out')
    ).annotate(
        remaining=ExpressionWrapper(F('transaction__total_price') - F('amount_paid'), output_field=DecimalField())
    ).filter(remaining__gt=0)
    
    receivable = receivable_records.aggregate(total=Sum('remaining'))['total'] or 0

    # --- حساب المبالغ المطلوبة (علينا) ---
    payable_records = FinancialRecord.objects.filter(
        transaction__in=transactions_queryset.filter(transaction_type='in')
    ).annotate(
        remaining=ExpressionWrapper(F('transaction__total_price') - F('amount_paid'), output_field=DecimalField())
    ).filter(remaining__gt=0)
    
    payable = payable_records.aggregate(total=Sum('remaining'))['total'] or 0

    debt_details = payable_records.select_related('transaction', 'transaction__contact', 'transaction__product').order_by('transaction__date')
    receivable_details = receivable_records.select_related('transaction', 'transaction__contact', 'transaction__product').order_by('transaction__date')

    # --- أحدث العمليات ---
    recent_sales_queryset = transactions_queryset.filter(
        transaction_type='out'
    ).select_related('product', 'contact', 'financialrecord').order_by('-date')[:10]

    for sale in recent_sales_queryset:
        if hasattr(sale, 'financialrecord'):
            sale.remaining_amount = sale.financialrecord.remaining_amount
            sale.is_actually_paid = sale.financialrecord.is_fully_paid
        else:
            sale.remaining_amount = sale.total_price
            sale.is_actually_paid = False

    # ============================================================
    # --- نظام التنبيهات وحسابات البنك للكارت (الإضافة المحدثة) ---
    # ============================================================
    
    # 1. جلب بيانات القرض والملخص للكارت الأزرق
    loan = BankLoan.objects.filter(is_active=True).first()
    bank_summary = {
        'total_remaining': 0,
        'next_installment_amount': 0,
        'next_installment_date': None,
        'bank_name': "لا يوجد قرض نشط"
    }

    if loan:
        bank_insts = BankInstallment.objects.filter(loan=loan)
        total_flow = bank_insts.aggregate(Sum('total_installment_amount'))['total_installment_amount__sum'] or 0
        total_paid = bank_insts.filter(is_paid=True).aggregate(Sum('total_installment_amount'))['total_installment_amount__sum'] or 0
        
        # القسط القادم (أول قسط غير مدفوع تاريخه اليوم أو مستقبلاً)
        next_inst = bank_insts.filter(is_paid=False, due_date__gte=today).order_by('due_date').first()
        
        bank_summary = {
            'total_remaining': total_flow - total_paid,
            'next_installment_amount': next_inst.total_installment_amount if next_inst else 0,
            'next_installment_date': next_inst.due_date if next_inst else None,
            'bank_name': loan.bank_name
        }

    # 2. جلب التنبيهات (كما كانت في كودك)
    upcoming_bank_alerts = BankInstallment.objects.filter(
        is_paid=False, 
        due_date__range=[today, today + timedelta(days=3)]
    ).select_related('loan')

    overdue_bank_alerts = BankInstallment.objects.filter(
        is_paid=False, 
        due_date__lt=today
    ).select_related('loan')

    # ============================================================

    context = {
        'total_sales': total_sales,
        'total_purchases': total_purchases,
        'net_profit': net_profit,
        'inventory': inventory,
        'receivable': receivable,
        'payable': payable,
        'debt_details': debt_details,
        'receivable_details': receivable_details,
        'recent_sales': recent_sales_queryset,
        'low_stock': Product.objects.filter(quantity_available__lt=50),
        # المتغيرات الجديدة والملخص
        'bank_summary': bank_summary,
        'upcoming_bank_alerts': upcoming_bank_alerts,
        'overdue_bank_alerts': overdue_bank_alerts,
    }
    
    return render(request, 'dashboard.html', context)

# --- 4. دالة قائمة العمليات ---

@login_required
def transactions_list(request):
    period = request.GET.get('period', 'all')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    transactions = DailyTransaction.objects.select_related(
        'product', 'contact', 'financialrecord'
    ).all().order_by('-date')
    
    today = timezone.now().date()

    if period == 'today':
        transactions = transactions.filter(date=today)
    elif period == 'week':
        transactions = transactions.filter(date__gte=today - timedelta(days=7))
    elif period == 'month':
        transactions = transactions.filter(date__gte=today - timedelta(days=30))
    elif period == 'custom' and start_date and end_date:
        transactions = transactions.filter(date__range=[start_date, end_date])

    return render(request, 'transactions.html', {'transactions': transactions})

# --- 5. دالة تفاصيل التاجر ---

@login_required
def contact_detail(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    
    transactions = DailyTransaction.objects.filter(contact=contact).select_related(
        'product', 'financialrecord'
    ).order_by('-date')
    
    total_out = transactions.filter(transaction_type='out').aggregate(Sum('total_price'))['total_price__sum'] or 0
    total_in = transactions.filter(transaction_type='in').aggregate(Sum('total_price'))['total_price__sum'] or 0
    
    balance_us = 0
    balance_them = 0
    
    records = FinancialRecord.objects.filter(transaction__contact=contact)
    for record in records:
        if record.transaction.transaction_type == 'out':
            balance_us += record.remaining_amount
        else:
            balance_them += record.remaining_amount

    net_balance = balance_us - balance_them
    total_remaining = abs(net_balance)

    context = {
        'contact': contact,
        'transactions': transactions,
        'total_out': total_out,
        'total_in': total_in,
        'total_remaining': total_remaining,
        'net_balance': net_balance,
    }
    return render(request, 'contact_detail.html', context)

# --- 6. دالة كشف حساب البنك (المضافة حديثاً) ---

@login_required
def bank_statement(request):
    loan = BankLoan.objects.filter(is_active=True).first()
    installments = []
    summary = {
        'total_flow': 0,
        'total_interest': 0,
        'total_paid': 0,
        'total_remaining': 0
    }

    if loan:
        installments = BankInstallment.objects.filter(loan=loan).order_by('due_date')
        
        # حسابات مجمعة
        aggregate_data = installments.aggregate(
            total_flow=Sum('total_installment_amount'),
            total_interest=Sum('interest_component'),
        )
        
        # حساب ما تم دفعه والمتبقي برمجياً
        total_paid = installments.filter(is_paid=True).aggregate(Sum('total_installment_amount'))['total_installment_amount__sum'] or 0
        total_flow = aggregate_data['total_flow'] or 0
        
        summary = {
            'total_flow': total_flow,
            'total_interest': aggregate_data['total_interest'] or 0,
            'total_paid': total_paid,
            'total_remaining': total_flow - total_paid
        }

    context = {
        'loan': loan,
        'installments': installments,
        'summary': summary,
    }
    return render(request, 'bank_statement.html', context)

@login_required
def add_bank_installment(request):
    return redirect('/admin/store/bankinstallment/add/')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def toggle_installment_status(request, inst_id):
    installment = get_object_or_404(BankInstallment, id=inst_id)
    installment.is_paid = not installment.is_paid  # يعكس الحالة (إذا مدفوع يجعله معلق والعكس)
    installment.save()
    messages.success(request, f"تم تحديث حالة قسط شهر {installment.due_date.month} بنجاح.")
    return redirect('bank_statement')