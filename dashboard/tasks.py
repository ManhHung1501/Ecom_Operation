import sys
sys.path.insert(0, '/home/mkt-en/ecom_operation/dashboard/etl')
from celery import Celery
from django.conf import settings
from .models import Order, Order_Line_Item, Site, Variation, SKU, Shipping, Product_Site
from urllib.parse import urlparse
from woocommerce import API
import requests
from collections import Counter
from django.core.exceptions import ObjectDoesNotExist
from datetime import datetime
from itertools import product
import pandas as pd
import numpy as np 
import emoji
import re
import time

app = Celery('dashboard')

def check_connection(url, key, secret):
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
        response = wcapi.get("orders")
        if response.status_code == 200:
            return wcapi
        else:
            return None

def remove_emoji(string):
    return emoji.replace_emoji(string, replace='')

def replace_empty_strings_with_none(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                # Recursively call the function for nested dictionaries or lists
                data[key] = replace_empty_strings_with_none(value)
            elif value == "":
                # Replace empty strings with None
                data[key] = None
    
    return data

# PRODUCT AND SKU
def get_all_product(wcapi):
    now = datetime.now()
    print(f'Starting to get Products from Woo ...')
    for attempt in range(1, 6):
        result_data = []
        page = 1
        filters = {'per_page': 100}

        try:
            while True:
                filters['page'] = page
                response = wcapi.get('products', params=filters)

                if response.status_code == 200:
                    headers = response.headers
                    data = response.json()

                    for order in data:
                        order = replace_empty_strings_with_none(order)
                        result_data.append(order)

                    page += 1

                    if page > int(headers['x-wp-totalpages']):
                        break
                else:
                    print(f'Get Products Failed with Error {response.status_code}: {response.text}')
                    return []

            print(f'Get {len(result_data)} Products from Woo Success in: {datetime.now() - now}')
            return result_data

        except requests.Timeout:
            print(f'Timeout error on attempt {attempt}')
        except requests.RequestException as e:
            print(f'Request error on attempt {attempt}: {e}')
            
    print(f'Reached maximum retry attempts. Returning {len(result_data)} Products.')
    return result_data

def get_product(wcapi, lst_ids):
    print(f'Starting to get Products from Woo ...')
    
    result_data = []
    if len(lst_ids) > 0:
        ids = ','.join(lst_ids)
         
        page = 1
        filters = {
            'per_page': 100,
            'include' : ids
        }
        
        while True:
            filters['page'] = page
            response = wcapi.get('products', params=filters)
            if response.status_code == 200:
                headers = response.headers
                data = response.json()
                for product in data:
                    product = replace_empty_strings_with_none(product)
                    result_data.append(product)
            
                page+=1
                if page > int(headers['x-wp-totalpages']):
                    break
            else:
                print(f'Get Products Failed with Error {response.status_code}: {response.text}')
          
                
    print(f'Get {len(result_data)} Products from Woo Success')  
       
    return result_data

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

def get_variation(wcapi,site, pr_data):
    def create_temp_sku(row):
        return 'tempsku_'+str(row['site_id_id']) +'_'+ str(row['product_site_id']) +'_'+ str(row['attributes_id'])

    print(f'Starting to get Variations from Woo ...')
    
    pr_sku_lst = []
    for pr in pr_data:
        temp_dict = {
            'product_site_id' : str(pr['id']),
            'product_name' : pr['name'],
        }

        meta_lst = []
        if len(pr['attributes']) == 1:
            temp_dict['meta_data'] = [
                [pr['attributes'][0]['name'] +'(:)'+ option]
                for option in pr['attributes'][0]['options']
            ]
            
        elif len(pr['attributes']) > 1:
            for atb in pr['attributes']:
                meta_lst.append([atb['name']+'(:)'+option for option in atb['options']])
                
            sku_lst = meta_lst[0]    
            for idx in range(1,len(meta_lst)):
                result_lst = list(product(sku_lst,meta_lst[idx]))
                sku_lst = ['|'.join(item) for item in result_lst]    
                
            # Create string attributes
            sku_lst = [item.split('|') for item in sku_lst]
            # sku_lst = [[sub_item.lower() for sub_item in item] for item in sku_lst]
            temp_dict['meta_data'] = sku_lst
            
            
        else:  
            temp_dict['meta_data'] = None
       
        pr_sku_lst.append(temp_dict)

    df = pd.DataFrame(pr_sku_lst)
    df['date_created'] = datetime.now()
    df['date_modified'] = datetime.now()

    df = df.explode('meta_data')
    df['attributes'] = df['meta_data'].apply(lambda x: [item.split('(:)')[1].lower() for item in x] if x != None else x)
    df['meta_data'] = df['meta_data'].apply(lambda x:[{'key': item.split('(:)')[0], 'value': item.split('(:)')[1]} for item in x] if x != None else x)
    df['attributes_id'] = df['attributes'].apply(lambda x: ' | '.join(sorted(x)) if x != None else 'NA')
    # df['meta_data'] = df['meta_data'].apply(lambda x: create_meta_data(x))
    df['site_id_id'] = site.site_id
    
    df = df.replace({np.nan: None})
    
    product_site_df = pd.DataFrame(Product_Site.objects.filter(site_id=site.site_id).values())
    df = df.merge(product_site_df[['product_site_id','site_id_id','product_id']], on = ['product_site_id','site_id_id'], how = 'left')
    df['sku'] = df.apply(create_temp_sku, axis = 1)
    
    return df

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


# Order
def get_all_order(wcapi):
    now = datetime.now()
    print(f'Starting to get Orders from Woo ...')
  
    for attempt in range(1, 6):
        result_data = []
        page = 1
        filters = {'per_page': 100}

        try:
            while True:
                filters['page'] = page
                response = wcapi.get('orders', params=filters)

                if response.status_code == 200:
                    headers = response.headers
                    data = response.json()

                    for order in data:
                        order = replace_empty_strings_with_none(order)
                        result_data.append(order)

                    page += 1

                    if page > int(headers['x-wp-totalpages']):
                        break
                else:
                    print(f'Get Orders Failed with Error {response.status_code}: {response.text}')
                    return []

            print(f'Get {len(result_data)} Orders from Woo Success in: {datetime.now() - now}')
            return result_data
        
        except requests.Timeout:
            print(f'Timeout error on attempt {attempt}')
        except requests.RequestException as e:
            print(f'Request error on attempt {attempt}: {e}')

    print(f'Reached maximum retry attempts. Returning {len(result_data)} orders.')
    return result_data

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
        for row in batch_data:
            if row['status'] == 'trash' or row['status'] == 'failed':
                continue
            
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
            it_status = 'checking'
            if row['status'] == 'pending':
                ff_status = 'need_approved'
                it_status = 'checking'
            elif row['status'] == 'processing':  
                try:
                    order = Order.objects.get(order_id=site.site_id + '-' + str(row['id']))
                    ff_status = reversed_status_mapping.get(order.status) 
                except ObjectDoesNotExist:
                    ff_status = 'need_approved'
                    it_status = 'checking'
            elif row['status'] in ['shipped','completed']:
                shippings = Shipping.objects.filter(order_number = row['number'],valid=1)
                for tracking in shippings:
                    if tracking.delivery_status != 7:
                        ff_status = 'shipping'
                        it_status = 'shipping'
                        break
                else:
                    ff_status = 'completed'
                    it_status = 'completed'
            elif row['status'] == 'refunded':
                ff_status == 'cancelled'
                it_status == 'cancelled'
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
                order_id = site.site_id + '-' + str(row['id']),
                site_id = site,
                order_number = row['number'],
                transaction_id = row['transaction_id'],
                status = status_mapping.get(ff_status),
                payment_status = payment_status,
                number_items = len(row['line_items']),
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
                        'shipping_country_code', 'discount_amount', 'refund_amount', 'shipping_amount', 
                        'total_amount', 'date_paid', 'date_modified','date_completed', 'coupon_code', 'status']
            )   
        
        # Load items
        Order_Line_Item.objects.bulk_create(
            item_insert, 
            update_conflicts = True, 
            update_fields= ['item_name','quantity', 'subtotal_amount', 'total_amount', 'date_modified', 'price','meta_data_id', 'image_url']
            )  
        # update_item_status(item_instances)
        
    
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


@app.task
def first_site_process(site_id):
    site = Site.objects.get(site_id=site_id)
    wcapi = check_connection(site.link, site.authentication['key'], site.authentication['secret'])
    if wcapi:  
        # Get all product and variation                                
        product_site_data = get_all_product(wcapi)
        load_product_site(product_site_data, site)
        df = get_variation(wcapi,site,product_site_data)
        load_sku_df(df)
        load_variation_df(df, site)
        
        orders = get_all_order(wcapi)
        load_order(orders, site, wcapi)   
            