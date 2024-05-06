import sys
sys.path.insert(0, '/home/mkt-en/ecom_operation')
import os
import django
# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecom_operation.settings')
django.setup()
from dashboard.models import Shipping, SKU,Key_API, Product_Site
from woocommerce import API
from itertools import product
import pandas as pd
import numpy as np
from datetime import datetime
from urllib.parse import urlparse
import time
from datetime import datetime,timedelta,timezone,date
import json
import requests
from requests.auth import HTTPBasicAuth
import stripe



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

def get_last_modified_order(url, key, secret, hours, days, wcapi):
    print(f'Starting to get last Modified Orders from {url} ...')
    
    # Get last order ids
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    wcapi_v1 = API(
            url=url,
            consumer_key=key,
            consumer_secret=secret,
            version= 'wc/v1',
            timeout=60,
            user_agent = domain
            
        )
    
    filters = {
        'hours': hours,
        'days': days,
        'offset': 0,
        'limit': 1000000
    }
    
    for attempt in range(1, 6):
        try:
            lst_ids = []
            ids_modified = wcapi_v1.get('orders/updated', params=filters).json()
            for row in ids_modified['orders']:
                lst_ids.append(row['id'])
            ids = ','.join(lst_ids)
            
            # GET ORDERS
            result_data = []
            if len(ids) > 0:
                page = 1
                filters = {
                    'per_page': 50,
                    'include': ids
                }
                
                while True:
                    filters['page'] = page
                    response = wcapi.get('orders', params=filters)
                    if response.status_code == 200:
                        headers = response.headers
                        data = response.json()
                        for order in data:
                            order = replace_empty_strings_with_none(order)
                            result_data.append(order)
                    
                        page+=1
                        if page > int(headers['x-wp-totalpages']):
                            break
                    
                    else:
                        print(f'Get Orders Failed with Error {response.status_code}: {response.text}')
                        return []
                    
            print(f'Get {len(lst_ids)} Modified Orders from {domain} Success')    
            return result_data
        except requests.Timeout:
            print(f'Timeout error on attempt {attempt}')
        except requests.RequestException as e:
            print(f'Request error on attempt {attempt}: {e}')

    print(f'Reached maximum retry attempts. Returning {len(result_data)} orders.')
    return result_data

def get_modified_order(wcapi, after,before):
    now = datetime.now()
    print(f'Starting to get Orders from Woo ...')
    before = before + timedelta(days=1)
    for attempt in range(1, 6):
        result_data = []
        page = 1
        filters = {'per_page': 50,
                   'modified_after': f'{after}T00:00:00',
                   'modified_before': f'{before}T00:00:00'
                   }

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

            print(f'Get {len(result_data)} Modified Orders from Woo Success in: {datetime.now() - now}')
            return result_data
        
        except requests.Timeout:
            print(f'Timeout error on attempt {attempt}')
        except requests.RequestException as e:
            print(f'Request error on attempt {attempt}: {e}')

    print(f'Reached maximum retry attempts. Returning {len(result_data)} orders.')
    return result_data
       
def get_all_order(wcapi, after,before):
    now = datetime.now()
    print(f'Starting to get Orders from Woo ...')
  
    for attempt in range(1, 6):
        result_data = []
        page = 1
        filters = {'per_page': 50,
                   'after': f'{after}T00:00:00',
                   'before': f'{before}T00:00:00'
                   }

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

