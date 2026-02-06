from django.contrib import admin
from django.urls import path, include # تأكد من استيراد include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('baton/', include('baton.urls')), # هذا السطر هو الحل للنقص المسبب للخطأ
    path('', include('store.urls')), # مسارات تطبيقك
]