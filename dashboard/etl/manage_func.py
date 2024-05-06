import os
import django
# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecom_operation.settings')
django.setup()
from dashboard.models import  Order, Order_Line_Item, Site, Notification, Email_Sent, Variation, Key_API
from urllib.parse import urlparse
from woocommerce import API
import json
from datetime import date,datetime,timedelta
from status_map import sys_to_woo
from urllib.parse import urlparse
from send_mail import get_courier_dict, render_template_email, send_html_email, render_template_with_tracking
import pandas as pd

def init_connection(url, key, secret):
    parsed_url = urlparse(url)
    domain = parsed_url.netloc

    wcapi = API(
        url=url,
        consumer_key=key,
        consumer_secret=secret,
        wp_api=True,
        version='wc/v3',
        timeout=60,
        query_string_auth=True,
        user_agent = domain
    )
    
    file_path = '/home/mkt-en/ecom_operation/dashboard/etl/site_error/error_count.txt'
    if os.path.exists(file_path):
        with open(file_path, 'r') as file_check:
            error_data = json.load(file_check)
            if url not in error_data:
                error_data[url] = 0
    else:
        error_data = {url : 0}
    
    try:
        response = wcapi.get("orders")
        if response.status_code == 200:
            error_data[url] = 0
            with open(file_path, 'w') as file_check:
                json.dump(error_data, file_check, indent=2)
            print(f'Init connection to {url} successful')
            return wcapi
        else:
            print(f'Failed to init connection of {url}  with code: {response.status_code}')
            error_data[url] = error_data[url] + 1
            
    except Exception as e:
        error_data[url] = error_data[url] + 1
    
    if error_data[url] == 5:
        Site.objects.filter(link=url).update(status='Disabled')
        error_data[url] = 0
    
    with open(file_path, 'w') as file_check:
        json.dump(error_data, file_check, indent=2)
 
def create_product(wcapi):
    data = {
        'name': 'Premium Quality'
    }
    new_product = wcapi.post('products', data).json()
    print(new_product)

def create_variation(wcapi):
    data = {
        'name': 'Premium Quality'
    }
    new_product = wcapi.post('products', data).json()
    print(new_product)
    
def check_webhook(wcapi):
    print(f'Check status webhook with id ...')
    params = {
        'per_page': 100
    }
    abi_webhook_ids = []
    end_point = f'webhooks'
    webhook_data = wcapi.get(end_point, params=params).json()
    for webhook in webhook_data:
        if webhook['delivery_url'] == 'https://data.abigames.com/woo-commerce' and webhook['status'] != 'active':
            abi_webhook_ids.append(webhook['id'])

    for webhook_id in abi_webhook_ids:
        data = {
            'status': 'active'
        }
        end_point = f'webhooks/{webhook_id}'
        data = wcapi.put(end_point, data).json()
        
        print(f'Complete change webhook status of webhook')

def sync_to_woo(order_obj, method_update):
    dict_site_id = {site.site_id: site for site in Site.objects.all()}
    data_ori = {}
    for order in order_obj:
        if order.order_id.startswith('RS-'):
            continue 
        order_site_id = order.order_id.split('-')[-1]
        site_id = order.site_id.site_id
        
        if site_id not in data_ori:
            data_ori[site_id] = []
        
        if method_update == 'update':
            status  = order.status
            if status == 0:
                continue
            woo_status = sys_to_woo[status]
            if status == 7 and order.payment_status == 2:
                woo_status = 'refunded'
            temp = {
                "id" : order_site_id,
                "status" : woo_status
            }
        else:
            temp = order_site_id
                
        data_ori[site_id].append(temp)
        
    for site_id in data_ori:
        site = dict_site_id.get(site_id)
        wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
        if wcapi:
            for i in range(0,len(data_ori[site_id]),100):
                batch = data_ori[site_id][i:i+100]
                data ={
                    method_update: batch
                }
                wcapi.post('orders/batch', data).json()
    return 1

def update_item_status(item_instances):
    def determine_item_status(item):
        if item.order_id.status in [0,8,9]:
            return 0
        if item.order_id.status == 1:
            return 1
        elif item.order_id.status == 2:
            return item.status
        elif item.order_id.status == 3:
            return 2
        elif item.order_id.status == 4:
            return 3
        elif item.order_id.status == 5:
            return 3
        elif item.order_id.status == 6:
            return 4
        elif item.order_id.status == 7:
            return 5
    updates = []
    for item in item_instances:
        updates.append(Order_Line_Item(line_item_id=item.line_item_id, status = determine_item_status(item)))
        
    Order_Line_Item.objects.bulk_update(updates, fields=['status'],batch_size=500)

