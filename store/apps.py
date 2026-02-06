from django.apps import AppConfig

class StoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField' # هذا السطر سيخفي كل التحذيرات
    name = 'store'