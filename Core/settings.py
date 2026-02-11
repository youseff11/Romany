from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-+!!bxosf5+x(5(!g6fq%&*q139v7@#pk3ppxwtp00$btc)a305'

DEBUG = False

ALLOWED_HOSTS = [
    'romany.pythonanywhere.com', 
    '127.0.0.1', 
    'localhost',
]


INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'store',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'Core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'store.context_processors.all_contacts_processor',
            ],
        },
    },
]

WSGI_APPLICATION = 'Core.wsgi.application'


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Africa/Cairo'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'



# --- إعدادات قالب Jazzmin ---

JAZZMIN_SETTINGS = {
    # العنوان الذي يظهر في أعلى القائمة الجانبية (Sidebar)
    "site_brand": "نظام الإدارة",

    # الروابط في القائمة العلوية (Top Menu)
    "topmenu_links": [
        # رابط مباشر للصفحة الرئيسية للموقع
        {"name": "الرئيسية", "url": "/", "new_window": False},
        
        # رابط لعرض الموقع العام (يفتح في نافذة جديدة)
        {"name": "عرض الموقع", "url": "/", "new_window": True},
    ],

    # إضافة الرابط في القائمة الجانبية (Sidebar) مع أيقونة
    "custom_links": {
        "store": [  # اسم التطبيق الخاص بك
            {
                "name": "العودة للموقع", 
                "url": "/", 
                "icon": "fas fa-home", # أيقونة المنزل
                "permissions": ["auth.view_user"]
            },
        ],
    },

    # أيقونات الموديلات في القائمة الجانبية
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "store.Contact": "fas fa-address-book",
        "store.Product": "fas fa-boxes",
        "store.DailyTransaction": "fas fa-exchange-alt",
        "store.FinancialRecord": "fas fa-file-invoice-dollar",
        "store.HomeExpense": "fas fa-house-user",
        "store.Capital": "fas fa-money-bill-wave",
        "store.BankLoan": "fas fa-university",
    },
    
    # جعل القائمة الجانبية تفتح وتغلق (اختياري)
    "show_sidebar": True,
    "navigation_expanded": True,
}

# --- تنسيق واجهة المستخدم (اختياري لجعل الشكل أجمل) ---
JAZZMIN_UI_CONFIG = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-dark",
    "accent": "accent-primary",
    "navbar": "navbar-dark navbar-primary",
    "no_navbar_border": False,
    "navbar_fixed": False,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": False,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "default",
    "dark_mode_theme": None,
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success"
    }
}