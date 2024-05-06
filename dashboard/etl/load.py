import sys
import textwrap
sys.path.insert(0, '/home/mkt-en/ecom_operation')
import os
import django
# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecom_operation.settings')
django.setup()
from django.db import connection
from django.core.exceptions import ObjectDoesNotExist
from dashboard.models import  Order, Order_Line_Item, Site, Variation, SKU, Shipping, Shipping_Detail, Product_Site, Key_API, Email_Template, Email_Sent
from collections import Counter
import pandas as pd
from manage_func import sync_to_woo, send_email,update_order_status, send_mail_sub_tracking
from datetime import datetime
import warnings
from get_data import get_product
import emoji
import re
from status_map import status_mapping, tracking_status_mapping, item_status
warnings.filterwarnings('ignore', category=RuntimeWarning)

def remove_emoji(string):
    return emoji.replace_emoji(string, replace='')
   
def load_variation(variation_data, site):
    now = datetime.now()
    print(f'Starting to Load Variations of {site.site_id} ...')
    
    # Load data
    batch_size = 5000
    for i in range(0, len(variation_data), batch_size):
        batch_data = variation_data[i:i + batch_size]
        Variation.objects.bulk_create(
            [
            Variation(
                product_site_id = item['product_site_id'],
                product_site_name = item['product_site_name'],
                site_id = site,
                attributes_id = remove_emoji(item['attributes_id']) if item['attributes_id'] != None else 'NA',
                attributes = item['attributes'],
                meta_data = item['meta_data'],
                sku = item['sku'],
                date_modified = datetime.now()
            ) 
            for item in batch_data
            ],
            update_conflicts = True,
            update_fields= ['date_modified', 'product_site_name' ,'meta_data']
        )

    print(f'Complete Load Variations of {site.site_id} with {len(variation_data)} rows in: {datetime.now() - now}')

def load_variation_df(variation_df,site):
    now = datetime.now()
    print(f'Starting to Load Variations of {site.site_id} ...')
    dict_sku = {item.sku: item for item in SKU.objects.all()}
    # Load data
    batch_size = 5000
    for i in range(0, len(variation_df), batch_size):
        batch_data = variation_df[i:i + batch_size]
        Variation.objects.bulk_create(
            [
            Variation(
                product_site_id = item['product_site_id'],
                product_site_name = remove_emoji(item['product_name']),
                site_id = site,
                attributes_id = remove_emoji(item['attributes_id']) if item['attributes_id'] != None else 'NA',
                attributes = item['attributes'],
                meta_data = item['meta_data'],
                sku = dict_sku.get(item['sku']),
                date_modified = datetime.now()
            ) 
            for index, item in batch_data.iterrows()
            ],
            update_conflicts = True,
            update_fields= ['date_modified', 'product_site_name', 'meta_data']
        )

    print(f'Complete Load Variations of {site.site_id} with {len(variation_df)} rows in: {datetime.now() - now}')

def load_sku_df(sku_data):
    now = datetime.now()
    print(f'Starting to Load SKU ...')
    
    # Load data
    batch_size = 5000
    for i in range(0, len(sku_data), batch_size):
        batch_data = sku_data[i:i + batch_size]
        SKU.objects.bulk_create(
            [
            SKU(
                sku = item['sku'],
                product_id = item['product_id'],
                attributes_id = remove_emoji(item['attributes_id']) if item['attributes_id'] != None else 'NA',
                attributes = item['attributes']
            ) 
            for idx, item in batch_data.iterrows()
            ],
            update_conflicts = True,
            update_fields= ['attributes']
        )

    print(f'Complete Load SKU with {len(sku_data)} rows in: {datetime.now() - now}')

def load_product_site(product_site_data, site):
    now = datetime.now()
    print(f'Starting to Load Products Site ...')
    
    # Load data
    batch_size = 5000
    for i in range(0, len(product_site_data), batch_size):
        batch_data = product_site_data[i:i + batch_size]
        Product_Site.objects.bulk_create(
            [
            Product_Site(
                site_id = site,
                product_site_id = str(item['id']),
                product_site_name = remove_emoji(item['name']) if item['name'] != None else None,
                product_id = f'temp_{site.site_id}_' + str(item['id']),
                link = item.get('permalink'),
                price = item.get('price') if item.get('price') != None else 0,
                date_created = item.get('date_created_gmt'),
                date_modified = item.get('date_modified_gmt')
            ) 
            for item in batch_data
            ],
            update_conflicts = True,
            update_fields= ['product_site_name','date_modified','price']
        )

    print(f'Complete Load Products Site of Site {site.site_id} with {len(product_site_data)} rows in: {datetime.now() - now}')

