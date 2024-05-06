import sys
sys.path.insert(0, '/home/mkt-en/ecom_operation')
import os
import django
# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecom_operation.settings')
django.setup()
from dashboard.models import Order,Key_API, Site, Email_Template, Shipping_Detail
from get_data import get_variation, get_all_order, get_last_modified_order, get_all_tracking_lists, get_shipping_data,get_all_product, get_transaction_dispute, get_updated_shipping_data, get_modified_order
from load import load_order, load_product_site, load_shipping,load_variation_df,load_sku_df
from manage_func import check_webhook, init_connection, update_notification, send_email, send_mail_sub_tracking
from datetime import datetime, timedelta,date, timezone
import requests
from requests.auth import HTTPBasicAuth
import concurrent.futures
from django.db.models import Count
from django.utils import timezone
import stripe
import time


dict_site_id = {site.site_id: site for site in Site.objects.filter(status='Active')}

def etl_all_order(site):                                           
    # Get Order
    wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
    if wcapi:
        orders = get_all_order(wcapi)
        load_order(orders, site, wcapi)
                
def etl_all_order_concurrently():
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Submit the etl_order_for_site function for each site concurrently
        futures = [executor.submit(etl_all_order, site) for site_id, site in dict_site_id.items()]

        # Wait for all futures to complete
        concurrent.futures.wait(futures)     

def etl_all_order_separately():                                           
    for site_id, site in dict_site_id.items():
        wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
        if wcapi:
            orders = get_all_order(wcapi)
            load_order(orders, site, wcapi)
             
def activate_webhook():
    for site_id, site in dict_site_id.items():
        wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
        if wcapi:
            check_webhook(wcapi)

def etl_order(site):                                           
    # Get Order
    wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
    if wcapi:
        orders = get_last_modified_order(site.link, site.authentication['key'], site.authentication['secret'], 0, 3, wcapi)
        load_order(orders, site, wcapi)      
           
def etl_order_concurrently():
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Submit the etl_order_for_site function for each site concurrently
        futures = [executor.submit(etl_order, site) for site_id, site in dict_site_id.items()]

        # Wait for all futures to complete
        concurrent.futures.wait(futures)

def etl_order_separately():                                           
    for site_id, site in dict_site_id.items():
        wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
        if wcapi:
            before = date.today()
            after = date.today() - timedelta(days=3)
            orders = get_modified_order(wcapi, after, before )
            load_order(orders, site, wcapi)

def find_duplicate_orders():
    days_ago = datetime.now() - timedelta(days=7)

    duplicate_email_phone = Order.objects.filter(
        date_created__gte=days_ago, status=0
    ).values('email', 'phone').annotate(count=Count('order_id')).filter(count__gt=1)

    # Get the unique combinations of email and phone
    unique_combinations = [(item['email'], item['phone']) for item in duplicate_email_phone]

   
    order_duplicate = []
    # Query the database to get order numbers for each unique combination
    for email, phone in unique_combinations:
        orders = Order.objects.filter(email=email, phone=phone, date_created__gte=days_ago)
        for order in orders:
            order_duplicate.append(order.order_id)

    update_notification("Duplicate Order Infomation", order_duplicate)
    
    return order_duplicate

def etl_shipping():
    account_tk = Key_API.objects.filter(code='tracking')
    for site_id, site in dict_site_id.items():
        wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
        if wcapi:
            before = date.today() +  timedelta(days=1)
            after = date.today() -  timedelta(days=30)
            tracking_list = get_all_tracking_lists(wcapi, site_id, after, before)
            for ac in account_tk:
                API_KEY = ac.authentication['key']
                data = get_shipping_data(tracking_list, API_KEY)
                load_shipping(data)

def etl_updated_shipping():
    CHECKPOINT_FILE_PATH = "/home/mkt-en/ecom_operation/dashboard/etl/checkpoint/tracking_checkpoint.txt"
    def update_last_processed_timestamp(last_processed_timestamp):
        with open(CHECKPOINT_FILE_PATH, "w") as file:
            file.write(str(last_processed_timestamp))
            
    account_tk = Key_API.objects.filter(code='tracking')
    for ac in account_tk:
        API_KEY = ac.authentication['key']
        ts_now = int(time.time())
        data = get_updated_shipping_data(ts_now, API_KEY)
        load_shipping(data)
    
    update_last_processed_timestamp(ts_now) 

def etl_variation(site_id):
    site = dict_site_id.get(site_id)
    wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])     
    if wcapi:                                  
        product_site_data = get_all_product(wcapi)
        load_product_site(product_site_data, site)
        df = get_variation(wcapi,site_id)
        load_sku_df(df)
        load_variation_df(df, site)

def update_dispute_transaction(): 
    time_checkpoint = datetime.now() - timedelta(days=4)
    dispute_trans_ids= get_transaction_dispute(time_checkpoint)
    Order.objects.filter(transaction_id__in =dispute_trans_ids).update(is_dispute = 1) 

