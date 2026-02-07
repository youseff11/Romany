from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Sum, Prefetch, F, ExpressionWrapper, DecimalField
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import (
    DailyTransaction, Product, FinancialRecord, PaymentInstallment, 
    Contact, BankLoan, BankInstallment, Capital
)
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages
from decimal import Decimal, InvalidOperation

# --- 1. قسم الإشارات (Signals) ---
@receiver(post_save, sender=DailyTransaction)
def create_financial_record(sender, instance, created, **kwargs):
    """إنشاء سجل مالي تلقائي عند تسجيل أي حركة بيع أو شراء"""
    if created:
        FinancialRecord.objects.get_or_create(transaction=instance)

# --- 2. لوحة التحكم (Dashboard) ---
@login_required
def dashboard(request):
    period = request.GET.get('period', 'all')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    transactions_queryset = DailyTransaction.objects.all()
    today = timezone.now().date()

    if period == 'today':
        transactions_queryset = transactions_queryset.filter(date=today)
    elif period == 'week':
        transactions_queryset = transactions_queryset.filter(date__gte=today - timedelta(days=7))
    elif period == 'month':
        transactions_queryset = transactions_queryset.filter(date__gte=today - timedelta(days=30))
    elif period == 'custom' and start_date and end_date:
        transactions_queryset = transactions_queryset.filter(date__range=[start_date, end_date])

    total_sales = transactions_queryset.filter(transaction_type='out').aggregate(total=Sum('total_price'))['total'] or 0
    total_purchases = transactions_queryset.filter(transaction_type='in').aggregate(total=Sum('total_price'))['total'] or 0

    cost_of_goods_sold = transactions_queryset.filter(transaction_type='out').annotate(
        cost=ExpressionWrapper(F('weight') * F('product__purchase_price_per_kg'), output_field=DecimalField())
    ).aggregate(total=Sum('cost'))['total'] or 0

    net_profit = total_sales - cost_of_goods_sold
    inventory = Product.objects.all()
    
    receivable_records = FinancialRecord.objects.filter(
        transaction__in=transactions_queryset.filter(transaction_type='out')
    ).annotate(
        remaining=ExpressionWrapper(F('transaction__total_price') - F('amount_paid'), output_field=DecimalField())
    ).filter(remaining__gt=0)
    
    receivable = receivable_records.aggregate(total=Sum('remaining'))['total'] or 0

    payable_records = FinancialRecord.objects.filter(
        transaction__in=transactions_queryset.filter(transaction_type='in')
    ).annotate(
        remaining=ExpressionWrapper(F('transaction__total_price') - F('amount_paid'), output_field=DecimalField())
    ).filter(remaining__gt=0)
    
    payable = payable_records.aggregate(total=Sum('remaining'))['total'] or 0

    debt_details = payable_records.select_related('transaction', 'transaction__contact', 'transaction__product').order_by('transaction__date')
    receivable_details = receivable_records.select_related('transaction', 'transaction__contact', 'transaction__product').order_by('transaction__date')

    recent_sales_queryset = transactions_queryset.filter(transaction_type='out').select_related('product', 'contact', 'financialrecord').order_by('-date')[:10]

    for sale in recent_sales_queryset:
        if hasattr(sale, 'financialrecord'):
            sale.remaining_amount = sale.financialrecord.remaining_amount
            sale.is_actually_paid = sale.financialrecord.is_fully_paid
        else:
            sale.remaining_amount = sale.total_price
            sale.is_actually_paid = False

    loan = BankLoan.objects.filter(is_active=True).first()
    bank_summary = {'total_remaining': 0, 'next_installment_amount': 0, 'next_installment_date': None, 'bank_name': "لا يوجد قرض نشط"}

    if loan:
        bank_insts = BankInstallment.objects.filter(loan=loan)
        total_flow = bank_insts.aggregate(Sum('total_installment_amount'))['total_installment_amount__sum'] or 0
        total_paid = bank_insts.filter(is_paid=True).aggregate(Sum('total_installment_amount'))['total_installment_amount__sum'] or 0
        next_inst = bank_insts.filter(is_paid=False, due_date__gte=today).order_by('due_date').first()
        
        bank_summary = {
            'total_remaining': total_flow - total_paid,
            'next_installment_amount': next_inst.total_installment_amount if next_inst else 0,
            'next_installment_date': next_inst.due_date if next_inst else None,
            'bank_name': loan.bank_name
        }

    upcoming_bank_alerts = BankInstallment.objects.filter(is_paid=False, due_date__range=[today, today + timedelta(days=3)]).select_related('loan')
    overdue_bank_alerts = BankInstallment.objects.filter(is_paid=False, due_date__lt=today).select_related('loan')

    context = {
        'total_sales': total_sales, 'total_purchases': total_purchases, 'net_profit': net_profit,
        'inventory': inventory, 'receivable': receivable, 'payable': payable,
        'debt_details': debt_details, 'receivable_details': receivable_details,
        'recent_sales': recent_sales_queryset, 'low_stock': Product.objects.filter(quantity_available__lt=50),
        'bank_summary': bank_summary, 'upcoming_bank_alerts': upcoming_bank_alerts, 'overdue_bank_alerts': overdue_bank_alerts,
    }
    return render(request, 'dashboard.html', context)

