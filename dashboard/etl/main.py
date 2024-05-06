import sys
sys.path.insert(0, '/home/mkt-en/ecom_operation')
import os
import django
# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecom_operation.settings')
django.setup()
from django.db import connection
from dashboard.models import Order, Order_Line_Item, Shipping, Site, Key_API
from run import etl_order, etl_all_order_concurrently, find_duplicate_orders, etl_all_order_separately,etl_variation,etl_shipping
from get_data import get_variation, get_all_product, get_all_tracking_lists, get_shipping_data,get_coupons, get_updated_shipping_data, get_all_order, get_gateways
from load import load_variation_df, load_product_site, load_sku_df,load_shipping, load_order, load_key_gateway
from datetime import datetime, timedelta
from manage_func import init_connection
import requests
import time
from status_map import status_mapping, payment_status, item_status, item_tag, tracking_status_mapping,sys_to_woo

dict_site_id = {site.site_id: site for site in Site.objects.filter(status='Active')}


def date_range(start_date, end_date, gap_days):
    dates = []
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date)
        current_date += timedelta(days=gap_days)
    return dates
     
# for site_id, site in dict_site_id.items():
#     API_KEY = Key_API.objects.get(name='TrackingMore').authentication['key']
#     wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
#     if wcapi:
#         start_date = datetime(2023, 10, 1)  # Example start date
#         end_date = datetime(2024, 5, 1)   # Example end date
#         gap_days = 15

#         # Generate list of dates
#         date_list = date_range(start_date, end_date, gap_days)
#         for i, date in enumerate(date_list):
#             if i == len(date_list) -1:
#                 break
#             print(date_list[i], date_list[i+1])
#             tracking_list = get_all_tracking_lists(wcapi, site_id, date_list[i].date(), date_list[i+1].date())
#             data = get_shipping_data(tracking_list, API_KEY)
#             load_shipping(data)     
     
# etl_all_order_separately()
for site_id, site in dict_site_id.items():
    wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
    if wcapi:
        # product_site_data = get_all_product(wcapi)
        # load_product_site(product_site_data, site)
        # df = get_variation(wcapi,site_id)
        # load_sku_df(df)
        # load_variation_df(df, site)
        # data = get_gateways(wcapi)
        # load_key_gateway(data)
        start_date = datetime(2023, 10, 1)  # Example start date
        end_date = datetime(2024, 5, 31)   # Example end date
        gap_days = 15

        # Generate list of dates
        date_list = date_range(start_date, end_date, gap_days)
        for i, date in enumerate(date_list):
            if i == len(date_list) -1:
                break
            print(date_list[i], date_list[i+1])
            orders = get_all_order(wcapi, date_list[i].date(), date_list[i+1].date())
            load_order(orders, site, wcapi)  
# etl_updated_shipping()
# etl_shipping()

# print(find_duplicate_orders(7))

# data = get_updated_shipping_data(int(time.time()))
# update_shipping_detail(data)