def update_order_status(orders):
    updates = []
    if not hasattr(orders, 'filter'):
        orders = [orders]
        
    for order in orders:
        number_items = order.number_items
        if order.number_items_shipping >= 1:
            if order.status != 5:
                order_status = 4
            else:
                order_status = 5
        elif order.number_items_completed == number_items:
            order_status = 6
        elif order.number_items_cancelled == number_items:
            order_status = 7
        elif order.number_items_fulfilled == number_items:
            order_status = 3
        elif order.number_items_fulfilled < number_items and order.number_items_fulfilled > 0:
            order_status = 2
        elif order.number_items_approved == number_items:
            order_status = 1
        else:
            order_status = order.status
        
        updates.append(
            Order(
                order_id=order.order_id,
                status=order_status
            )
        )
    Order.objects.bulk_update(updates, fields=['status'], batch_size=500)

def update_notification(type_noti, list_object_id):
    if len(list_object_id)>0:
        new_list_object_id = []
        noti_map = {
            "Disputes Need Response": {
                'object_type': 'Order',
                'details': f"Order have disputes need to response: ",
                'file_path': '/home/mkt-en/ecom_operation/dashboard/etl/checkpoint/need_response_noti.txt',
                'date_range': 31,
            },
            "Duplicate Order Infomation": {
                'object_type': 'Order',
                'details': f"Order have duplicate phone and email infomation in last 7 days: ",
                'file_path': '/home/mkt-en/ecom_operation/dashboard/etl/checkpoint/duplicate_order_noti.txt',
                'date_range': 31,
            }
        }
        file_path = noti_map[type_noti]['file_path']
        
        today =  date.today()
        if os.path.exists(file_path):
            with open(file_path, 'r') as file_check:
                current_noti = json.load(file_check)
                last_date_send = datetime.strptime(current_noti['date'], "%Y-%m-%d").date()
                if  last_date_send >= today - timedelta(days=noti_map[type_noti]['date_range']):
                    if not set(list_object_id).issubset(set(current_noti['object_id'])):
                        new_list_object_id = [object_id for object_id in list_object_id if object_id not in current_noti['object_id']]
                        current_noti['object_id'].extend(new_list_object_id)
                else: 
                    new_list_object_id = list_object_id
                    current_noti['date'] = str(today)
                    current_noti['object_id'] = new_list_object_id
        else:
            new_list_object_id = list_object_id
            current_noti = {
                'date': str(today),
                'object_id': new_list_object_id
            }
        
        if len(new_list_object_id) > 0:
            Notification.objects.create(
                    type_noti=type_noti,
                    object_type=noti_map[type_noti]['object_type'],
                    object_id=new_list_object_id,
                    details=noti_map[type_noti]['details']+ ','.join(new_list_object_id),
            )
            with open(file_path, 'w') as file_check:
                json.dump(current_noti, file_check, indent=2) 

def send_email(order, email_template, from_email, to_email, line_item_id=None):
    variation_df = pd.DataFrame.from_records(Variation.objects.all().values('site_id','sku','meta_data'))
    TRACKING_KEY = Key_API.objects.get(name='TrackingMore').authentication['key']
    courier_dict = get_courier_dict(TRACKING_KEY)
    html_email = render_template_email(email_template, courier_dict, order, variation_df, line_item_id=line_item_id)
    api_key = Key_API.objects.get(name='SendGrid').authentication['key']
    message_id = send_html_email(api_key,email_template.subject,from_email, to_email, html_email)
    Email_Sent.objects.create(
        message_id = message_id,
        order_id = order,
        email_template= email_template,
        line_item = list(order.line_items.all().values_list('line_item_id', flat=True)) if line_item_id is None else line_item_id
    )

def send_automail(order,automail_template,from_email,to_email,html_email):
    api_key = Key_API.objects.get(name='SendGrid').authentication['key']
    message_id = send_html_email(api_key,automail_template.subject,from_email, to_email, html_email)
    Email_Sent.objects.create(
        message_id = message_id,
        order_id = order,
        automail= automail_template
    )
    
def send_mail_sub_tracking(order, email_template, from_email, to_email,  tracking):
    html_email = render_template_with_tracking( order, tracking, email_template)
    if html_email:
        message_id = send_html_email(email_template.subject,from_email, to_email, html_email)
        Email_Sent.objects.create(
            message_id = message_id,
            order_id = order,
            email_emplate= email_template,
        )
            