# --- 3. إدارة العمليات المالية والتجار ---

@login_required
def transactions_list(request):
    period = request.GET.get('period', 'all')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    transactions = DailyTransaction.objects.select_related('product', 'contact', 'financialrecord').all().order_by('-date')
    today = timezone.now().date()

    if period == 'today': transactions = transactions.filter(date=today)
    elif period == 'week': transactions = transactions.filter(date__gte=today - timedelta(days=7))
    elif period == 'month': transactions = transactions.filter(date__gte=today - timedelta(days=30))
    elif period == 'custom' and start_date and end_date: transactions = transactions.filter(date__range=[start_date, end_date])

    return render(request, 'transactions.html', {'transactions': transactions})

@login_required
def contact_detail(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    transactions = DailyTransaction.objects.filter(contact=contact).select_related('product', 'financialrecord').order_by('-date')
    
    products = Product.objects.all()
    today = timezone.now().date()
    
    # حساب الإجماليات
    total_out = transactions.filter(transaction_type='out').aggregate(Sum('total_price'))['total_price__sum'] or 0
    total_in = transactions.filter(transaction_type='in').aggregate(Sum('total_price'))['total_price__sum'] or 0
    
    # حساب الصافي المتبقي
    balance_us, balance_them = 0, 0
    records = FinancialRecord.objects.filter(transaction__contact=contact)
    for record in records:
        if record.transaction.transaction_type == 'out': 
            balance_us += record.remaining_amount
        else: 
            balance_them += record.remaining_amount

    net_balance = balance_us - balance_them
    
    payment_history = PaymentInstallment.objects.filter(
        financial_record__transaction__contact=contact
    ).select_related('financial_record__transaction__product', 'financial_record__transaction').order_by('-date_paid')

    context = {
        'contact': contact, 
        'transactions': transactions, 
        'products': products,
        'today': today,
        'total_out': total_out,
        'total_in': total_in, 
        'total_remaining': abs(net_balance), 
        'net_balance': net_balance,
        'payment_history': payment_history,
    }
    return render(request, 'contact_detail.html', context)

@user_passes_test(lambda u: u.is_superuser)
def add_transaction_direct(request):
    if request.method == 'POST':
        try:
            contact_id = request.POST.get('contact_id')
            product_id = request.POST.get('product_id')
            weight = Decimal(request.POST.get('weight'))
            price = Decimal(request.POST.get('price_per_kg'))
            t_type = request.POST.get('transaction_type')
            
            # 1. جلب المبلغ المدفوع الآن من الفورم (القيمة الافتراضية 0)
            amount_paid_now = request.POST.get('amount_paid_now', '0')
            paid_dec = Decimal(amount_paid_now) if amount_paid_now else Decimal(0)
            
            if t_type == 'out':
                product = get_object_or_404(Product, id=product_id)
                if product.quantity_available < weight:
                    messages.error(request, f"الكمية غير كافية بالمخزن! المتاح: {product.quantity_available}")
                    return redirect(request.META.get('HTTP_REFERER'))

            # 2. إنشاء الحركة التجارية مع تمرير المبلغ المدفوع
            # تأكد أن موديل DailyTransaction يحتوي على حقل باسم paid_amount_now
            DailyTransaction.objects.create(
                date=request.POST.get('date'),
                transaction_type=t_type,
                product_id=product_id,
                contact_id=contact_id,
                weight=weight,
                price_per_kg=price,
                paid_amount_now=paid_dec  
            )

            messages.success(request, "تمت إضافة العملية وتحديث السجلات المالية بنجاح.")
        except Exception as e:
            messages.error(request, f"خطأ في البيانات المرسلة: {e}")
            
    return redirect(request.META.get('HTTP_REFERER'))

@user_passes_test(lambda u: u.is_superuser)
def update_paid_amount(request, record_id):
    """تعديل: تسجيل الدفعة مع تحديد النوع (قبض/صرف) تلقائياً"""
    if request.method == 'POST':
        target_id = record_id if record_id != 0 else request.POST.get('record_id')
        payment_amount = request.POST.get('amount_paid')
        notes = request.POST.get('notes', '')
        
        record = get_object_or_404(FinancialRecord, id=target_id)
        
        try:
            amount_dec = Decimal(payment_amount)
            if amount_dec > 0:
                if record.transaction.transaction_type == 'out':
                    direction = "استلام نقدية (تحصيل من العميل)"
                else:
                    direction = "دفع نقدية (سداد للمورد)"
                
                full_notes = f"{direction} - {notes}" if notes else direction

                PaymentInstallment.objects.create(
                    financial_record=record,
                    amount=amount_dec,
                    notes=full_notes
                )
                messages.success(request, f"تم بنجاح {direction} بمبلغ {amount_dec}")
            else:
                messages.warning(request, "يجب إدخال مبلغ أكبر من الصفر.")
        except (InvalidOperation, ValueError):
            messages.error(request, "خطأ: يرجى إدخال رقم صحيح للمبلغ.")
    return redirect(request.META.get('HTTP_REFERER'))

# --- 4. نظام كشف حساب البنك والأقساط ---

@login_required
def bank_statement(request):
    loan = BankLoan.objects.filter(is_active=True).first()
    installments = []
    summary = {'total_flow': 0, 'total_interest': 0, 'total_paid': 0, 'total_remaining': 0}

    if loan:
        installments = BankInstallment.objects.filter(loan=loan).order_by('due_date')
        aggregate_data = installments.aggregate(total_flow=Sum('total_installment_amount'), total_interest=Sum('interest_component'))
        total_paid = installments.filter(is_paid=True).aggregate(Sum('total_installment_amount'))['total_installment_amount__sum'] or 0
        total_flow = aggregate_data['total_flow'] or 0
        summary = {
            'total_flow': total_flow, 'total_interest': aggregate_data['total_interest'] or 0,
            'total_paid': total_paid, 'total_remaining': total_flow - total_paid
        }

    return render(request, 'bank_statement.html', {'loan': loan, 'installments': installments, 'summary': summary})

@login_required
def add_bank_installment(request):
    return redirect('/admin/store/bankinstallment/add/')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def toggle_installment_status(request, inst_id):
    installment = get_object_or_404(BankInstallment, id=inst_id)
    installment.is_paid = not installment.is_paid
    installment.save()
    messages.success(request, f"تم تحديث حالة قسط شهر {installment.due_date.month} بنجاح.")
    return redirect('bank_statement')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def update_installment_charges(request, inst_id):
    if request.method == 'POST':
        new_charges = request.POST.get('extra_charges')
        if new_charges is not None:
            installment = get_object_or_404(BankInstallment, id=inst_id)
            try:
                installment.extra_charges = Decimal(new_charges)
                installment.save()
                messages.success(request, f"تم تحديث الرسوم وإعادة احتساب إجمالي قسط شهر {installment.due_date.month}.")
            except (InvalidOperation, ValueError):
                messages.error(request, "خطأ: يرجى إدخال رقم صحيح.")
            except Exception as e:
                messages.error(request, f"حدث خطأ: {str(e)}")
    return redirect('bank_statement')

# --- 5. لوحة السجلات الإدارية (Admin Logs) ---

@user_passes_test(lambda u: u.is_superuser)
def admin_logs_dashboard(request):
    # 1. جلب بارامترات التصفية من الرابط (GET Request)
    period = request.GET.get('period', 'all')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    today = timezone.now().date()

    # 2. تجهيز الكويري سيت الأساسية (بدون تصفية زمنية بعد)
    purchase_logs = DailyTransaction.objects.filter(transaction_type='in').select_related('product', 'contact')
    
    payment_logs = PaymentInstallment.objects.select_related(
        'financial_record__transaction', 
        'financial_record__transaction__contact'
    )

    # تجهيز سجل الأرباح مع حساب التكلفة والربح لكل عملية (للبيع فقط)
    profit_logs = DailyTransaction.objects.filter(transaction_type='out').select_related('product', 'contact').annotate(
        # تكلفة البضاعة = الوزن المباع × سعر شراء الكيلو المسجل في موديل المنتج
        cost_price=ExpressionWrapper(
            F('weight') * F('product__purchase_price_per_kg'), 
            output_field=DecimalField()
        ),
        # الربح الصافي للعملية = إجمالي سعر البيع - تكلفة البضاعة
        unit_profit=ExpressionWrapper(
            F('total_price') - (F('weight') * F('product__purchase_price_per_kg')), 
            output_field=DecimalField()
        )
    )

    # 3. تطبيق منطق التصفية الزمني على كافة السجلات
    if period == 'today':
        purchase_logs = purchase_logs.filter(date=today)
        payment_logs = payment_logs.filter(date_paid__date=today)
        profit_logs = profit_logs.filter(date=today)
    elif period == 'week':
        last_week = today - timedelta(days=7)
        purchase_logs = purchase_logs.filter(date__gte=last_week)
        payment_logs = payment_logs.filter(date_paid__date__gte=last_week)
        profit_logs = profit_logs.filter(date__gte=last_week)
    elif period == 'month':
        last_month = today - timedelta(days=30)
        purchase_logs = purchase_logs.filter(date__gte=last_month)
        payment_logs = payment_logs.filter(date_paid__date__gte=last_month)
        profit_logs = profit_logs.filter(date__gte=last_month)
    elif start_date and end_date:
        purchase_logs = purchase_logs.filter(date__range=[start_date, end_date])
        payment_logs = payment_logs.filter(date_paid__date__range=[start_date, end_date])
        profit_logs = profit_logs.filter(date__range=[start_date, end_date])

    # 4. حساب إجمالي الأرباح للفترة المحددة
    total_profit_period = profit_logs.aggregate(total=Sum('unit_profit'))['total'] or 0

    # 5. حساب الإحصائيات العامة (الوضع الحالي)
    capital_obj = Capital.objects.first()
    cash_in_hand = capital_obj.initial_amount if capital_obj else Decimal(0)

    products = Product.objects.all()
    total_inventory_value = sum(p.quantity_available * p.purchase_price_per_kg for p in products)

    receivable = FinancialRecord.objects.filter(transaction__transaction_type='out').annotate(
        rem=ExpressionWrapper(F('transaction__total_price') - F('amount_paid'), output_field=DecimalField())
    ).aggregate(total=Sum('rem'))['total'] or 0

    payable = FinancialRecord.objects.filter(transaction__transaction_type='in').annotate(
        rem=ExpressionWrapper(F('transaction__total_price') - F('amount_paid'), output_field=DecimalField())
    ).aggregate(total=Sum('rem'))['total'] or 0

    loan = BankLoan.objects.filter(is_active=True).first()
    bank_remaining = BankInstallment.objects.filter(loan=loan, is_paid=False).aggregate(
        total=Sum('total_installment_amount'))['total'] or 0 if loan else 0

    total_capital = (cash_in_hand + total_inventory_value + receivable) - (payable + bank_remaining)

    # 6. تمرير البيانات للـ Template
    context = {
        # بيانات الإحصائيات (البطاقات العلوية)
        'cash_in_hand': cash_in_hand,
        'total_inventory_value': total_inventory_value,
        'total_capital': total_capital,
        'receivable': receivable,
        'payable': payable,
        'bank_remaining': bank_remaining,
        'total_profit_period': total_profit_period,
        
        # سجلات الجداول
        'purchase_logs': purchase_logs.order_by('-date'),
        'payment_logs': payment_logs.order_by('-date_paid')[:20],
        'profit_logs': profit_logs.order_by('-date'),
        
        # بيانات التصفية والوقت
        'today': today,
        'start_date': start_date,
        'end_date': end_date,
        'period': period,
    }

    return render(request, 'admin_logs.html', context)