def load_shipping(shipping_data):
    now = datetime.now()
    print(f'Starting to Load Shipping ...')

    to_country_tracking = []
    to_po_tracking = []
    delivery_tracking = []
    active_tracking = []
    # Load data
    for i in range(0, len(shipping_data), 5000):
        shipping_insert = []
        shipping_detail_insert = []
        batch_data = shipping_data[i:i + 5000]
        for item in batch_data:
            tracking_info =[]
           
            for inf in item['origin_info']['trackinfo']:
                inf['origin_destination'] = 0
                tracking_info.append(inf)
        
            orgin_info = item['origin_info'].copy()
            orgin_info.pop('trackinfo')
            
            des_info = None
            if len(item['destination_info']['trackinfo']) > 0:
                des_info = item['destination_info'].copy()
                for inf in item['destination_info']['trackinfo']:
                    inf['origin_destination'] = 1
                    tracking_info.append(inf)
                des_info.pop('trackinfo')   
                
           
            item['updating'] = 1 if item['updating'] else 0
            item['archived'] = 1 if item['archived'] else 0
            
            if len(tracking_info) > 1 and item['delivery_status'] != 'delivered': 
                active_tracking.append(item['tracking_number'])
            if item['delivery_status'] == 'delivered': 
                delivery_tracking.append(item['tracking_number'])
            
            shipping_instance = Shipping(
                    tracking_number = item['tracking_number'],
                    order_number = item['order_number'],
                    courier_code = item['courier_code'],
                    created_at = item['created_at'],
                    update_date = item['update_date'],
                    shipping_date = item['shipping_date'],
                    archived = item['archived'],
                    delivery_status = tracking_status_mapping.get(item['delivery_status'], 0),
                    updating = item['updating'] ,
                    destination = item['destination'],
                    original = item['original'],
                    weight = item['weight'],
                    substatus = item['substatus'],
                    status_info = item['status_info'],
                    previously = item['previously'],
                    destination_track_number = item['destination_track_number'],
                    consignee = item['consignee'],
                    scheduled_delivery_date = item['scheduled_delivery_date'],
                    scheduled_address = item['Scheduled_Address'],
                    lastest_checkpoint_time = item['lastest_checkpoint_time'],
                    exchange_number = item['exchangeNumber'],
                    transit_time = item['transit_time'],
                    stay_time = item['stay_time'],
                    origin_info = orgin_info,
                    destination_info = des_info,
                    valid = item.get('valid', 1),
                ) 
            shipping_insert.append(shipping_instance)
            
            detail_index = len(tracking_info)
            for inf in tracking_info:
                shipping_detail_insert.append(
                    Shipping_Detail(
                        tracking_number = shipping_instance,  
                        checkpoint_date = inf['checkpoint_date'],
                        tracking_detail = inf['tracking_detail'],
                        location = inf['location'],
                        checkpoint_delivery_status = inf['checkpoint_delivery_status'],
                        checkpoint_delivery_substatus = inf['checkpoint_delivery_substatus'],
                        origin_destination = inf['origin_destination'],
                        detail_index = detail_index
                    )
                )
                detail_index -= 1
                if inf['tracking_detail'].strip() == 'International flight has arrived' and item['tracking_number'] not in to_country_tracking:
                    to_country_tracking.append(item['tracking_number'])
                if 'Shipment information received Last mile tracking number' in inf['tracking_detail'] and item['tracking_number'] not in to_po_tracking:
                    to_po_tracking.append(shipping_instance)
        
        shipping_created = Shipping.objects.bulk_create( 
            shipping_insert,  
            update_conflicts = True, 
            update_fields= ['update_date','shipping_date', 'archived', 'delivery_status', 'updating', 
                        'destination', 'original', 'weight', 'substatus', 'status_info','previously',
                        'destination_track_number','exchange_number','scheduled_delivery_date','scheduled_address',
                        'lastest_checkpoint_time','transit_time','stay_time','origin_info','destination_info']
        )
        
        for shipping_instance in shipping_created:
            for data in batch_data:
                if 'line_item_id' in data:
                    if data['order_number'] == shipping_instance.order_number:
                        shipping_instance.line_item_id.add(data['line_item_id'])

        Shipping_Detail.objects.bulk_create( 
            shipping_detail_insert,  
            update_conflicts = True, 
            update_fields= ['checkpoint_date','tracking_detail', 'location', 'checkpoint_delivery_status', 
                        'checkpoint_delivery_substatus', 'origin_destination']
        )
    
    if to_country_tracking:
        to_country_item =  Order_Line_Item.objects.filter(shippings__tracking_number__in=to_country_tracking)
        order_ids = to_country_item.values_list('order_id__order_id', flat=True).distinct()
        
        item_sent_pr = []
        email_sent = Email_Sent.objects.filter(email_template__id=6, order_id__order_id__in = order_ids)
        for email in email_sent:
            item_sent_pr.extend(email.line_item)
        
        send_email_item = to_country_item.exclude(line_item_id__in= item_sent_pr)
        send_email_order = Order.objects.filter(
            order_id__in=send_email_item.values_list('order_id__order_id', flat=True).distinct(),
            site_id__auto_send_mail = 1, 
            site_id__email__isnull = False
        ).distinct()
        
        email_template = Email_Template.objects.get(id=4)
        for order in send_email_order:
            if order.last_to_country_sent == None:
                line_item_id = send_email_item.filter(order_id = order).values_list('line_item_id', flat=True).distinct()
                send_email(order, email_template, order.site_id.email, order.email, line_item_id=list(line_item_id))    

    if to_po_tracking:
        lst_tkn = [tracking.tracking_number for tracking in to_po_tracking]
        send_email_order = Order.objects.filter(
            line_items__shippings__tracking_number__in = lst_tkn,
            site_id__auto_send_mail = 1, 
            site_id__email__isnull = False
            ).distinct()
        email_template = Email_Template.objects.get(id=5)
        for order in send_email_order:
            if order.last_to_po_sent == None:
                for tracking in to_po_tracking:
                    if tracking.order_number == order.order_number:
                        tracking_number = tracking
                        break
                send_mail_sub_tracking(order, email_template, order.site_id.email, order.email, tracking_number)

    if delivery_tracking:
        completed_item = Order_Line_Item.objects.filter(shippings__tracking_number__in=delivery_tracking)
        completed_item.update(status=4)
        order_ids = completed_item.values_list('order_id__order_id', flat=True).distinct()
        completed_order = Order.objects.filter(order_id__in=order_ids)
        update_order_status(completed_order)
        sync_to_woo(completed_order, 'update')
        item_sent_pr = []
        email_sent = Email_Sent.objects.filter(email_template__id=6, order_id__order_id__in = order_ids)
        for email in email_sent:
            item_sent_pr.extend(email.line_item)
        send_email_order = completed_order.filter(site_id__auto_send_mail = 1, site_id__email__isnull = False)
        send_email_item = completed_item.exclude(line_item_id__in= item_sent_pr)
        email_template = Email_Template.objects.get(id=6)
        for order in send_email_order:
            if order.last_delivery_sent == None:
                line_item_id = send_email_item.filter(order_id = order).values_list('line_item_id', flat=True).distinct()
                if line_item_id:
                    send_email(order, email_template, order.site_id.email, order.email, line_item_id=list(line_item_id))
    
    if active_tracking:
        order_ids = Order_Line_Item.objects.filter(shippings__tracking_number__in=delivery_tracking).values_list('order_id__order_id', flat=True).distinct()
        Order.objects.filter(order_id__in=order_ids).update(status=5)
        
    
    print(f'Complete Load Shipping with {len(shipping_data)} rows in: {datetime.now() - now}')