def check_dispute_status():
    unresolved_dispute_order = Order.objects.filter(is_dispute=1).exclude(dispute_resolved=1)
    order_need_response = []
    for order in unresolved_dispute_order:
        resolved = True
        need_response = False
        if order.payment_method == 'paypal_express':
            key_api = Key_API.objects.get(name=order.payment_method_title)
            CLIENT_ID = key_api.authentication['key']
            CLIENT_SECRET = key_api.authentication['secret']
            response = requests.post(
                'https://api-m.paypal.com/v1/oauth2/token',
                auth=HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET),
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data= {'grant_type': 'client_credentials'}
            )

            headers = {
                'Authorization': 'Bearer ' + response.json()['access_token'],
                'Content-Type': 'application/json',
            }

            params = {
                'disputed_transaction_id': order.transaction_id,
                'page_size': 50,
            }
            response = requests.get('https://api-m.paypal.com/v1/customer/disputes', headers=headers, params=params)
            data = response.json()
            dispute_ids = [item['dispute_id'] for item in data['items']]
            while 'links' in data and any(link['rel'] == 'next' for link in data['links']):
                next_link = next(link['href'] for link in data['links'] if link['rel'] == 'next')
                response = requests.get(next_link, headers=headers)
                data = response.json()
                if response.status_code == 200:
                    for item in data['items']:
                        dispute_ids.append(item['dispute_id'])

            for dispute_id in dispute_ids:
                url = f'https://api-m.paypal.com/v1/customer/disputes/{dispute_id}'
                response = requests.get(url, headers=headers)
                data = response.json()
                if data['status'] != 'RESOLVED':
                    resolved = False
                    if data['status'] == 'WAITING_FOR_SELLER_RESPONSE':
                        need_response = True
                    break
            
        elif order.payment_method == 'stripe':
            stripe.api_key = Key_API.objects.get(name=order.payment_method_title).authentication['secret']
            
            dispute_list_params = {'limit': 100}
            if order.transaction_id.startswith('ch_'):
                dispute_list_params['charge'] = order.transaction_id
            elif order.transaction_id.startswith('pi_'):
                dispute_list_params['payment_intent'] = order.transaction_id

            starting_after = None
            while True:
                response = stripe.Dispute.list(starting_after=starting_after, **dispute_list_params)
                for dispute in response['data']:
                    if dispute['status'] not in ['won', 'lost']:
                        resolved = False
                        if dispute['status'] in ['needs_response', 'warning_needs_response']:
                            need_response = True

                starting_after = response['data'][-1]['id'] if response['data'] else None

                if not response['has_more'] or not resolved:
                    break
        
        order.dispute_resolved = 1 if resolved else 0
        order.save()
        
        if need_response == True:
            order_need_response.append(order.order_id)
    
    update_notification("Disputes Need Response", order_need_response)
    
    return order_need_response

def check_processing_and_confirm_order(type_mail):
    current_time = timezone.now()
    twelve_hours_ago = current_time - timedelta(hours=12)
    
    orders = Order.objects.filter(site_id__auto_send_mail = 1, site_id__email__isnull = False, payment_status= 1)
    if type_mail == 'Confirm':
        email_template = Email_Template.objects.get(id=1)
        orders = orders.filter(status__in=[0, 1, 2, 3], date_created__gt=twelve_hours_ago)
        for order in orders:
            hours_from_last_sent = 0
            if order.last_confirm_sent :
                hours_from_last_sent = (timezone.now() - order.last_confirm_sent.date_sent ).total_seconds() / 3600 
            if order.last_confirm_sent == None or hours_from_last_sent>= 3:
                send_email(order, email_template, order.site_id.email, order.email)
            
                
    elif type_mail == 'Processing':
        email_template = Email_Template.objects.get(id=2)
        orders = orders.filter(status__in=[1, 2, 3], date_created__lte=twelve_hours_ago)
        for order in orders:
            send_email(order, email_template, order.site_id.email, order.email)             

def check_po2day_and_shippingusps(type_mail):
    # Find to postoffice tracking number
    now = datetime.now(timezone.utc)
    order_nums = []
    if type_mail =='Po2Day':
        po2day_tkn = []
        tracking_details = Shipping_Detail.objects.filter(tracking_detail__icontains='Shipment information received Last mile tracking number').exclude(tracking_number__delivery_status=7)
        for detail in tracking_details:
            if detail.checkpoint_date.replace(tzinfo=timezone.utc) <= now - timedelta(days=2):
                po2day_tkn.append(detail.tracking_number)
                order_number = detail.tracking_number.order_number
                if order_number not in order_nums:
                    order_nums.append(order_number)
        orders = Order.objects.filter(order_number__in=order_nums, site_id__auto_send_mail=1, site_id__email__isnull=False)
        email_template = Email_Template.objects.get(id=7)
        for order in orders:
            if order.last_po2days_sent == None:
                for tracking in po2day_tkn:
                    if tracking.order_number == order.order_number:
                        tkn = tracking
                        break
                send_mail_sub_tracking(order, email_template, order.email, order.site_id.email,  tkn)
    elif type_mail =='ShippingUSPS':
        tracking_details = Shipping_Detail.objects.filter(tracking_detail__icontains='Shipment information received Last mile tracking number').exclude(tracking_number__delivery_status=7)
        for detail in tracking_details:
            if detail.tracking_number.created_at.replace(tzinfo=timezone.utc) <= now - timedelta(days=2):
                order_number = detail.tracking_number.order_number
                if order_number not in order_nums:
                    order_nums.append(order_number)
        orders = Order.objects.filter(order_number__in=order_nums, site_id__auto_send_mail=1, site_id__email__isnull=False)
        email_template = Email_Template.objects.get(id=8)
        for order in orders:
            if order.last_shipping_usps_sent == None:
                send_email(order, email_template, order.email, order.site_id.email)