def get_product(wcapi, lst_ids):
    print(f'Starting to get Products from Woo ...')
    
    result_data = []
    if len(lst_ids) > 0:
        ids = ','.join(lst_ids)
         
        page = 1
        filters = {
            'per_page': 25,
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
                return []
                
    print(f'Get {len(result_data)} Products from Woo Success')  
       
    return result_data

def get_all_product(wcapi):
    now = datetime.now()
    print(f'Starting to get Products from Woo ...')
    for attempt in range(1, 6):
        result_data = []
        page = 1
        filters = {'per_page': 25}

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
        
def get_variation(wcapi,site_id):
    def create_temp_sku(row):
        return 'tempsku_'+str(row['site_id_id']) +'_'+ str(row['product_site_id']) +'_'+ str(row['attributes_id'])

    print(f'Starting to get Variations from Woo ...')
    data = get_all_product(wcapi)
    
    pr_sku_lst = []
    for pr in data:
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
                sku_lst = ['(|)'.join(item) for item in result_lst]    
                
            # Create string attributes
            sku_lst = [item.split('(|)') for item in sku_lst]
            # sku_lst = [[sub_item.lower() for sub_item in item] for item in sku_lst]
            temp_dict['meta_data'] = sku_lst
            
            
        else:  
            temp_dict['meta_data'] = None
       
        pr_sku_lst.append(temp_dict)

    df = pd.DataFrame(pr_sku_lst)
    df['date_created'] = datetime.now()
    df['date_modified'] = datetime.now()

    df = df.explode('meta_data')
    df = df[df['meta_data'].notna()]
    df['attributes'] = df['meta_data'].apply(lambda x: [item.split('(:)')[1].lower() for item in x] if x != None else x)
    df['meta_data'] = df['meta_data'].apply(lambda x:[{'key': item.split('(:)')[0], 'value': item.split('(:)')[1]} for item in x] if x != None else x)
    df['attributes_id'] = df['attributes'].apply(lambda x: ' | '.join(sorted(x)) if x != None else 'NA')
    # df['meta_data'] = df['meta_data'].apply(lambda x: create_meta_data(x))
    df['site_id_id'] = site_id
    
    df = df.replace({np.nan: None})
    
    product_site_df = pd.DataFrame(Product_Site.objects.filter(site_id=site_id).values())
    df = df.merge(product_site_df[['product_site_id','site_id_id','product_id']], on = ['product_site_id','site_id_id'], how = 'left')
    df['sku'] = df.apply(create_temp_sku, axis = 1)
    
    df_sku_sys = pd.DataFrame(SKU.objects.all().values())
    df_sku_sys.rename(columns={'sku': 'sku_sys'}, inplace=True)
    if len(df_sku_sys) > 0:
        df = df.merge(df_sku_sys[['product_id', 'attributes_id', 'sku_sys']], on = ['product_id', 'attributes_id'], how= 'left')
        df = df[df['sku_sys'].isna()]

    print(f'Get {len(df)} Variations Success')
    return df

def get_all_tracking_lists(wcapi, site_id, after, before):
    list_tracking = []
    result = get_all_order(wcapi, after, before)
  
    for order in result:
        order_number = order['number']
        add_data={
                'order_number': order_number
            }
        temp_lst = []
        for item in order['line_items']:
            for value in item['meta_data']:
                if 'tracking_number' in value['value']:
                    track = json.loads(value['value'])
                    temp = {
                        'line_item_id' : site_id + '-' + str(item['id']),
                        'tracking_number': track[-1]['tracking_number'] 
                    }
                    temp_lst.append(temp)
                    
        if len(temp_lst) > 0:
            add_data['tracking_item'] = temp_lst
            list_tracking.append(add_data)         
      
    fn_list_tracking = []
    mark = []
    for i in range(0,len(list_tracking)):
        if i in mark:
            fn_list_tracking.append(list_tracking[i])
            continue
        
        for j in range(i+1,len(list_tracking)):
            if list_tracking[i]['tracking_item'][0]['tracking_number'] == list_tracking[j]['tracking_item'][0]['tracking_number']:
                temp = list_tracking[i]['tracking_item'].copy()
                list_tracking[i]['tracking_item'].extend(list_tracking[j]['tracking_item'])
                list_tracking[j]['tracking_item'].extend(temp)
                mark.append(j)
        fn_list_tracking.append(list_tracking[i])
    return fn_list_tracking

def get_shipping_data(tracking_list,API_KEY):
    fn_data = []

    headers = {
        'Content-Type': 'application/json',
        'Tracking-Api-Key': API_KEY
    }
    today = datetime.now(timezone.utc)

    params = {
        'items_amount': 2000,
        'pages_amount' : 1,
    }
    URL = 'https://api.trackingmore.com/v3/trackings/get'
    
    for i in range(0, len(tracking_list), 40):
        time.sleep(2)
  
        batch = tracking_list[i:i+40]
        lst_ord = [item['order_number'] for item in batch]
        pr = ','.join(lst_ord)

        params['order_numbers'] = pr
        response = requests.get(url = URL, headers=headers, params = params)
        code = response.json()['code']
        tracking_data = response.json()['data']
        if code != 200:
            if code != 204:
                print(f'get error {code}: {response.text}')
            continue
        
        filtered_data = [
            tracking for tracking in tracking_data 
            if not (
                (
                    today - datetime.fromisoformat(tracking['created_at']).astimezone(timezone.utc) >= timedelta(days=90) 
                    and tracking['substatus'] == 'notfound001'
                ) 
                or tracking['substatus'] == 'notfound002'
            )
        ]
    
        for tracking in filtered_data:
            for row in batch:
                if row['order_number'] == tracking['order_number']:
                    check = False
                    for track_item in row['tracking_item']:
                        if track_item['tracking_number'] == tracking['tracking_number']:
                            temp = tracking.copy()
                            temp['line_item_id'] = track_item['line_item_id']
                            fn_data.append(temp)
                            check = True
                            
                    if check == False:
                        for ti in row['tracking_item']:
                            temp = tracking.copy()
                            temp['line_item_id'] = ti['line_item_id']
                            fn_data.append(temp)
                    
    return fn_data

def get_updated_shipping_data(max_time_ts, API_KEY):
    CHECKPOINT_FILE_PATH = "/home/mkt-en/ecom_operation/dashboard/etl/checkpoint/tracking_checkpoint.txt"
    def get_last_processed_timestamp():
        try:
            with open(CHECKPOINT_FILE_PATH, "r") as file:
                last_processed_timestamp = file.read()
                return int(last_processed_timestamp)
        except FileNotFoundError:
            tmont = datetime.now() - timedelta(days=1)
            return int(tmont.timestamp())
            
    
  
    print(f'Starting to get tracking data from Tracking More ...')
    
    min_time_ts = get_last_processed_timestamp()
    fn_data = []

    headers = {
        'Content-Type': 'application/json',
        'Tracking-Api-Key': API_KEY
    }
    params = {
        'items_amount': 2000,
        'pages_amount' : 1,
        'updated_date_min' : min_time_ts,
        'updated_date_max': max_time_ts
    }
    URL = 'https://api.trackingmore.com/v3/trackings/get'
    while True:
        response = requests.get(url = URL, headers=headers, params = params)
        
        if response.json()['code'] == 204:
            break
        elif response.json()['code'] not in [200, 204]:
            return fn_data
        
        data = response.json()['data']
        fn_data.extend(data)
        params['pages_amount'] += 1
        time.sleep(2)
        
    for dt in fn_data:
        if dt['substatus'] == 'notfound002':
            dt['valid'] = 0
        else:
            dt['valid'] = 1
       
    tracking_numbers = set(tracking['tracking_number'] for tracking in fn_data)
    # Assuming 'tracking_number' is a unique field in the Shipping model
    shipping_ids = Shipping.objects.filter(tracking_number__in=tracking_numbers).values_list('tracking_number', flat=True)
    # Only keep tracking data with matching tracking numbers
    fn_data = [tracking for tracking in fn_data if tracking['tracking_number'] in shipping_ids]   
       
       
        
    print(f'Complete get {len(fn_data)} Tracking Numbers from Tracking More ...')
    
       
    return fn_data

def get_coupons(wcapi):
    print(f'Starting to get Coupons from Woo ...')
    
    result_data = []
    page = 1
    filters = {
        'per_page': 100,
    }
    while True:
        filters['page'] = page
        response = wcapi.get('coupons', params=filters)
        if response.status_code == 200:
            headers = response.headers
            data = response.json()
            for coupon in data:
                replace_empty_strings_with_none(coupon)
                result_data.append(coupon)
            page+=1
            if page > int(headers['x-wp-totalpages']):
                break
         
        else:
            print(f'Get Coupons Failed with Error {response.status_code}: {response.text}')
            return []
    
    print(f'Get {len(result_data)} Coupons from Woo Success')  
       
    return result_data

def get_gateways(wcapi):
    print(f'Starting to get Gateways from Woo ...')
    
    result_data = []
    response = wcapi.get('payment_gateways')
    if response.status_code == 200:
        headers = response.headers
        data = response.json()
        for gateway in data:
            if gateway['id'] == "stripe" and gateway["enabled"] == True:
                replace_empty_strings_with_none(gateway)
                result_data.append(gateway)
    else:
        print(f'Get Gateways Failed with Error {response.status_code}: {response.text}')
        return []
    
    print(f'Get {len(result_data)} Gateways from Woo Success')  
       
    return result_data

def get_shipping_method(wcapi):
    print(f'Starting to get Shipping methods from Woo ...')
    
    result_data = []
   
    filters = {
        'per_page': 100,
    }
    response = wcapi.get('shipping_methods', params=filters)
    if response.status_code == 200:
        data = response.json()
        for method in data:
            replace_empty_strings_with_none(method)
            result_data.append(method)
         
    else:
        print(f'Get Shipping methods Failed with Error {response.status_code}: {response.text}')
        return []
    
    print(f'Get {len(result_data)} Shipping methods from Woo Success')  
       
    return result_data

def get_transaction_dispute(time_checkpoint):
    dispute_transaction_id = []
    for paypal_gateway in Key_API.objects.filter(code='paypal_express'):
        CLIENT_ID = paypal_gateway.authentication['key']
        CLIENT_SECRET = paypal_gateway.authentication['secret']
        response = requests.post(
            'https://api-m.paypal.com/v1/oauth2/token',
            auth=HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data= {'grant_type': 'client_credentials'}
        )

        token = response.json()['access_token']

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }
        time_checkpoint = time_checkpoint.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        
        params = {
            'start_time': time_checkpoint,
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
            for trans in data['disputed_transactions']:
                if trans['seller_transaction_id'] not in dispute_transaction_id:
                    dispute_transaction_id.append(trans['seller_transaction_id'])   
        
    # Get dispute from Stripe 
    file_path = '/home/mkt-en/ecom_operation/dashboard/etl/checkpoint/stripe_dispute.txt'
    if os.path.exists(file_path):
        with open(file_path, 'r') as file_check:
            stripe_checkpoint = json.load(file_check)  
    else:
        stripe_checkpoint = {}
    for stripe_gateway in Key_API.objects.filter(code='stripe'):
        stripe.api_key = stripe_gateway.authentication['secret']
        if stripe_gateway.name in stripe_checkpoint:
            starting_after = stripe_checkpoint[stripe_gateway.name]
        else:
            starting_after = None
        while True:
            response = stripe.Dispute.list(limit=100,starting_after=starting_after)
            
            for trans in response['data']:
                if trans['charge'] != None and trans['charge'] not in dispute_transaction_id:
                    dispute_transaction_id.append(trans['charge'])
                if trans['payment_intent'] != None and trans['payment_intent'] not in dispute_transaction_id:
                    dispute_transaction_id.append(trans['payment_intent'])
            
            if response['count'] > 0:
                starting_after = response['data'][-1]['id']
            if response['has_more'] == False:
                break
        
        stripe_checkpoint[stripe_gateway.name] = starting_after
        
    with open(file_path, 'w') as file_check:
        json.dump(stripe_checkpoint, file_check, indent=2)
        
    return dispute_transaction_id