from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Sum, Prefetch, F, ExpressionWrapper, DecimalField
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import (
    DailyTransaction, Product, FinancialRecord, PaymentInstallment, 
    Contact, BankLoan, BankInstallment, Capital, HomeExpense, ContactExpense
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

    # --- فلترة المدة الزمنية ---
    if period == 'today':
        transactions_queryset = transactions_queryset.filter(date=today)
    elif period == 'week':
        transactions_queryset = transactions_queryset.filter(date__gte=today - timedelta(days=7))
    elif period == 'month':
        transactions_queryset = transactions_queryset.filter(date__gte=today - timedelta(days=30))
    elif period == 'custom' and start_date and end_date:
        transactions_queryset = transactions_queryset.filter(date__range=[start_date, end_date])

    # --- حسابات المبيعات والمشتريات ---
    total_sales = transactions_queryset.filter(transaction_type='out').aggregate(total=Sum('total_price'))['total'] or 0
    total_purchases = transactions_queryset.filter(transaction_type='in').aggregate(total=Sum('total_price'))['total'] or 0
    
    cost_of_goods_sold = transactions_queryset.filter(transaction_type='out').annotate(
        cost=ExpressionWrapper(F('weight') * F('product__purchase_price_per_kg'), output_field=DecimalField())
    ).aggregate(total=Sum('cost'))['total'] or 0
    net_profit = total_sales - cost_of_goods_sold

    # --- 1. مستحقاتنا (لنا) ---
    # مبالغ مبيعات لم تُحصل بعد
    receivable_records = FinancialRecord.objects.filter(
        transaction__in=transactions_queryset.filter(transaction_type='out')
    ).annotate(
        remaining=ExpressionWrapper(F('transaction__total_price') - F('amount_paid'), output_field=DecimalField())
    ).filter(remaining__gt=0)
    
    # مبالغ دفعناها نحن (سلف أو مصاريف على التاجر)
    receivable_expenses = ContactExpense.objects.filter(payer_type='us').select_related('contact').order_by('-date')
    
    total_receivable = (receivable_records.aggregate(total=Sum('remaining'))['total'] or 0) + \
                       (receivable_expenses.aggregate(total=Sum('amount'))['total'] or 0)

    # --- 2. مديونيات (علينا) ---
    # مبالغ مشتريات لم تُدفع بعد
    payable_records = FinancialRecord.objects.filter(
        transaction__in=transactions_queryset.filter(transaction_type='in')
    ).annotate(
        remaining=ExpressionWrapper(F('transaction__total_price') - F('amount_paid'), output_field=DecimalField())
    ).filter(remaining__gt=0)
    
    # مبالغ دفعها التاجر عنا (ديون علينا)
    pending_expenses = ContactExpense.objects.filter(payer_type='them').select_related('contact').order_by('-date')
    
    total_payable = (payable_records.aggregate(total=Sum('remaining'))['total'] or 0) + \
                     (pending_expenses.aggregate(total=Sum('amount'))['total'] or 0)

    # --- البنك والعمليات الأخيرة ---
    debt_details = payable_records.select_related('transaction', 'transaction__contact', 'transaction__product').order_by('transaction__date')
    receivable_details = receivable_records.select_related('transaction', 'transaction__contact', 'transaction__product').order_by('transaction__date')
    recent_sales = transactions_queryset.filter(transaction_type='out').select_related('product', 'contact', 'financialrecord').order_by('-date')[:10]

    # (كود البنك يظل كما هو دون تغيير)
    loan = BankLoan.objects.filter(is_active=True).first()
    bank_summary = {'total_remaining': 0, 'bank_name': "لا يوجد قرض نشط"}
    if loan:
        bank_insts = BankInstallment.objects.filter(loan=loan)
        total_flow = bank_insts.aggregate(Sum('total_installment_amount'))['total_installment_amount__sum'] or 0
        total_paid = bank_insts.filter(is_paid=True).aggregate(Sum('total_installment_amount'))['total_installment_amount__sum'] or 0
        next_inst = bank_insts.filter(is_paid=False, due_date__gte=today).order_by('due_date').first()
        bank_summary = {'total_remaining': total_flow - total_paid, 'next_installment_amount': next_inst.total_installment_amount if next_inst else 0,
                        'next_installment_date': next_inst.due_date if next_inst else None, 'bank_name': loan.bank_name}

    context = {
        'total_sales': total_sales, 'net_profit': net_profit,
        'receivable': total_receivable, 'payable': total_payable,
        'receivable_details': receivable_details, 'debt_details': debt_details,
        'receivable_expenses': receivable_expenses, 'pending_expenses': pending_expenses,
        'recent_sales': recent_sales, 'inventory': Product.objects.all(),
        'bank_summary': bank_summary,
        'upcoming_bank_alerts': BankInstallment.objects.filter(is_paid=False, due_date__range=[today, today + timedelta(days=3)]),
        'overdue_bank_alerts': BankInstallment.objects.filter(is_paid=False, due_date__lt=today),
    }
    return render(request, 'dashboard.html', context)
# --- 3. إدارة العمليات المالية والتجار ---

@login_required
def transactions_list(request):
    period = request.GET.get('period', 'all')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    today = timezone.now().date()

    # 1. جلب الحركات التجارية (وارد وصادر)
    transactions = DailyTransaction.objects.select_related('product', 'contact', 'financialrecord').all().order_by('-date')

    # 2. جلب مصاريف التجار ومصاريف البيت
    contact_expenses = ContactExpense.objects.select_related('contact').all().order_by('-date')
    home_expenses = HomeExpense.objects.all().order_by('-date')

    # --- تطبيق الفلترة الزمنية على الكل ---
    if period == 'today':
        transactions = transactions.filter(date=today)
        contact_expenses = contact_expenses.filter(date=today)
        home_expenses = home_expenses.filter(date=today)
    elif period == 'week':
        last_week = today - timedelta(days=7)
        transactions = transactions.filter(date__gte=last_week)
        contact_expenses = contact_expenses.filter(date__gte=last_week)
        home_expenses = home_expenses.filter(date__gte=last_week)
    elif period == 'month':
        last_month = today - timedelta(days=30)
        transactions = transactions.filter(date__gte=last_month)
        contact_expenses = contact_expenses.filter(date__gte=last_month)
        home_expenses = home_expenses.filter(date__gte=last_month)
    elif period == 'custom' and start_date and end_date:
        transactions = transactions.filter(date__range=[start_date, end_date])
        contact_expenses = contact_expenses.filter(date__range=[start_date, end_date])
        home_expenses = home_expenses.filter(date__range=[start_date, end_date])

    context = {
        'transactions': transactions,
        'contact_expenses': contact_expenses, # تم الإضافة
        'home_expenses': home_expenses,       # تم الإضافة
    }

    return render(request, 'transactions.html', context)

@login_required
def contact_detail(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    transactions = DailyTransaction.objects.filter(contact=contact).select_related('product', 'financialrecord').order_by('-date')
    
    contact_expenses = ContactExpense.objects.filter(contact=contact).order_by('-date')
    
    products = Product.objects.all()
    today = timezone.now().date()
    
    balance_us, balance_them = 0, 0
    records = FinancialRecord.objects.filter(transaction__contact=contact)
    for record in records:
        if record.transaction.transaction_type == 'out': 
            balance_us += record.remaining_amount
        else: 
            balance_them += record.remaining_amount

    total_expenses = contact_expenses.aggregate(Sum('amount'))['amount__sum'] or 0

    us_paid_expenses = contact_expenses.filter(payer_type='us').aggregate(Sum('amount'))['amount__sum'] or 0
    balance_us += us_paid_expenses
    
    them_paid_expenses = contact_expenses.filter(payer_type='them').aggregate(Sum('amount'))['amount__sum'] or 0
    balance_them += them_paid_expenses

    net_balance = balance_us - balance_them
    
    payment_history = PaymentInstallment.objects.filter(
        financial_record__transaction__contact=contact
    ).select_related('financial_record__transaction__product', 'financial_record__transaction').order_by('-date_paid')

    total_out = transactions.filter(transaction_type='out').aggregate(Sum('total_price'))['total_price__sum'] or 0
    total_in = transactions.filter(transaction_type='in').aggregate(Sum('total_price'))['total_price__sum'] or 0

    context = {
        'contact': contact, 
        'transactions': transactions, 
        'contact_expenses': contact_expenses,
        'products': products,
        'today': today,
        'total_out': total_out,
        'total_in': total_in,
        'total_expenses': total_expenses,
        'total_remaining': abs(net_balance), 
        'net_balance': net_balance,
        'payment_history': payment_history,
    }
    return render(request, 'contact_detail.html', context)

@user_passes_test(lambda u: u.is_superuser)
def add_contact_expense(request):
    if request.method == 'POST':
        try:
            contact_id = request.POST.get('contact_id')
            amount = Decimal(request.POST.get('amount'))
            payer_type = request.POST.get('payer_type') 
            notes = request.POST.get('notes')
            date = request.POST.get('date') or timezone.now().date()

            # هذا السطر سيقوم بإنشاء المصروف.. 
            # والـ Signal الموجود في models.py سيتكفل بالخصم من الخزنة تلقائياً مرة واحدة فقط.
            ContactExpense.objects.create(
                contact_id=contact_id,
                amount=amount,
                payer_type=payer_type,
                notes=notes,
                date=date
            )

            messages.success(request, "تم تسجيل المصروف بنجاح.")
        except Exception as e:
            messages.error(request, f"خطأ في البيانات: {e}")
            
    return redirect(request.META.get('HTTP_REFERER'))

@user_passes_test(lambda u: u.is_superuser)
def edit_contact_expense(request, expense_id):
    if request.method == 'POST':
        expense = get_object_or_404(ContactExpense, id=expense_id)
        old_amount = expense.amount
        old_payer = expense.payer_type
        
        try:
            new_amount = Decimal(request.POST.get('amount'))
            new_payer = request.POST.get('payer_type')
            expense.notes = request.POST.get('notes')
            expense.amount = new_amount
            expense.payer_type = new_payer
            expense.save()

            # تحديث الخزنة بناءً على التغيير
            capital = Capital.objects.first()
            if capital:
                # إلغاء تأثير المبلغ القديم
                if old_payer == 'us':
                    capital.initial_amount += old_amount
                
                # إضافة تأثير المبلغ الجديد
                if new_payer == 'us':
                    capital.initial_amount -= new_amount
                
                capital.save()

            messages.success(request, "تم تعديل المصروف وتحديث الخزنة.")
        except Exception as e:
            messages.error(request, f"خطأ: {e}")
            
    return redirect(request.META.get('HTTP_REFERER'))

@user_passes_test(lambda u: u.is_superuser)
def add_transaction_direct(request):
    if request.method == 'POST':
        try:
            contact_id = request.POST.get('contact_id')
            product_id = request.POST.get('product_id')
            weight = Decimal(request.POST.get('weight'))
            price = Decimal(request.POST.get('price_per_kg'))
            t_type = request.POST.get('transaction_type')
            
            amount_paid_now = request.POST.get('amount_paid_now', '0')
            paid_dec = Decimal(amount_paid_now) if amount_paid_now else Decimal(0)
            
            if t_type == 'out':
                product = get_object_or_404(Product, id=product_id)
                if product.quantity_available < weight:
                    messages.error(request, f"الكمية غير كافية بالمخزن! المتاح: {product.quantity_available}")
                    return redirect(request.META.get('HTTP_REFERER'))

            DailyTransaction.objects.create(
                date=request.POST.get('date'),
                transaction_type=t_type,
                product_id=product_id,
                contact_id=contact_id,
                weight=weight,
                price_per_kg=price,
                paid_amount_now=paid_dec  
            )

            messages.success(request, "تمت إضافة العملية بنجاح.")
        except Exception as e:
            messages.error(request, f"خطأ في البيانات: {e}")
            
    return redirect(request.META.get('HTTP_REFERER'))

@user_passes_test(lambda u: u.is_superuser)
def update_paid_amount(request, record_id):
    if request.method == 'POST':
        target_id = record_id if record_id != 0 else request.POST.get('record_id')
        payment_amount = request.POST.get('amount_paid')
        notes = request.POST.get('notes', '')
        
        record = get_object_or_404(FinancialRecord, id=target_id)
        
        try:
            amount_dec = Decimal(payment_amount)
            if amount_dec > 0:
                if record.transaction.transaction_type == 'out':
                    direction = "تحصيل نقدية"
                    change = amount_dec
                else:
                    direction = "سداد نقدية"
                    change = -amount_dec
                
                full_notes = f"{direction} - {notes}" if notes else direction

                PaymentInstallment.objects.create(
                    financial_record=record,
                    amount=amount_dec,
                    notes=full_notes
                )

                capital = Capital.objects.first()
                if capital:
                    capital.initial_amount += change
                    capital.save()

                messages.success(request, f"تم {direction} بمبلغ {amount_dec}.")
            else:
                messages.warning(request, "يجب إدخال مبلغ أكبر من الصفر.")
        except (InvalidOperation, ValueError):
            messages.error(request, "خطأ في المبلغ.")
    return redirect(request.META.get('HTTP_REFERER'))

@user_passes_test(lambda u: u.is_superuser)
def edit_payment_amount(request, payment_id):
    if request.method == 'POST':
        payment = get_object_or_404(PaymentInstallment, id=payment_id)
        old_amount = payment.amount
        new_amount_str = request.POST.get('new_amount')
        
        try:
            new_amount = Decimal(new_amount_str)
            difference = new_amount - old_amount
            transaction_type = payment.financial_record.transaction.transaction_type
            
            payment.amount = new_amount
            payment.save()

            capital = Capital.objects.first()
            if capital:
                if transaction_type == 'out':
                    capital.initial_amount += difference
                else:
                    capital.initial_amount -= difference
                capital.save()

            messages.success(request, "تم تعديل الدفعة وتحديث الخزنة.")
        except (InvalidOperation, ValueError):
            messages.error(request, "خطأ في المبلغ.")
    return redirect(request.META.get('HTTP_REFERER'))

# --- 4. نظام البنك والأقساط ---

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
    
    capital = Capital.objects.first()
    if capital:
        if installment.is_paid:
            capital.initial_amount -= installment.total_installment_amount
        else:
            capital.initial_amount += installment.total_installment_amount
        capital.save()
        
    messages.success(request, "تم تحديث القسط وتعديل الخزنة.")
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
                messages.success(request, "تم تحديث الرسوم.")
            except (InvalidOperation, ValueError):
                messages.error(request, "خطأ في الرقم.")
    return redirect('bank_statement')

# --- 5. سجلات المدير (Admin Logs) ---

@user_passes_test(lambda u: u.is_superuser)
def admin_logs_dashboard(request):
    period = request.GET.get('period', 'all')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    today = timezone.now().date()

    purchase_logs = DailyTransaction.objects.filter(transaction_type='in').select_related('product', 'contact', 'financialrecord').annotate(
        paid_amount=F('financialrecord__amount_paid')
    )
    
    payment_logs = PaymentInstallment.objects.select_related(
        'financial_record__transaction', 
        'financial_record__transaction__contact'
    )

    profit_logs = DailyTransaction.objects.filter(transaction_type='out').select_related('product', 'contact', 'financialrecord').annotate(
        paid_amount=F('financialrecord__amount_paid'),
        unit_profit=ExpressionWrapper(
            F('total_price') - (F('weight') * F('product__purchase_price_per_kg')), 
            output_field=DecimalField()
        )
    )

    home_expenses = HomeExpense.objects.all()
    contact_expenses = ContactExpense.objects.select_related('contact').all()

    if period == 'today':
        purchase_logs = purchase_logs.filter(date=today)
        profit_logs = profit_logs.filter(date=today)
        home_expenses = home_expenses.filter(date=today)
        contact_expenses = contact_expenses.filter(date=today)
    elif period == 'week':
        last_week = today - timedelta(days=7)
        purchase_logs = purchase_logs.filter(date__gte=last_week)
        profit_logs = profit_logs.filter(date__gte=last_week)
        home_expenses = home_expenses.filter(date__gte=last_week)
        contact_expenses = contact_expenses.filter(date__gte=last_week)
    elif period == 'month':
        last_month = today - timedelta(days=30)
        purchase_logs = purchase_logs.filter(date__gte=last_month)
        profit_logs = profit_logs.filter(date__gte=last_month)
        home_expenses = home_expenses.filter(date__gte=last_month)
        contact_expenses = contact_expenses.filter(date__gte=last_month)
    elif start_date and end_date:
        purchase_logs = purchase_logs.filter(date__range=[start_date, end_date])
        profit_logs = profit_logs.filter(date__range=[start_date, end_date])
        home_expenses = home_expenses.filter(date__range=[start_date, end_date])
        contact_expenses = contact_expenses.filter(date__range=[start_date, end_date])

    total_sales_profit = profit_logs.aggregate(total=Sum('unit_profit'))['total'] or 0
    total_home_expenses = home_expenses.aggregate(total=Sum('amount'))['total'] or 0
    total_contact_expenses = contact_expenses.aggregate(total=Sum('amount'))['total'] or 0
    
    net_profit_period = total_sales_profit - (total_home_expenses + total_contact_expenses)

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

    context = {
        'cash_in_hand': cash_in_hand,
        'total_inventory_value': total_inventory_value,
        'total_capital': total_capital,
        'receivable': receivable,
        'payable': payable,
        'bank_remaining': bank_remaining,
        'total_profit_period': total_sales_profit,
        'total_home_expenses': total_home_expenses,
        'total_contact_expenses': total_contact_expenses,
        'net_profit_period': net_profit_period,
        'purchase_logs': purchase_logs.order_by('-date'),
        'payment_logs': payment_logs.order_by('-date_paid')[:20],
        'profit_logs': profit_logs.order_by('-date'),
        'home_expenses': home_expenses.order_by('-date'),
        'contact_expenses': contact_expenses.order_by('-date'),
        'today': today,
        'start_date': start_date,
        'end_date': end_date,
        'period': period,
    }

    return render(request, 'admin_logs.html', context)