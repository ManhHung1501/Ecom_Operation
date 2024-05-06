"""
URL configuration for woo-commerce_operation project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, re_path, include
from dashboard import views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.views import LoginView, LogoutView
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

schema_view = get_schema_view(
    openapi.Info(
        title="Ecom Operation API",
        default_version='v1',),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('woo-commerce/docs/', schema_view.with_ui('swagger', cache_timeout=0),
         name='schema-swagger-ui'),
    path('woo-commerce/admin/', admin.site.urls),
    path('woo-commerce', views.woocommerce_webhook),
    path('woo-commerce/webhook/sendgrid/', views.sendgrid_webhook),
    path('woo-commerce/report/', views.view_report),
    path('woo-commerce/logout/', LogoutView.as_view(next_page='/'), name='logout'),
    path('woo-commerce/info_orders/<str:order_id>/', views.read_an_order, name='read_an_order'),
    path('woo-commerce/orders/', views.read_or_create_orders, name='read_or_create_orders'),
    path('woo-commerce/orders/<str:order_id>/', views.rud_an_order, name='RUD_an_order'),
    path('woo-commerce/orders/<str:order_id>/disputes', views.read_dispute, name='get_dispute'),
    path('woo-commerce/orders/<str:order_id>/resend/', views.resend_order, name='resend_order'),
    path('woo-commerce/orders/<str:order_id>/refund/', views.refund_order, name='refund_order'),
    path('woo-commerce/batch_resend_order/', views.batch_resend_order, name='batch_resend_order'),
    path('woo-commerce/batch_create_item/', views.batch_create_item, name='batch_create_item'),
    path('woo-commerce/items/', views.read_or_create_items, name='read_or_create_items'),
    path('woo-commerce/items/<str:line_item_id>/', views.rud_an_item, name='RUD_an_item'),
    path('woo-commerce/shippings/', views.read_or_create_shippings, name='read_or_create_shippings'),
    path('woo-commerce/batches/', views.read_or_create_batches, name='view_batches'),
    path('woo-commerce/batches/<str:batch_id>/', views.rud_a_batch, name='rud_a_batch'),
    path('woo-commerce/sites/', views.view_sites, name='list_all_sites'),
    path('woo-commerce/sites/<str:site_id>/', views.rud_a_site, name='RUD_asite'),
    path('woo-commerce/variations/', views.read_variations, name='read_variations'),
    path('woo-commerce/product_sites/', views.read_product_sites, name='read_product_sites'),
    path('woo-commerce/up_file/sku/', views.upload_sku_file, name='upload_sku_file'),
    path('woo-commerce/up_file/tracking/', views.upload_tracking_file, name='upload_tracking_file'),
    path('woo-commerce/up_file/evidence_image/', views.upload_image, name='evidence_image'),
    path('woo-commerce/batch_update/orders/', views.batch_update_orders, name='batch_update_orders'),
    path('woo-commerce/batch_update/items/', views.batch_update_items, name='batch_update_items'),
    path('woo-commerce/gateways/', views.view_gateway, name='get_gate_way'),
    path('woo-commerce/coupons/', views.view_coupon, name='get_coupons'),
    path('woo-commerce/template_export/', views.read_or_create_templates, name='read_or_create_templates'),
    path('woo-commerce/template_export/<str:template_id>/', views.rud_a_template, name='rud_a_template'),
    path('woo-commerce/email_template/', views.read_email_template, name='read_email_template'),
    path('woo-commerce/email_template/<str:template_id>/', views.rud_an_email_template, name='rud_an_email_template'),
    path('woo-commerce/automail/', views.read_or_create_automail, name='read_or_create_automail'),
    path('woo-commerce/automail/<str:automail_id>/', views.rud_an_automail, name='rud_an_automail'),
    path('woo-commerce/send_mail/', views.send_mail, name='send_mail'),
    path('woo-commerce/notifications/', views.read_notifications, name='read_notifications'),
    path('woo-commerce/action_logs/', views.read_action_logs, name='read_action_logs'),
    path('woo-commerce/tickets/', views.read_or_create_ticket, name='read_or_create_ticket'),
    path('woo-commerce/tickets/<str:ticket_id>', views.rud_a_ticket, name='rud_a_ticket'),
    path('woo-commerce/login/', views.login_view, name='login_view'),
    path('woo-commerce/docs/api-auth/', include('rest_framework.urls', namespace='rest_framework')),
]+ static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)