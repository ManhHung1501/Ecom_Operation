import sys
sys.path.insert(0, '/home/mkt-en/ecom_operation')
import os
import django
# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecom_operation.settings')
django.setup()
from django.db import connection
from dashboard.models import  Order, Order_Line_Item, Variation, SKU, Shipping, Shipping_Detail, Product_Site,Email_Sent, Email_Template, Site, Batch, Auto_Email_Template
from django.db.models import Min, Q
from django.db.models import Subquery, OuterRef, Case, When, Value, IntegerField, Count, F
from django.db import transaction
from get_data import get_gateways
from run import etl_updated_shipping
from datetime import datetime
from itertools import product
import pandas as pd
import numpy as np
from get_data import get_variation, get_all_order, get_last_modified_order, get_product, get_all_tracking_lists, get_shipping_data, get_all_product, get_coupons
from load import load_variation, load_order, load_product_site, load_shipping
import requests
# from status_map import status_mapping, payment_status, item_status, item_tag, tracking_status_mapping,sys_to_woo
from urllib.parse import urlparse
from woocommerce import API
from django.forms.models import model_to_dict
import json
import requests 
import re
from manage_func import send_automail


# data = []
# str_find_tracking = "Shipment information received Last mile tracking number:"
# str_find_carrier = " - Last mile tracking carrier:"
# matching_shipping_details = Shipping_Detail.objects.filter(tracking_detail__icontains="Shipment information received Last mile tracking number:")
# for shipping_detail in matching_shipping_details:
#     tracking_detail = shipping_detail.tracking_detail
#     tracking_number_start = tracking_detail.find("Shipment information received Last mile tracking number:") + len("Shipment information received Last mile tracking number:")
#     tracking_number_end = tracking_detail.find(" - Last mile tracking carrier:")
#     extracted_tracking_number = tracking_detail[tracking_number_start:tracking_number_end].strip()

#     # Extracting carrier
#     carrier_start = tracking_detail.find(" - Last mile tracking carrier:", tracking_number_end) + len(" - Last mile tracking carrier:")
#     extracted_carrier = remove_chinese_characters(tracking_detail[carrier_start:]).strip()
    
#     data.append(
#         {'tracking_number': shipping_detail.tracking_number,
#         'last_tn': extracted_tracking_number,
#         'carrier': extracted_carrier}
#     )
# df = pd.DataFrame(data)
# df.to_csv('/home/mkt-en/ecom_operation/dashboard/etl/last_tracking.csv', index=False)
# variation_df = pd.DataFrame.from_records(Variation.objects.all().values('site_id','sku','meta_data'))
# order = Order.objects.get(order_id='MALIVY-2629')
# courier_dict = get_courier_dict()
# email_template = Email_Template.objects.get(name="Shipping Email")
# html_email = render_template_email(email_template, courier_dict, order, variation_df, tracking=None)
# message_id = send_html_email(email_template.subject,"support@katycharm.com", "hungnm@abigames.com.vn", html_email)
# print(message_id)
# Email_Sent.objects.create(
#     message_id = message_id,
#     order_id = order,
#     email_emplate= email_template
# )

# order = Order.objects.get(order_id='DAYL-8910')
# email_template = Email_Template.objects.get(id=5)
# tracking = Shipping.objects.get(tracking_number='YT2330321272307195')
# send_mail_sub_tracking(order, email_template, 'support@katycharm.com', 'hungnm.airflow@gmail.com',  tracking)
# queryset = Shipping.objects.get(tracking_number='LR042048980CN').shipping_details.all().count()

from django.utils import timezone
from datetime import timedelta

def auto_send_mail():
    for row in Auto_Email_Template.objects.all():
        condition = row.condition
        queryset = Order.objects.all()
        if 'order_number' in condition:
            order_number = condition['order_number'].split(',')
            queryset = queryset.filter(order_number__in=order_number)
        if 'sku'in condition:
            sku = condition['sku'].split(',')
            queryset = queryset.filter(line_items__sku__sku__in=sku)
        if 'status' in condition:
            sku = condition['status'].split(',')
            queryset = queryset.filter(status__in=sku)
        if 'tkn_status' in condition:
            tkn_status = condition['tkn_status'].split(',')
            queryset = queryset.filter(line_items__shippings__delivery_status__in=tkn_status)
        if 'date_paid_to_now' in condition:
            value = timezone.now() - timedelta(days=condition['date_paid_to_now']['value'])
            if condition['date_paid_to_now']['comparison'] == 'gte':
                queryset = queryset.filter(date_paid__lte=value)
            else:
                queryset = queryset.filter(date_paid__gte=value)
        if 'tkn_created_to_now' in condition:
            value = timezone.now() - timedelta(days=condition['tkn_created_to_now']['value'])
            if condition['tkn_created_to_now']['comparison'] == 'gte':
                queryset = queryset.filter(line_items__shippings__created_at__lte=value)
            else:
                queryset = queryset.filter(line_items__shippings__created_at__gte=value)
        if 'tkn_updated_to_now' in condition:
            value = timezone.now() - timedelta(days=condition['tkn_updated_to_now']['value'])
            if condition['tkn_updated_to_now']['comparison'] == 'gte':
                queryset = queryset.filter(line_items__shippings__update_date__lte=value)
            else:
                queryset = queryset.filter(line_items__shippings__update_date__gte=value)
        if 'tkn_active_to_now' in condition:
            value = timezone.now() - timedelta(days=condition['tkn_active_to_now']['value'])
            value = timezone.now() - timedelta(days=condition['tkn_active_to_now']['value'])
            queryset = queryset.filter(
                Q(line_items__shippings__shipping_details__detail_index=2) &
                Q(line_items__shippings__shipping_details__checkpoint_date__lte=value) if condition['tkn_active_to_now']['comparison'] == 'gte' else
                Q(line_items__shippings__shipping_details__detail_index=2) &
                Q(line_items__shippings__shipping_details__checkpoint_date__gte=value)
            ).annotate(num_shipping_details=Count('line_items__shippings__shipping_details')).filter(num_shipping_details__gt=1)
        
        queryset = queryset.exclude(sent_emails__automail=row.name, site_id__auto_send_mail = 0, site_id__email__isnull = True)
        queryset = queryset.distinct()
        
        for order in queryset:
            if not Email_Sent.objects.filter(order_id=order.order_id, automail=row.name).exists():
                html_email = row.content.replace('[$a]', order.phone)
                send_automail(order,row,order.site_id.email,order.email,html_email)