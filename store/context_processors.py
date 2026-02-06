from .models import Contact

def all_contacts_processor(request):
    """
    هذه الدالة تجعل قائمة التجار متاحة في جميع ملفات الـ Template
    باسم المتغير 'all_contacts'
    """
    if request.user.is_authenticated:
        return {
            'all_contacts': Contact.objects.all().order_by('name')
        }
    return {'all_contacts': []}