def load_key_gateway(gateway_data):
    gateway_insert = []
    for gateway in gateway_data:
        if gateway['id'] == 'stripe':
            gateway_insert.append(
                Key_API(
                    code = 'stripe',
                    name = gateway['title'],
                    authentication = {'key':gateway['settings']['publishable_key']['value'],'secret':gateway['settings']['secret_key']['value']},
                )
            )
    Key_API.objects.bulk_create(gateway_insert,  update_conflicts = True, update_fields= ['authentication'])
    
def load_order(orders_data, site, wcapi): 
    now = datetime.now()
    print(f'Starting to Load Orders of {site.site_id} ...')
    # Convert to list if input is an order type dict
    orders_data = orders_data if isinstance(orders_data, list) else [orders_data]
    reversed_status_mapping = {v: k for k, v in status_mapping.items()}
    lst_variation = [
        {
            'product_site_id' : var.product_site_id,
            'product_site_name' : var.product_site_name,
            'site_id' : var.site_id,
            'attributes_id' : var.attributes_id,
            'attributes' : var.attributes,
            'sku': var.sku
        } 
        for var in Variation.objects.filter(site_id=site.site_id)
        ]
   
    lst_product_site = [
        {
            'product_site_id' : pro.product_site_id,
            'site_id' : pro.site_id.site_id,
            'product_id': pro.product_id
        } 
        for pro in Product_Site.objects.filter(site_id=site.site_id)
        ]
    
    # Load data
    variation_insert = []
    product_site_ids = [pro['product_site_id'] for pro in lst_product_site]
    batch_size = 5000
    for i in range(0, len(orders_data), batch_size):
        item_insert = []
        order_insert = []
        batch_data = orders_data[i:i + batch_size]
        batch_order_id = [site.site_id + '-' + str(row['id']) for row in batch_data]
        for row in batch_data:
            if row['status'] == 'trash' or row['status'] == 'failed':
                continue
            
            order_id = site.site_id + '-' + str(row['id'])
            
            # Payment status
            if row['date_paid_gmt'] is None:
                if row['payment_method'] == 'paypal_express' and row['status'] == 'on-hold':
                    payment_status = 3
                else:
                    payment_status = 0
            else:
                if row['status'] == 'refunded':
                    payment_status = 2
                elif row['status'] == 'on-hold':
                    payment_status = 3
                else:
                    payment_status = 1
            
            # Fullfil status
         
            if row['status'] == 'pending':
                ff_status = 'need_approved'
                it_status = 'checking'
            elif row['status'] == 'processing':  
                try:
                    order = Order.objects.get(order_id=order_id)
                    ff_status = reversed_status_mapping.get(order.status) 
                    it_status = 'checking'
                except ObjectDoesNotExist:
                    ff_status = 'need_approved'
                    it_status = 'checking'
            elif row['status'] in ['shipped','completed']:
                shippings = Shipping.objects.filter(line_item_id__order_id__order_id = order_id, valid=1)
                ff_status = 'shipping'
                it_status = 'shipping'
                for tracking in shippings:
                    if tracking.delivery_status == 7:
                        ff_status = 'delivered'
                        it_status = 'delivered'
                        break
                    else:
                        if tracking.shipping_details.all().count() > 1:
                            ff_status = 'active'
                            it_status = 'shipping'     
                else:
                    ff_status = 'shipping'
                    it_status = 'shipping'
            elif row['status'] == 'refunded':
                ff_status = 'cancelled'
                it_status = 'cancelled'
            else:
                ff_status = row['status']
                if row['status'] in ['on-hold', 'cs-hold']:
                    it_status = 'checking'
                else:
                    it_status = row['status']
            
            # Refund amount   
            refund_amt = 0    
            for refund_row in row['refunds']:
                refund_amt += float(refund_row['total'])
            order_instance = Order(
                order_id = order_id,
                site_id = site,
                order_number = row['number'],
                transaction_id = row['transaction_id'],
                status = status_mapping.get(ff_status),
                payment_status = payment_status,
                first_name = remove_emoji(row['billing']['first_name']) if row['billing']['first_name'] is not None else None,
                last_name = remove_emoji(row['billing']['last_name']) if row['billing']['last_name'] is not None else None,
                email = row['billing']['email'].strip() if row['billing']['email'] is not None else None,
                phone = re.sub(r'\D', '', row['billing']['phone']) if row['billing']['phone'] is not None else None,
                address_1 = row['billing']['address_1'],
                address_2 = row['billing']['address_2'],
                city = row['billing']['city'],
                state_code = row['billing']['state'],
                postcode = row['billing']['postcode'],
                country_code = row['billing']['country'],
                currency = row['currency'],
                shipping_first_name = remove_emoji(row['shipping']['first_name']) if row['shipping']['first_name'] is not None else None,
                shipping_last_name = remove_emoji(row['shipping']['last_name']) if row['shipping']['last_name'] is not None else None,
                shipping_phone = re.sub(r'\D', '', row['shipping']['phone']) if row['shipping']['phone'] is not None else None,
                shipping_address_1 = row['shipping']['address_1'],
                shipping_address_2 = row['shipping']['address_2'],
                shipping_city = row['shipping']['city'],
                shipping_state_code = row['shipping']['state'],
                shipping_postcode = row['shipping']['postcode'],
                shipping_country_code = row['shipping']['country'],
                payment_method = row['payment_method'],
                payment_method_title = row['payment_method_title'],
                discount_amount = row['discount_total'],
                shipping_amount = row['shipping_total'],
                refund_amount = refund_amt,
                coupon_code = [coupon['code'] for coupon in row['coupon_lines']],
                total_amount = row['total'],
                date_paid = row['date_paid_gmt'],
                date_created =  row['date_created_gmt'],
                date_modified = row['date_modified_gmt'],
                date_completed = row['date_completed_gmt']
            )
            order_insert.append(order_instance)
            
            for item in row['line_items']:
                # Create variation
                meta_data = [{'key': meta['display_key'],'value': meta['display_value']} for meta in item['meta_data'] if 'tracking_number' not in meta['display_value'] and meta['display_value'] != ""]
                item_atb = [meta['display_value'].lower() for meta in item['meta_data'] if 'tracking_number' not in meta['display_value'] and meta['display_value'] != ""]
                variation_temp = {
                        'product_site_id' : str(item['product_id']),
                        'product_site_name' : remove_emoji(item['name']).strip(),
                        'site_id' : site,
                        'attributes_id' : remove_emoji(' | '.join(sorted(item_atb))),
                        'attributes' : item_atb,
                        'meta_data': meta_data if len(meta_data) > 0 else None
                    }
              
                if str(item['product_id']) not in product_site_ids:
                    product_site_ids.append(str(item['product_id']))  
            
                # Map SKU
                sku_var_check = [
                        var for var in lst_variation
                        if var['site_id'].site_id == site.site_id 
                        and var['product_site_id'] == str(item['product_id']) 
                    ]
            
                # Check sku is exist in db
                exist_sku = False
                for variation in sku_var_check:
                    if Counter(item_atb) == Counter(variation['attributes']):
                        sku_instance = variation['sku']
                        exist_sku = True
                        break
            
                # If sku not exist in db
                if exist_sku == False:
                    aid = variation_temp['attributes_id']
                    pid = variation_temp['product_site_id']
                    
                    temp_sku = f'tempsku_{site.site_id}_{pid}_{aid}'
                    
                    product_id = f'temp_{site.site_id}_{pid}'
                    for product_site in lst_product_site:
                        if site.site_id == product_site['site_id'] and variation_temp['product_site_id'] == product_site['product_site_id']:
                            product_id = product_site['product_id']
                            break
                        
                    sku_instance, created = SKU.objects.update_or_create(
                        product_id=product_id,
                        attributes_id=variation_temp['attributes_id'],
                        defaults={
                            'sku': temp_sku,
                            'attributes': variation_temp['attributes'],
                        }
                    )

                    # Update dict sku and list variation 
                    # dict_sku.update({temp_sku: sku_instance})
                    variation_temp['sku'] = sku_instance
                    lst_variation.append(variation_temp)
                    
                    # Append new sku and variation for insert
                    variation_insert.append(variation_temp)    
                
                meta_ids = [meta['id'] for meta in item['meta_data'] if 'tracking_number' not in meta['display_value'] and meta['display_value'] != ""]
                
                item_insert.append(
                    Order_Line_Item(
                        line_item_id = site.site_id +'-'+ str(item['id']), 
                        order_id = order_instance,
                        item_name = remove_emoji(item['name']),
                        quantity = item['quantity'],
                        subtotal_amount = item['subtotal'],
                        total_amount = item['total'],
                        sku = sku_instance,
                        status = item_status.get(it_status),
                        date_modified = row['date_modified_gmt'],
                        date_created = row['date_created_gmt'],
                        meta_data_id = meta_ids if len(meta_ids) > 0 else None,
                        price = item['price'],
                        image_url = item['image']['src'] if item.get('image') != None else None
                    )
                )
                    
        # Load orders
        Order.objects.bulk_create(
            order_insert, 
            update_conflicts = True, 
            update_fields= ['transaction_id','payment_status','first_name', 
                        'last_name', 'email', 'phone', 'address_1', 'address_2', 'city', 'state_code', 
                        'postcode', 'country_code', 'currency', 'payment_method','payment_method_title',
                        'shipping_first_name', 'shipping_last_name', 'shipping_phone', 'shipping_address_1', 
                        'shipping_address_2', 'shipping_city', 'shipping_state_code', 'shipping_postcode', 
                        'shipping_country_code', 'discount_amount', 'shipping_amount', 
                        'total_amount', 'date_paid', 'date_modified','date_completed', 'coupon_code', 'status']
            )   
        
        # Load items
        Order_Line_Item.objects.bulk_create(
            item_insert, 
            update_conflicts = True, 
            update_fields= ['item_name','quantity', 'subtotal_amount', 'total_amount', 'date_modified', 'price','meta_data_id', 'image_url', 'status']
            )  
    
    product_site_data = get_product(wcapi, product_site_ids)   
    exist_product_site_id = [str(p['id']) for p in product_site_data]
    not_exist_product_site_id = [pid for pid in product_site_ids if pid not in exist_product_site_id]
    for pid in not_exist_product_site_id:
        product_site_data.append(
            {
                'site_id' : site.site_id,
                'id': int(pid),
                'name': None
            }
        )
        
    load_product_site(product_site_data, site)
    load_variation(variation_insert, site)    
    
   
   
    print(f'Complete Load Orders of {site.site_id} with {len(orders_data)} rows in: {datetime.now() - now}')


