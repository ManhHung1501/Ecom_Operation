import sys
sys.path.insert(0, '/home/mkt-en/ecom_operation')
sys.path.insert(0, '/home/mkt-en/ecom_operation/dashboard/etl')
import os
import django
# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecom_operation.settings')
django.setup()
from django.db import connection
from dashboard.models import  Order, Order_Line_Item, Variation, Batch, SKU, Shipping, Shipping_Detail, UserActionLog, Template_Export,Key_API, Notification, Product_Site,Email_Sent, Site, Email_Template, Auto_Email_Template, Ticket
from django.db.models import Subquery, OuterRef, Case, When, Value, IntegerField, Count, F, Min, Max, Q, CharField, Sum
from django.db.models.functions import Concat
from django.db import transaction
from django.conf import settings
from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from datetime import datetime, date, timedelta, timezone
import time
import pandas as pd
import numpy as np
from urllib.parse import urlparse
from woocommerce import API
import stripe
import requests
from requests.auth import HTTPBasicAuth
import re
import json
from get_data import replace_empty_strings_with_none, get_variation , get_coupons, get_gateways
from status_map import status_mapping, payment_status, item_status, item_tag,sys_to_woo
from load import remove_emoji, load_sku_df, load_variation_df, load_order, load_shipping
from run import etl_variation, etl_order
from manage_func import update_item_status, update_order_status, sync_to_woo, init_connection, send_email
import warnings
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
warnings.filterwarnings('ignore', category=RuntimeWarning)
from rest_framework.response import Response
from rest_framework.parsers import FileUploadParser
import rest_framework.status as http_status
from rest_framework.decorators import api_view
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import authentication_classes, permission_classes
from .serializers import OrderSerializer, OrderLineItemSerializer, SiteSerializer, BatchSerializer, SKUSerializer, ShippingSerializer, VariationSerializer, TemplateExportSerializer, NotificationSerializer, ProductSiteSerializer, UserActionLogSerializer, EmailTemplateSerializer,UploadedImageSerializer,AutoEmailTemplateSerializer, TicketSerializer
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi



def generate_export_link(df, filename):
    today  = date.today().strftime('%Y-%m-%d')
    ts_now  = int(time.time())
    filename = filename + f'_{today}_{ts_now}.csv'
    file_path = os.path.join(settings.EXPORT_ROOT, filename)
    df.to_csv(file_path, index=False)
    download_link = os.path.join(settings.HOST_URL,settings.EXPORT_URL, filename)
    
    return download_link

def generate_cache_key(request):
    key_parts = [request.path]
    for param, value in request.GET.items():
        key_parts.append(f"{param}={value}")
    return "_".join(key_parts)

def search_string(queryset, param_name, param_value):
    search = {}
    param_value = json.loads(param_value)
    param_value['search_type'] = param_value['search_type'].lower()
    if param_value['search_type'] == 'notcontains':
        search[f'{param_name}__icontains'] = param_value['value']
        queryset = queryset.exclude(**search)
    else:
        if param_value['search_type'] == 'includes':
            search[f'{param_name}__in'] = [i.strip() for i in param_value['value'].split(',')]
        else:
            search[f'{param_name}__i'+param_value['search_type']] = param_value['value']
        for key, value in search.items():
            if value:
                queryset = queryset.filter(Q(**{key: value}))
    return queryset

def get_string_status(status_map, status):
    reversed_status = {v: k for k, v in status_map.items()}
    return reversed_status.get(status,None)

def create_refund(order, amount=None):
    transaction_id = order.transaction_id
    if order.payment_method == 'paypal_express':
        PAYPAL_HOST = "https://api-m.paypal.com/v1"
        PAYPAL_KEY = Key_API.objects.get(name = order.payment_method_title)
        CLIENT_ID = PAYPAL_KEY.authentication['key']
        CLIENT_SECRET = PAYPAL_KEY.authentication['secret']

        response = requests.post(
            PAYPAL_HOST+'/oauth2/token',
            auth=HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data= {"grant_type": "client_credentials"}
        )
        token = response.json()['access_token']     
                
        refund_url = f'https://api.paypal.com/v2/payments/captures/{transaction_id}/refund'
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }
        
        if amount != None:
            refund_data = {
                'amount': {
                    'currency_code': 'USD',  # Set the currency code
                    'value': str(amount),  # Set the amount to refund
                }
            }
            order.refund_amount = round(order.refund_amount + amount, 2)
            refund_response = requests.post(refund_url, data=json.dumps(refund_data), headers=headers)
        else:
            refund_response = requests.post(refund_url, headers=headers)
            order.refund_amount = order.total_amount
            
        
        if refund_response.status_code==201:
            is_success = 'success'
        else:
            is_success = refund_response.text
    elif order.payment_method == 'stripe':
        stripe.api_key = Key_API.objects.get(name = order.payment_method_title).authentication['secret']
        if transaction_id.startswith('ch_'):
            params = {'charge': transaction_id }
        elif transaction_id.startswith('pi_'):
            params = {'payment_intent': transaction_id }
        
        if amount != None:
            params['amount'] = amount * 100
            order.refund_amount  = round(order.refund_amount - amount, 2)
        else:
            order.refund_amount = - order.total_amount
            
        refund = stripe.Refund.create(**params)
        if refund.status == 'succeeded':
            is_success = 'success'
        else:
            is_success = json.dumps(refund, indent=2)

    if is_success == 'success':
        order.payment_status = 2
        order.save()
        if amount==None:
            order_site_id = order.order_id.split('-')[-1]
            site = order.site_id
            wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
            wcapi.put(f'orders/{order_site_id}', {'status': 'refunded'})
    
    return is_success

# ----------------WEBHOOK----------------------
@csrf_exempt
def woocommerce_webhook(request):
    if request.method == 'POST':
        # Verify the webhook secret
        try:
            new_order = replace_empty_strings_with_none(json.loads(request.body.decode('utf-8')))
            link_order = new_order['_links']['collection'][0]['href']
            link_order  = '/'.join(link_order.split('/')[:3])
            
            site = Site.objects.get(link=link_order)
            wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret']) 
            if wcapi:
                load_order(new_order, site, wcapi)
                if site.auto_send_mail == 1 and new_order['status'] == 'processing':
                    order = Order.objects.get(order_id=site.site_id + '-' + str(new_order['id']))
                    if order.last_confirm_sent == None: 
                        email_template = Email_Template.objects.get(id=1)
                        send_email(order, email_template, site.email, order.email)
                
                cache.clear()
                return JsonResponse({'status': 'success'}, status=200)
        except json.JSONDecodeError:
            print(f'Invalid JSON data with body {request.body}' )
            return JsonResponse({'error': 'Invalid JSON data'}, status=200)
    else:
        print('Invalid request method')
        return JsonResponse({'error': 'Invalid request method'}, status=405)

@csrf_exempt
def sendgrid_webhook(request):
    # try:
    data = json.loads(request.body.decode('utf-8'))
    event_mapping = {
        'processed': 'processed',
        'dropped': 'dropped',
        'delivered': 'delivered',
        'deferred': 'deferred',
        'bounce': 'bounce',
        'open': 'open_event',
        'click': 'click',
    }
    for event in data:
        message_id = event['sg_message_id'].split('.')[0]
        message = get_object_or_404(Email_Sent, message_id=message_id)
        event_type = event['event']
        message_list = event_mapping.get(event_type)

        if message_list is not None:
            if isinstance(getattr(message, message_list), list):
                getattr(message, message_list).append(event)
            else:
                setattr(message, message_list, [event])
            message.save()
            
    # except Exception as e:
    #     return JsonResponse({'Server get error': str(e)}, status=500)
    return JsonResponse({'results': 'ok'}, status=200)


# ------------------Authentication----------------------
from django.contrib.auth import authenticate
from django.conf import settings

@swagger_auto_schema(
    method='POST',
    request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'username': openapi.Schema(type=openapi.TYPE_STRING, description='Username'),
                'password': openapi.Schema(type=openapi.TYPE_STRING, description='Password'),
            }
        ),
    responses={
        200: openapi.Response('Successful Authentication'),
        400: openapi.Response('Bad Request'),
        403: openapi.Response('Forbidden')
    },
 ) 
@api_view(['POST'])
def login_view(request):
    try:
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            token, created = Token.objects.get_or_create(user=user)
            return Response(
                {
                    'Token': token.key, 
                    'User': {
                        'username': user.username,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'email': user.email,
                        'is_active': user.is_active,
                        'is_superuser': user.is_superuser
                    }
                }, status=200
                )
        else:
            return Response({'error': 'Forbidden'}, status=403)
    except Exception as e:
        return Response({'error': f'Server get errror {e}'}, status=500)



# ---------------REPORT---------------------
@swagger_auto_schema(
        method='GET',
        manual_parameters=[
            openapi.Parameter('start_date', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Start date (ISO format: YYYY-MM-DD)'),
            openapi.Parameter('end_date', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='End date (ISO format: YYYY-MM-DD)'),
        ],
        responses={
            200: openapi.Response(
                'Successful Response',
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'total_sales': openapi.Schema(type=openapi.TYPE_NUMBER, description='Total sales amount within the specified date range.'),
                        'active_site': openapi.Schema(type=openapi.TYPE_INTEGER, description='Count of active sites with orders.'),
                        'count_order': openapi.Schema(type=openapi.TYPE_INTEGER, description='Total number of orders.'),
                        'product_sold': openapi.Schema(type=openapi.TYPE_INTEGER, description='Total number of products sold.'),
                        'total_sales_each_day': openapi.Schema(type=openapi.TYPE_NUMBER, description='Total sales amount for each day within the specified date range.'),
                        'orders_each_day': openapi.Schema(type=openapi.TYPE_INTEGER, description='Count of orders for each day within the specified date range.'),
                    },
                ),
            ),
        },
    )
@api_view(['GET'])
def view_report(request):
    start_date_str = request.GET.get('start_date', (date.today() - timedelta(days=1)).isoformat())
    start_date = datetime.fromisoformat(start_date_str)
    end_date_str = request.GET.get('end_date', date.today().isoformat())
    end_date = datetime.fromisoformat(end_date_str)  + timedelta(days=1)
    
    order_data = Order.objects.filter(date_created__gte = start_date, date_created__lt = end_date, status__in = [1, 3])
    total_sales = 0
    active_site = []
    count_order = len(order_data)
    product_sold = 0
    total_sales_each_day = {}
    orders_each_day = {}
    for order in order_data:
        total_sales += order.total_amount
        if order.site_id not in active_site:
            active_site.append(order.site_id)
        product_sold += order.number_items
        if str(order.date_created.date()) not in total_sales_each_day:
            total_sales_each_day.update({str(order.date_created.date()):0})
        total_sales_each_day[str(order.date_created.date())] += order.total_amount
        if str(order.date_created.date()) not in orders_each_day:
            orders_each_day.update({str(order.date_created.date()):0})
        orders_each_day[str(order.date_created.date())] += 1
    data = {
        "total_sales": total_sales,
        "active_site": len(active_site),
        "count_order": count_order,
        "product_sold": product_sold,
        "total_sales_each_day": total_sales_each_day,
        "orders_each_day": orders_each_day
        }
    return Response(data)


# ---------------------ORDER------------------
@swagger_auto_schema(
        method='GET',
        manual_parameters=[
            openapi.Parameter('page', openapi.IN_QUERY, description="Page number ", type=openapi.TYPE_INTEGER),
            openapi.Parameter('per_page', openapi.IN_QUERY, description="Items per page (-1 to return all)", type=openapi.TYPE_INTEGER),
            openapi.Parameter('order_by', openapi.IN_QUERY, description="Order by field", type=openapi.TYPE_STRING),
            openapi.Parameter('order_type', openapi.IN_QUERY, description="Order type (asc/desc)", type=openapi.TYPE_STRING),
            openapi.Parameter('start_date', openapi.IN_QUERY, description="Start date date paid (ISO format)", type=openapi.TYPE_STRING),
            openapi.Parameter('end_date', openapi.IN_QUERY, description="End date date paid (ISO format)", type=openapi.TYPE_STRING),
            openapi.Parameter('start_date_created', openapi.IN_QUERY, description="Start date date created (ISO format)", type=openapi.TYPE_STRING),
            openapi.Parameter('end_date_created', openapi.IN_QUERY, description="End date date created (ISO format)", type=openapi.TYPE_STRING),
            openapi.Parameter('status', openapi.IN_QUERY, description="Status (1,2,3,...)", type=openapi.TYPE_STRING),
            openapi.Parameter('payment_status', openapi.IN_QUERY, description="Status (1,2,3,...)", type=openapi.TYPE_STRING),
            openapi.Parameter('order_number', openapi.IN_QUERY, description="string to search order number", type=openapi.TYPE_STRING),
            openapi.Parameter('phone', openapi.IN_QUERY, description="search_type:(contains,not_conatins,include,startswith,endswith),value:string", type=openapi.TYPE_STRING),
            openapi.Parameter('email', openapi.IN_QUERY, description="search_type:(contains,not_conatins,include,startswith,endswith),value:string", type=openapi.TYPE_STRING),
            openapi.Parameter('site_id', openapi.IN_QUERY, description="site_id (KATC,...)", type=openapi.TYPE_STRING),
            openapi.Parameter('is_dispute', openapi.IN_QUERY, description="1 to get dispute order", type=openapi.TYPE_STRING),
            openapi.Parameter('tracking_number', openapi.IN_QUERY, description="search_type:(contains,not_conatins,include,startswith,endswith),value:string", type=openapi.TYPE_STRING),
            openapi.Parameter('product_name', openapi.IN_QUERY, description="search_type:(contains,not_conatins,include,startswith,endswith),value:string", type=openapi.TYPE_STRING),
            openapi.Parameter('sku', openapi.IN_QUERY, description="search_type:(contains,not_conatins,include,startswith,endswith),value:string", type=openapi.TYPE_STRING),
            openapi.Parameter('temp_sku', openapi.IN_QUERY, description="true to filter orders have temp sku and will clear all filter", type=openapi.TYPE_STRING),
            openapi.Parameter('batch_id', openapi.IN_QUERY, description="batch filter", type=openapi.TYPE_STRING),
            openapi.Parameter('get_current_order_id', openapi.IN_QUERY, description="true to get current query order id", type=openapi.TYPE_STRING),
            openapi.Parameter('exclude_order_id', openapi.IN_QUERY, description="exclude_order_id in order id return", type=openapi.TYPE_STRING),
            openapi.Parameter('export', openapi.IN_QUERY, description="true to export current filter return CSV format", type=openapi.TYPE_STRING),
            openapi.Parameter('export_order_id', openapi.IN_QUERY, description="order_id to export (KATC-1,KATC-2,...)", type=openapi.TYPE_STRING),
            openapi.Parameter('export_field_order', openapi.IN_QUERY, description="field of order to export (order_id,order_number,...) if not input will return all field", type=openapi.TYPE_STRING),
            openapi.Parameter('export_field_item', openapi.IN_QUERY, description="item_name,batch_id,supplier,quantity,subtotal_amount,total_amount,sku,tag  if not input will return all field", type=openapi.TYPE_STRING),
            openapi.Parameter('order_of_fields', openapi.IN_QUERY, description="order of fields to export", type=openapi.TYPE_STRING),
        ],
        responses={
            200: openapi.Response('Successful Response', OrderSerializer(many=True)),
            400: 'Bad Request',
        },
    )
@swagger_auto_schema(
        method='POST',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'site_id': openapi.Schema(type=openapi.TYPE_STRING),    
                'status': openapi.Schema(type=openapi.TYPE_INTEGER),
                'set_paid': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'first_name': openapi.Schema(type=openapi.TYPE_STRING),
                'last_name': openapi.Schema(type=openapi.TYPE_STRING),
                'email': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_EMAIL),
                'phone': openapi.Schema(type=openapi.TYPE_STRING),
                'address_1': openapi.Schema(type=openapi.TYPE_STRING),
                'address_2': openapi.Schema(type=openapi.TYPE_STRING),
                'city': openapi.Schema(type=openapi.TYPE_STRING),
                'state_code': openapi.Schema(type=openapi.TYPE_STRING),
                'postcode': openapi.Schema(type=openapi.TYPE_STRING),
                'country_code': openapi.Schema(type=openapi.TYPE_STRING),
                'currency': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_first_name': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_last_name': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_phone': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_address_1': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_address_2': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_city': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_state_code': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_postcode': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_country_code': openapi.Schema(type=openapi.TYPE_STRING),
                'payment_method': openapi.Schema(type=openapi.TYPE_STRING),
                'payment_method_title': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                'coupon_code':openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_STRING)
                    ),
                'line_items': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'sku': openapi.Schema(type=openapi.TYPE_STRING),
                            'subtotal_amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                            'total_amount':  openapi.Schema(type=openapi.TYPE_NUMBER)
                        },
                        required=['quantity', 'sku']  # Add required fields
                    )
                ),
            },
            required=['site_id', 'status']  # Add required fields
        ),
        responses={
            201: openapi.Response('Created', OrderSerializer),
            400: 'Bad Request',
        },
    )
@api_view(['GET','POST'])
def read_or_create_orders(request):    
    if request.method == 'GET':
        # return cache data if it exist
        cache_key = generate_cache_key(request)
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
    
        params = request.GET

        # Validate and sanitize parameters
        try:
            page = int(params.get('page', 1))
            per_page = int(params.get('per_page', 10))
        except ValueError:
            return Response({'error': 'Invalid page or per_page value'}, status=400)

        # Sort
        order_by = params.get('order_by', 'date_created')
        order_type = params.get('order_type', 'desc')
        if order_by == 'tracking_number':
            queryset = Order.objects.annotate(
                num_tracking=Count('line_items__shippings__tracking_number',  distinct=True)
            ).order_by('num_tracking' if order_type == 'asc' else '-num_tracking', '-date_created')
        elif order_by == 'batch_id':
            queryset = Order.objects.annotate(
                sum_batch=Sum('line_items__batch_id__batch_id',  distinct=True)
            ).order_by('sum_batch' if order_type == 'asc' else '-sum_batch', '-date_created')
        else:
            order_by_field = order_by if order_type == 'asc' else '-' + order_by
            queryset = Order.objects.all().order_by(order_by_field)
        
        # Define Filter
        filters = {}
        if 'start_date' in params:
            filters['date_paid__gte'] = params['start_date']
        
        if 'end_date' in params:
            filters['date_paid__lte'] = params['end_date']

        if 'start_date_created' in params:
            filters['date_created__gte'] = params['start_date_created']
          
        if 'end_date_created' in params:
            end_date = datetime.fromisoformat(params['end_date_created'])  + timedelta(days=1)
            queryset = queryset.filter(date_created__lte= end_date)
            # filters['date_created__lte'] = params['end_date_created']
          
        if 'status' in params:
            filters['status__in'] = params['status'].split(',')
     
        if 'payment_status' in params:
            filters['payment_status__in'] = params['payment_status'].split(',')
           
        if 'site_id' in params:
            filters['site_id__in'] = params['site_id'].split(',')

        if 'is_dispute' in params:
            filters['is_dispute'] = params['is_dispute']
     
        if  'batch_id' in params:
            filters['batch_id__in'] = params['batch_id'].split(',')
            
        if 'order_number' in params:
            queryset = search_string(queryset, 'order_number', params['order_number'])
      
        if 'email' in params:
            queryset = search_string(queryset, 'email', params['email'])  
        
        if 'phone' in params: 
            queryset = search_string(queryset, 'phone', params['phone'])  
            
        if 'postcode' in params:
            queryset = search_string(queryset, 'postcode', params['postcode'])  
         
        if 'product_name' in params:
            queryset = search_string(queryset, 'line_items__item_name', params['product_name']).distinct() 
         
        if  'tracking_number' in params:
            queryset = search_string(queryset, 'line_items__shippings__tracking_number', params['tracking_number']).distinct() 
            
        if  'sku' in params:
            queryset = search_string(queryset, 'line_items__sku__sku', params['sku']).distinct() 
        
        #Apply Filter 
        for key, value in filters.items():
            if value:
                queryset = queryset.filter(Q(**{key: value}))
        
        # Return other data if boolean params
        if params.get('temp_sku','false') == 'true':
            queryset = Order.objects.filter(line_items__sku__sku__startswith='tempsku_').distinct() 
        
        if params.get('get_current_order_id','false') == 'true':
            order_ids = list(queryset.values_list('order_id', flat=True))
            if 'exclude_order_id' in params:
                order_ids = [i for i in order_ids if i not in params['exclude_order_id'].split(',')]
            return Response({'results': order_ids})
         
        # export
        if params.get('export','false') == 'true':
            if 'export_order_id' in params:
                queryset = queryset.filter(order_id__in = params['export_order_id'].split(",") )
                
            queryset = queryset.select_related('line_items')
            
            exclude_order_field = ['line_items', 'shipping_name','number_items','sent_emails']
            export_field_order_request = []
            if 'export_field_order' in params:
                export_field_order_request = params['export_field_order'].split(',')
                export_field_order = [field for field in params['export_field_order'].split(',')  if field not in exclude_order_field]
            else:
                export_field_order = [field.name for field in Order._meta.get_fields() if field.name not in exclude_order_field]
            
            exclude_item_field = ['order_id', 'date_created', 'date_modified', 'shippings','meta_data_id']
            if 'export_field_item' in params:
                export_field_item = [f'line_items__{field}' for field in params['export_field_item'].split(',')  if field not in exclude_item_field]
            else:
                # export_field_item = [f'line_items__{field.name}' for field in Order_Line_Item._meta.get_fields() if field.name not in exclude_item_field] 
                export_field_item = []
            
            export_field_order.extend(['first_name', 'last_name'])
            df = pd.DataFrame.from_records(
                queryset.values(*export_field_order, *export_field_item)
            )
      
            df['shipping_name'] = df['first_name'] + ' ' + df['last_name']
            drop_col = []
            for column in ['first_name', 'last_name', 'shipping_name']:
                if column not in export_field_order_request and 'export_field_order' in params:
                    drop_col.append(column)
            df.drop(columns=drop_col, inplace=True)
            
            if 'order_of_fields' in params:
                order_of_fields = [
                    'line_items__'+field if field in params['export_field_item'].split(',') 
                    else field
                    for field in params['order_of_fields'].split(',') 
                ]
                df = df[order_of_fields]
            
            # Change status from int to string
            if 'status' in export_field_order:
                df['status'] = df['status'].apply(lambda x: get_string_status(status_mapping, x))
            if 'payment_status' in export_field_order:
                df['payment_status'] = df['payment_status'].apply(lambda x: get_string_status(payment_status,x))
            # if 'line_items__status' in export_field_item:
            #     df['line_items__status'] = df['line_items__status'].apply(lambda x: get_string_status(item_status,x))
            if 'line_items__tag' in export_field_item:
                df['line_items__tag'] = df['line_items__tag'].apply(lambda x: get_string_status(item_tag,x))
            if 'coupon_code' in export_field_order:
                df['coupon_code'] = df['coupon_code'].apply(lambda x: np.nan if not x else x)
            
            # Rename column to pretty
            column_mapping = {
                'order_id': 'Order ID',
                'site_id': 'Site ID',
                'order_number': 'Order Number',
                'transaction_id': 'Transaction ID',
                'status': 'Status',
                'fulfill_status': 'Fulfill Status',
                'payment_status': 'Payment Status',
                'number_items': 'Number of Items',
                'first_name': 'First Name',
                'last_name': 'Last Name',
                'shipping_name': 'Shipping Name',
                'email': 'Email',
                'phone': 'Phone',
                'address_1': 'Address 1',
                'address_2': 'Address 2',
                'city': 'City',
                'state_code': 'State Code',
                'postcode': 'Postcode',
                'country_code': 'Country Code',
                'currency': 'Currency',
                'shipping_first_name': 'Shipping First Name',
                'shipping_last_name': 'Shipping Last Name',
                'shipping_phone': 'Shipping Phone',
                'shipping_address_1': 'Shipping Address 1',
                'shipping_address_2': 'Shipping Address 2',
                'shipping_city': 'Shipping City',
                'shipping_state_code': 'Shipping State Code',
                'shipping_postcode': 'Shipping Postcode',
                'shipping_country_code': 'Shipping Country Code',
                'payment_method': 'Payment Method',
                'payment_method_title': 'Payment Method Title',
                'discount_amount': 'Discount Amount',
                'coupon_code': 'Coupon Code',
                'refund_amount': 'Refund Amount',
                'shipping_amount': 'Shipping Amount',
                'total_amount': 'Total Amount',
                'date_paid': 'Date Paid',
                'date_created': 'Date Created',
                'date_modified': 'Date Modified',
                'date_completed': 'Date Completed',
                'line_items__line_item_id': 'Line Item ID',
                'line_items__batch_id': 'Line Item Batch ID',
                'line_items__item_name': 'Line Item Name',
                'line_items__sku': 'Line Item SKU',
                'line_items__supplier': 'Line Item Supplier',
                'line_items__quantity': 'Line Item Quantity',
                'line_items__subtotal_amount': 'Line Item Subtotal Amount',
                'line_items__total_amount': 'Line Item Total Amount',
                'line_items__price': 'Line Item Price',
                'line_items__status': 'Line Item Status',
                'line_items__tag': 'Line Item Tag',
            }
            df.rename(columns=column_mapping, inplace=True)
            
            return Response({'csv': generate_export_link(df, 'export_order')}) 
         
        if per_page == -1:    
            serializer = OrderSerializer(queryset, many=True)
            data = {
                'page': 1,
                'per_page': -1,
                'total_pages': 1,
                'total_rows': len(queryset),
                'results': serializer.data
            } 
        else:
            paginator = Paginator(queryset, per_page)
            page_obj = paginator.get_page(page)
            serializer = OrderSerializer(page_obj, many=True)
            data = {
                'page': page,
                'per_page': per_page,
                'total_pages': paginator.num_pages,
                'total_rows': paginator.count,
                'results': serializer.data
            }
        
        cache.set(cache_key, data, 60 * 15)    
        return Response(data)
    
    elif request.method == 'POST':
        create_data = request.data
        line_items_data = []
        for i in create_data['line_items']:
            variation_int = Variation.objects.filter(sku = i['sku'], site_id = create_data['site_id']).first()
            line_items_data.append(
                {
                    'quantity': i['quantity'],
                    'product_id': int(variation_int.product_site_id),
                    'meta_data': variation_int.meta_data if variation_int.meta_data != None else [],
                    'subtotal': str(i['subtotal_amount']),
                    'total': str(i['total_amount'])
                }
            )
        # site = Site.objects.get(site_id=create_data['site_id'])
        # wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
        # data = {
        #     "status": sys_to_woo.get(create_data.get('status', 0)),
        #     "currency": create_data.get('currency','USD'),
        #     "payment_method": create_data.get('payment_method',""),
        #     "payment_method_title": create_data.get('payment_method_title',""),
        #     "set_paid": True if create_data.get('set_paid') =='true' else False,
        #     "billing": {
        #         "first_name": create_data.get('first_name',""),
        #         "last_name": create_data.get('last_name',""),
        #         "address_1": create_data.get('address_1',""),
        #         "address_2":create_data.get('address_1',""), 
        #         "city":create_data.get('city',""), 
        #         "state":create_data.get('state',""), 
        #         "postcode":create_data.get('postcode',""), 
        #         "country":create_data.get('country',""), 
        #         "email":create_data.get('email',""), 
        #         "phone":create_data.get('phone',"")
        #     },
        #     "shipping": {
        #         "first_name":create_data.get('shipping_first_name',""), 
        #         "last_name":create_data.get('shipping_last_name',""),  
        #         "address_1":create_data.get('shipping_address_1',""),  
        #         "address_2":create_data.get('shipping_address_2',""), 
        #         "city":create_data.get('shipping_city',""),  
        #         "state":create_data.get('shipping_state',""), 
        #         "postcode":create_data.get('shipping_postcode',""), 
        #         "country":create_data.get('shipping_country',""),  
        #         "phone":create_data.get('shipping_phone',""),  
        #     },
        #     "line_items": line_items_data,
        #     "shipping_lines": [
        #         {
        #             "method_id": "flat_rate",
        #             "total": str(create_data.get('shipping_amount',0))
        #         }
        #     ],
        #     "coupon_lines": [
        #         {
        #             "code": code
        #         }
        #         for code in create_data.get('coupon_code',[])
        #     ],
        # }     
        
        # new_order = wcapi.post('orders', data).json()
        # load_order(new_order, site.site_id, wcapi)
        
        # UserActionLog.objects.create(
        #         user=request.user,
        #         action='Create',
        #         object_name = 'Order',
        #         object_id = site.site_id+'-'+str(new_order['id']),
        #     )
        # VALIDATE
        # if len(line_items_data) == 0:
        #     return Response({'error': 'order must contain line item data'}, status=400)
        
        # # POST TO WOOCOMMERCE
        # ts_now = int(time.time() * 1000)
        # create_data['order_id'] = 'SYSTEM-' + create_data['site_id'] +'-' + str(ts_now)
        # serializer = OrderSerializer(data=create_data)
        # if serializer.is_valid():
        #     order_instance = serializer.save()
        #     for item in line_items_data:
        #         variation = Variation.objects.get(sku = item['sku'])
        #         i = 1
        #         Order_Line_Item.objects.create(
        #             line_item_id = create_data['order_id'] + '-' + str(i),
        #             order_id = order_instance,
        #             item_name = variation.product_site_name,
        #             quantity = item['quantity'],
        #             sku =  SKU.objects.get(sku=variation.sku),
        #             status = item['status'],
        #             date_modified = datetime.now(),
        #             date_created = datetime.now()
        #         )
        #         i += 1
            
           
        return Response({'success': 'created order successful'}, status=200)
        # else:
        #     return Response({'error': f'{serializer.errors}'}, status=400)
            
@swagger_auto_schema(
        methods=['GET', 'DELETE'],
        manual_parameters=[
            openapi.Parameter('order_id', openapi.IN_PATH, description="Order ID", type=openapi.TYPE_STRING),
        ],
        responses={
            200: openapi.Response('Successful Response', OrderSerializer),
            204: 'No Content',
            400: 'Bad Request',
            404: 'Not Found',
        },
    )
@swagger_auto_schema(
        method='PUT',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'status': openapi.Schema(type=openapi.TYPE_INTEGER),
                'is_dispute': openapi.Schema(type=openapi.TYPE_INTEGER),
                'first_name': openapi.Schema(type=openapi.TYPE_STRING),
                'last_name': openapi.Schema(type=openapi.TYPE_STRING),
                'email': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_EMAIL),
                'phone': openapi.Schema(type=openapi.TYPE_STRING),
                'address_1': openapi.Schema(type=openapi.TYPE_STRING),
                'address_2': openapi.Schema(type=openapi.TYPE_STRING),
                'city': openapi.Schema(type=openapi.TYPE_STRING),
                'state_code': openapi.Schema(type=openapi.TYPE_STRING),
                'postcode': openapi.Schema(type=openapi.TYPE_STRING),
                'country_code': openapi.Schema(type=openapi.TYPE_STRING),
                'currency': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_first_name': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_last_name': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_phone': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_address_1': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_address_2': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_city': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_state_code': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_postcode': openapi.Schema(type=openapi.TYPE_STRING),
                'shipping_country_code': openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        responses={
            200: openapi.Response('Successful Response', OrderSerializer),
            204: 'No Content',
            400: 'Bad Request',
            404: 'Not Found',
        },
    )
@api_view(['GET','PUT','DELETE'])
def rud_an_order(request, order_id):
    order = get_object_or_404(Order, order_id=order_id)
    site = order.site_id
    order_site_id = order.order_id.split('-')[-1]
    wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
    
    if request.method == 'GET':
        serializer = OrderSerializer(order)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        try:
            status_update = request.data.get('status')
            if order.status == 6:
                return Response({'error': 'Order is completed and not allowed to edit'}, status=400)
            for key in request.data:
                if request.data[key] != getattr(order,key) and key != 'status' and order.status in [1,2,3,4,5,6,7]:
                    return Response({'error': f'Order is {get_string_status(status_mapping,order.status)} and not allowed to edit customer infomation'}, status=400)
            if status_update:
                if status_update not in [0,1,7,8,9]:
                    return Response({'error': f'Not allowed to change status'}, status=400)
                else:
                    if status_update in [1,8,9] and order.status != 0:
                        return Response({'error': f'Order is {get_string_status(status_mapping,order.status)} and not allowed to change status'}, status=400) 
                    if status_update == 1:
                        line_items = order.line_items.all()
                        if line_items.filter(sku__sku__istartswith='tempsku').exists():
                            return Response({'error': 'Order have item not have sku and not allowed to change status'}, status=400)
                        
            orderpr = {key : getattr(order,key) for key in request.data.keys()}
            
            serializer = OrderSerializer(order, data=request.data, partial=True)
            if serializer.is_valid():
                update_order = serializer.save()
                if status_update != orderpr['status']:
                    line_items = update_order.line_items.all()
                    update_item_status(line_items)
                    if status_update == 7:
                        batch_ids = list(line_items.values_list('batch_id', flat = True).distinct())
                        batchs = Batch.objects.filter(batch_id__in = batch_ids)
                        line_items.update(batch_id=None)  
                        for batch in batchs:
                            if batch.number_items == 0:
                                batch.delete()
                         
                if not order.order_id.startswith('RS-'):       
                    data = {
                        "status": sys_to_woo.get(update_order.status,'pending'),
                        "currency": update_order.currency,
                        "billing": {
                            "first_name": update_order.first_name if update_order.first_name != None else "",
                            "last_name": update_order.last_name if update_order.last_name != None else "",
                            "address_1": update_order.address_1 if update_order.address_1 != None else "",
                            "address_2": update_order.address_2 if update_order.address_2 != None else "",
                            "city": update_order.city if update_order.city != None else "",
                            "state": update_order.state_code if update_order.state_code != None else "",
                            "postcode": update_order.postcode if update_order.postcode != None else "",
                            "country": update_order.country_code if update_order.country_code != None else "",
                            "email": update_order.email if update_order.email != None else "",
                            "phone": update_order.phone if update_order.phone != None else ""
                        },
                        "shipping": {
                            "first_name": update_order.shipping_first_name if update_order.shipping_first_name != None else "",
                            "last_name": update_order.shipping_last_name if update_order.shipping_last_name != None else "",
                            "address_1": update_order.shipping_address_1 if update_order.shipping_address_1 != None else "",
                            "address_2": update_order.shipping_address_2 if update_order.shipping_address_2 != None else "",
                            "city": update_order.shipping_city if update_order.shipping_city != None else "",
                            "state":update_order.shipping_state_code if update_order.shipping_state_code != None else "",
                            "postcode":update_order.shipping_postcode if update_order.shipping_postcode != None else "",
                            "country": update_order.shipping_country_code if update_order.shipping_country_code != None else "",
                            "phone": update_order.shipping_phone if update_order.shipping_phone != None else ""
                        }
                    }
                    wcapi.put(f'orders/{order_site_id}', data)
                    
                orderaft = {key : getattr(update_order,key) for key in orderpr}
                for key, value in orderpr.items():
                    aft_value = orderaft[key]
                    if key == 'status':
                        value = get_string_status(status_mapping, value)
                        aft_value = get_string_status(status_mapping, aft_value)
                    if aft_value != value:   
                        UserActionLog.objects.create(
                            user=request.user,
                            action='Update',
                            object_name = 'Order',
                            object_id = update_order.order_id,
                            details= f'{key} change from {value} to {aft_value}',
                        )
                cache.clear()
                return Response(serializer.data, status=200)
            else:
                return Response({'error': serializer.errors}, status=400)
        except Exception as e:
            return Response({'error': f'Server get error: {e}'}, status=500)

    elif request.method == 'DELETE':
        if not order.order_id.startswith('RS-'):
            wcapi.delete(f'orders/{order_site_id}', params={"force": True})
        
        UserActionLog.objects.create(
            user=request.user,
            action='Delete',
            object_name = 'Order',
            object_id = order.order_id,
        )
        order.delete()
        cache.clear()
        return Response({'success': f'Delete order {order_id} success'},status=200)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def read_an_order(request, order_id):
        if request.method != 'GET':
            return Response({'error': 'Method not allow'}, status=400)
        order = get_object_or_404(Order, order_id=order_id)
        
        serializer = OrderSerializer(order)
        return Response(serializer.data)

@swagger_auto_schema(
        method='POST',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'line_items': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'sku': openapi.Schema(type=openapi.TYPE_STRING),
                        },
                        required=['quantity', 'sku']  # Add required fields
                    )
                ),
            },
            required=['line_items']  # Add required fields
        ),
        responses={
            200: 'Success',
            400: 'Bad Request',
        },
    )
@api_view(['POST'])
def resend_order(request, order_id):
    try:
        order = get_object_or_404(Order, order_id=order_id)
        if order.status not in [3,4,5,6,7]:
            return Response({'error': f'Order {order_id} not allowed to resend'}, status=400)
        
        if order_id.startswith('RS-'):
            cur_i = int(order_id.split('-')[1])
            cur_order_id = order_id[5:]
            new_order_id = f'RS-{cur_i+1}-' + cur_order_id
        else:
            i = 1
            new_order_id = f'RS-{i}-' + order_id
            while Order.objects.filter(order_id=new_order_id).exists():
                i += 1
                new_order_id = f'RS-{i}-' + order_id
            
        # Create an order copy
        now = datetime.now()
        new_order = Order()
        new_order.__dict__.update(order.__dict__)
        new_order.order_id = new_order_id
        new_order.order_number = new_order_id
        new_order.status = 0
        new_order.date_created = now
        new_order.date_modified = now
        
        # Create resend item
        i = 1
        resend_item = []
        for item in request.data['line_items']:
            variation_int = Variation.objects.filter(sku = item['sku'], site_id = new_order.site_id.site_id).first()
            if variation_int == None:
                return Response({'error': f'Sku {item["sku"]} not exist in system'}, status=400)
            if item['sku'].startswith('tempsku'):
                return Response({'error': f'Not allowed to resend order with variantion not have SKU'}, status=400)
            price = Product_Site.objects.filter(site_id=variation_int.site_id.site_id, product_site_id=variation_int.product_site_id).first().price
            if price == None:
                price = 0
            
            resend_item.append(
                Order_Line_Item(
                    line_item_id=f'{new_order.order_id}-{i}',
                    order_id = new_order,
                    sku = variation_int.sku,
                    item_name = variation_int.product_site_name,
                    quantity = item['quantity'],
                    price= price,
                    subtotal_amount = round(price*item['quantity'], 2),
                    total_amount = round(price*item['quantity'],2),
                    status=0,
                    date_modified= now,
                    date_created= now,
                )
            )
            i+=1
            
        new_order.save()
        Order_Line_Item.objects.bulk_create(resend_item)
        
        UserActionLog.objects.create(
                user=request.user,
                action='Resend',
                object_name = 'Order',
                object_id = order_id,
                details = f'Resend order with new order id is {new_order.order_id}'
            )
        cache.clear()
        return Response({'success': f'Resend order {new_order.order_id} Successful'})
    except Exception as e:
        return Response({'error': f'Server get error: {e}'}, status=500)

@swagger_auto_schema(
        method='POST',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'order_id': openapi.Schema(type=openapi.TYPE_STRING),
            #     'line_items': openapi.Schema(
            #         type=openapi.TYPE_ARRAY,
            #         items=openapi.Schema(
            #             type=openapi.TYPE_OBJECT,
            #             properties={
            #                 'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
            #                 'sku': openapi.Schema(type=openapi.TYPE_STRING),
            #             },
            #             required=['quantity', 'sku']  # Add required fields
            #         )
            #     ),
            },
            required=['order_id']  # Add required fields
        ),
        responses={
            200: 'Success',
            400: 'Bad Request',
        },
    )
@api_view(['POST'])
def batch_resend_order(request):
    try:
        order_ids = request.data['order_id'].split(',')
        orders = Order.objects.filter(order_id__in=order_ids)
        for order in orders:
            order_id = order.order_id
            
            if order.status not in [3,4,5,6,7]:
                return Response({'error': f'Order {order.order_id} not allowed to resend'}, status=400)
            
            if order_id.startswith('RS-'):
                cur_i = int(order_id.split('-')[1])
                cur_order_id = order_id[5:]
                new_order_id = f'RS-{cur_i+1}-' + cur_order_id
            else:
                i = 1
                new_order_id = f'RS-{i}-' + order_id
                while Order.objects.filter(order_id=new_order_id).exists():
                    i += 1
                    new_order_id = f'RS-{i}-' + order_id
            # Create an order copy
            now = datetime.now()
            new_order = Order()
            new_order.__dict__.update(order.__dict__)
            new_order.order_id = new_order_id
            new_order.order_number = new_order_id
            new_order.status = 0
            new_order.date_created = now
            new_order.date_modified = now
            new_order.save()
            # Create resend item
            for j, item in enumerate(order.line_items.all(), start=1):
                new_line_item_id = f'{new_order.order_id}-{j}'
                new_item = Order_Line_Item(
                    order_id = new_order,
                    line_item_id=new_line_item_id,
                    status=0,  # Update status as needed
                    date_created=now,
                    date_modified=now,
                    sku = item.sku,
                    image_url =item.image_url,
                    item_name = item.item_name,
                    price = item.price,
                    subtotal_amount = item.subtotal_amount,
                    total_amount = item.total_amount,
                    quantity=item.quantity
                )
                new_item.save()
            # Order_Line_Item.objects.bulk_create(resend_item)
        
            UserActionLog.objects.create(
                    user=request.user,
                    action='Resend',
                    object_name = 'Order',
                    object_id = order_id,
                    details = f'Resend order with new order id is {new_order.order_id}'
                )
        cache.clear()   
        return Response({'success': f'Batch Resend order Successful'})
    except Exception as e:
        return Response({'error': f'Server get error: {e}'}, status=500)

@swagger_auto_schema(
        method='POST',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'amount': openapi.Schema(type=openapi.TYPE_INTEGER),
            }
        ),
        responses={
            200: 'Success',
            400: 'Bad Request',
        },
    )
@api_view(['POST'])
def refund_order(request, order_id):
    try:
        order = get_object_or_404(Order, order_id=order_id)
        amount = request.data.get('amount')
        if amount <=0 :
            return Response({'error': 'Refund amount must be greater than 0'}, status=400)
        
        if order.payment_status not in [1,2]:
            return Response({'error': 'Order is not paid or refunded and not allowed to refund'}, status=400)
        if amount != None:
            new_refund_amt = abs(round(order.refund_amount - amount, 2))
            if new_refund_amt > order.total_amount:
                return Response({'error': 'Amount refund is not allowed to be greater than total amount'}, status=400)
        if order.order_id.startswith('RS-'):
            if amount != None:
                order.refund_amount  = new_refund_amt
            else:
                order.refund_amount = -order.total_amount
                
            order.payment_status = 2
            order.save()
            cache.clear()
            result_refund = 'success'
        else:   
            result_refund = create_refund(order=order, amount=amount)
            
        if result_refund == 'success':
            UserActionLog.objects.create(
                user=request.user,
                action='Refund',
                object_name = 'Order',
                object_id = order.order_id,
                details = f'Refund entire order' if amount == None else f'Partially refund with amount {amount}' 
            )
            cache.clear()
            return Response({'success': f'Refund success'})
        else:
            return Response({'error': f'Refund order in Gateway get error {result_refund}'}, status=400)
    except Exception as e:
        return Response({'error': f'Server get error: {e}'}, status=500)

@api_view(['GET'])
def read_dispute(request, order_id):
    order = get_object_or_404(Order, order_id=order_id)
    if order.is_dispute != 1:
        return Response({'error': 'Order not have dispute'}, status=400)
    
    dispute_data = []
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
            dispute_data.append(response.json())
    
    elif order.payment_method == 'stripe':
        stripe.api_key = Key_API.objects.get(name=order.payment_method_title).authentication['secret']
        starting_after = None
        if order.transaction_id.startswith('ch_'):
            while True:
                response = stripe.Dispute.list(limit=100,charge=order.transaction_id,starting_after=starting_after)
                for dispute in response['data']:
                    dispute_data.append(dispute)
                starting_after = response['data'][-1]['id']
                if response['has_more'] == False:
                    break
        elif order.transaction_id.startswith('pi_'):
            while True:
                response = stripe.Dispute.list(limit=100,payment_intent=order.transaction_id,starting_after=starting_after)
                for dispute in response['data']:
                    dispute_data.append(dispute)
                starting_after = response['data'][-1]['id']
                if response['has_more'] == False:
                    break
            
    return Response({'results': dispute_data})

              
# -------------ITEM---------------
@swagger_auto_schema(
        method='GET',
        manual_parameters=[
            openapi.Parameter('start_date', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Start date (ISO format: YYYY-MM-DD)'),
            openapi.Parameter('end_date', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='End date (ISO format: YYYY-MM-DD)'),
            openapi.Parameter('status', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Line item status (comma-separated list)'),
            openapi.Parameter('sku', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='SKU (comma-separated list)'),
            openapi.Parameter('order_number', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Search by order number'),
            openapi.Parameter('export', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='True to export'),
            openapi.Parameter('export_item_id', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='id of item to export'),
        ],
        responses={200: openapi.Response('Successful Response', openapi.Schema(type=openapi.TYPE_OBJECT))},
    )
@swagger_auto_schema(
        method='POST',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'order_id': openapi.Schema(type=openapi.TYPE_STRING),
                'sku': openapi.Schema(type=openapi.TYPE_STRING),
                'quantity': openapi.Schema(type=openapi.TYPE_INTEGER)
            },
            required=['order_id','sku','quantity']  # Add required fields
        ),
        responses={
            200: openapi.Response('Created', OrderLineItemSerializer),
            400: 'Bad Request',
        },
    )
@api_view(['GET','POST'])
def read_or_create_items(request):
    if request.method == 'GET':
        # Get parameters from the query string
        page = request.GET.get('page', 1)
        per_page = request.GET.get('per_page', 10)
        order_by = request.GET.get('order_by', 'date_created')
        order_type = request.GET.get('order_type', 'desc')
        status_filter = request.GET.get('status')
        sku_filter = request.GET.get('sku')
        order_number_filter = request.GET.get('order_numbers')
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        export = request.GET.get('export')
        export_item_id = request.GET.get('export_item_id') 

        
        # Validate and sanitize parameters
        try:
            page = int(page)
            per_page = int(per_page)
        except ValueError:
            return Response({'error': 'Invalid page or per_page value'}, status=400)
    
        if order_type == 'asc':
            order_by_field = order_by
        elif order_type == 'desc':
            order_by_field = '-' + order_by
        else:
            return Response({'error': 'Invalid order_type value'}, status=400)
        
            
        queryset = Order_Line_Item.objects.all().order_by(order_by_field)
        
        if start_date_str:
            start_date = datetime.fromisoformat(start_date_str)
            queryset = queryset.filter(date_created__gte = start_date)

        if end_date_str:
            end_date = datetime.fromisoformat(end_date_str) + timedelta(days=1)
            queryset = queryset.filter(date_created__lt = end_date)
        
        if status_filter:
            status_filter = status_filter.split(",")
            status_filter = [int(part) for part in status_filter]
            queryset = queryset.filter(status__in = status_filter)
            
        if sku_filter:
            queryset = queryset.filter(sku__sku__icontains = sku_filter)
        
        if order_number_filter:
            queryset = queryset.filter(order_id__order_number__icontains = order_number_filter)
        
        if export == 'true':
            # Assuming that the necessary related fields are prefetched or selected in the queryset
            queryset = queryset.select_related(
                'order_id__site_id',
                'order_id',
                'batch_id',
                'sku',
                'shippings'
            )

            if export_item_id:
                export_item_id = export_item_id.split(",") 
                queryset = queryset.filter(line_item_id__in=export_item_id)

            # Create a DataFrame directly from the queryset
            df = pd.DataFrame.from_records(
                    queryset.values(
                        'order_id__site_id__site_id',
                        'order_id__order_number',
                        'batch_id__batch_id',
                        'line_item_id',
                        'batch_id__supplier',
                        'item_name',
                        'price',
                        'quantity',
                        'subtotal_amount',
                        'total_amount',
                        'sku__sku',
                        'sku__attributes_id',
                        'shippings__tracking_number',
                        'status',
                        'tag'
                    )
                )
            
            reversed_item_status = {v: k for k, v in item_status.items()}
            reversed_item_tag = {v: k for k, v in item_tag.items()} 
        
            df['status'] = df['status'].apply(lambda x: reversed_item_status.get(x))
            df['tag'] = df['tag'].apply(lambda x: reversed_item_tag.get(x))
            
            column_mapping = {
                'order_id__site_id__site_id': 'Site_ID',
                'order_id__order_number': 'Order_Number',
                'batch_id__batch_id': 'Batch_ID',
                'line_item_id': 'Line_Item_ID',
                'batch_id__supplier': 'Supplier',
                'item_name': 'Item_Name',
                'price': 'Item_Cost',
                'quantity': 'Quantity',
                'subtotal_amount': 'Subtotal_Amount',
                'total_amount': 'Total_Amount',
                'sku__sku': 'SKU',
                'sku__attributes_id': 'Attributes',
                'shippings__tracking_number': 'Tracking Number',
                'status': 'Status',
                'tag': 'Tag',
            }
            df.rename(columns=column_mapping, inplace=True)
            
            return Response({'csv': generate_export_link(df, 'export_item')})          
                    
        
        if per_page == -1:    
            serializer = OrderLineItemSerializer(queryset, many=True)
            data = {
                'total_rows': len(queryset),
                'results': serializer.data
            }
        
        else:
            paginator = Paginator(queryset, per_page)
            page_obj = paginator.get_page(page)
            serializer = OrderLineItemSerializer(page_obj, many=True)
            
            data = {
                    'page': page,
                    'per_page': per_page,
                    'total_pages': paginator.num_pages,
                    'total_rows': paginator.count,
                    'results': serializer.data
                }
            
        return Response(data)

    if request.method == 'POST':
        create_data = request.data
        order = get_object_or_404(Order, order_id=create_data['order_id'])
        order_id = order.order_id
        site = order.site_id
        site_id = site.site_id
        variation = Variation.objects.filter(site_id=site_id,sku=create_data['sku']).first()
        if order.status not in  [0, 8, 9]:
            return Response({'error': 'Only need approved, cs-hold, on hold order can add product'}, status=400)
        if create_data['sku'].startswith('tempsku'):
            return Response({'error': 'Not allow to add product not have sku (have tempsku)'}, status=400)
        if variation == None:
            return Response({'error': f'Site {site_id} not have sku {create_data["sku"]}'}, status=400)
        try:
            
            if not order_id.startswith('RS-'):
                order_site_id = int(order_id.split('-')[-1])
                wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
                data = {
                    'id': order_site_id,
                    'line_items': [
                        {
                            'quantity': create_data['quantity'],
                            'product_id': int(variation.product_site_id),
                            'meta_data': variation.meta_data
                        }
                    ]
                }
                
                response = wcapi.put(f'orders/{order_site_id}', data)
                if response.status_code==200:
                    update_order=response.json()
                    load_order(update_order, site, wcapi)
                else:
                    return Response({'error': f'Failed to add item to in WooCommerce: {response.json()["message"]}'}, status=400)
            else:
                i = 1
                new_item_id = f'{order_id}-{i}'
                
                while Order_Line_Item.objects.filter(line_item_id=new_item_id).exists():
                    i += 1
                    new_item_id = f'{order_id}-{i}'
                price = Product_Site.objects.filter(site_id=site_id, product_site_id=variation.product_site_id).first().price
                if price == None:
                    price = 0
                now = datetime.now()
                new_order_line_item = Order_Line_Item(
                    order_id=order, 
                    line_item_id=new_item_id, 
                    quantity=create_data['quantity'],
                    sku = variation.sku,
                    item_name = variation.product_site_name,
                    price= price,
                    subtotal_amount = round(price*create_data['quantity'], 2),
                    total_amount = round(price*create_data['quantity'],2),
                    status=0,
                    date_modified= now,
                    date_created= now,
                )
                new_order_line_item.save()
                
            UserActionLog.objects.create(
                user=request.user,
                action='Add Item',
                object_name = 'Order',
                object_id = order_id,
                details= f'Add item with SKU {create_data["sku"]}',
                )
            cache.clear()
            return Response({'success': 'add item succesful'}, status=200)
        except Exception as e:
            return Response({'error': f'Server get error: {e}'}, status=500)

@swagger_auto_schema(
        method='POST',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'order_id': openapi.Schema(type=openapi.TYPE_STRING),
                'sku': openapi.Schema(type=openapi.TYPE_STRING),
                'quantity': openapi.Schema(type=openapi.TYPE_INTEGER)
            },
            required=['order_id','sku','quantity']  # Add required fields
        ),
        responses={
            200: openapi.Response('Created', OrderLineItemSerializer),
            400: 'Bad Request',
        },
    )
@api_view(['POST'])
def batch_create_item(request):
    create_data = request.data
    order_ids = create_data['order_id'].split(',')
    orders = Order.objects.filter(order_id__in = order_ids)
    error_orders = orders.exclude(status=0)
    if error_orders.exists():
        return Response({'error': f'Order with IDs {list(error_orders.values_list("order_id", flat=True))} is not allowed to add product because status is not need approved'}, status=400)
    unique_site_id = list(orders.values_list("site_id__site_id", flat=True).distinct())
    if len(unique_site_id) > 1:
        return Response({'error': f'Can only add product with orders in a site'}, status=400)
    if create_data['sku'].startswith('tempsku'):
        return Response({'error': 'Not allow to add product not have sku'}, status=400)
    site = Site.objects.get(site_id=unique_site_id[0])
    site_id = site.site_id
    variation = Variation.objects.filter(site_id=site_id,sku=create_data['sku']).first()
    if variation == None:
        return Response({'error': f'Site {site_id} not have sku {create_data["sku"]}'}, status=400)
    for order in orders:
        order_id = order.order_id
        try:
            if not order_id.startswith('RS-'):
                order_site_id = int(order_id.split('-')[-1])
                wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
                data = {
                    'id': order_site_id,
                    'line_items': [
                        {
                            'quantity': create_data['quantity'],
                            'product_id': int(variation.product_site_id),
                            'meta_data': variation.meta_data
                            # 'subtotal': str(create_data['subtotal_amount']),
                            # 'total': str(create_data['total_amount'])
                        }
                    ]
                }
                
                response = wcapi.put(f'orders/{order_site_id}', data)
                if response.status_code==200:
                    update_order=response.json()
                    load_order(update_order, site, wcapi)
                else:
                    return Response({'error': f'Failed to add item to in WooCommerce: {response.json()["message"]}'}, status=400)
            else:
                i = 1
                new_item_id = f'{order_id}-{i}'
                
                while Order_Line_Item.objects.filter(line_item_id=new_item_id).exists():
                    i += 1
                    new_item_id = f'{order_id}-{i}'
                price = Product_Site.objects.filter(site_id=site_id, product_site_id=variation.product_site_id).first().price
                if price == None:
                    price = 0
                now = datetime.now()
                new_order_line_item = Order_Line_Item(
                    order_id=order, 
                    line_item_id=new_item_id, 
                    quantity=create_data['quantity'],
                    sku = variation.sku,
                    item_name = variation.product_site_name,
                    price= price,
                    subtotal_amount = round(price*create_data['quantity'], 2),
                    total_amount = round(price*create_data['quantity'],2),
                    status=0,
                    date_modified= now,
                    date_created= now,
                )
                new_order_line_item.save()
                
            UserActionLog.objects.create(
                user=request.user,
                action='Add Item',
                object_name = 'Order',
                object_id = order_id,
                details= f'Add item with SKU {create_data["sku"]}',
                )
        except Exception as e:
            return Response({'error': f'Server get error: {e}'}, status=500)    
    
    cache.clear()
    return Response({'success': 'add item succesful'}, status=200)
   
@swagger_auto_schema(
        method='PUT',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'status': openapi.Schema(type=openapi.TYPE_INTEGER),
                'sku': openapi.Schema(type=openapi.TYPE_STRING),
                'quantity': openapi.Schema(type=openapi.TYPE_INTEGER),
                'subtotal_amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                'total_amount': openapi.Schema(type=openapi.TYPE_NUMBER)
            }
        ),
        responses={
            200: openapi.Response('Successful Response', OrderLineItemSerializer),
            400: 'Bad Request',
            404: 'Not Found',
        },
    )
@swagger_auto_schema(
        methods=['GET', 'DELETE'],
        manual_parameters=[
            openapi.Parameter('line_item_id', openapi.IN_PATH, description="Line Item ID", type=openapi.TYPE_STRING),
        ],
        responses={
            200: openapi.Response('Successful Response', OrderLineItemSerializer),
            204: 'No Content',
            400: 'Bad Request',
            404: 'Not Found',
        },
    )
@api_view(['GET','PUT','DELETE'])
def rud_an_item(request, line_item_id):
    line_item = get_object_or_404(Order_Line_Item, line_item_id=line_item_id)
    line_item_site_id = line_item.line_item_id.split('-')[1]
    
    order = line_item.order_id
    site = order.site_id
    order_site_id = order.order_id.split('-')[-1]
    wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
    
    if request.method == 'GET':
        serializer = OrderLineItemSerializer(line_item)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        line_itempr = { key : getattr(line_item,key) for key in request.data.keys()}
        
        serializer = OrderLineItemSerializer(line_item, data=request.data, partial=True)
        if serializer.is_valid():
            status_update = request.data.get('status')
            quantity_update = request.data.get('quantity')
            sku_update = request.data.get('sku')
            if quantity_update == 0:
                return Response({'error': 'Not allowed to update quantity to 0'}, status=400)          
            update_item = serializer.save()
            
            if status_update:
                update_order_status(order)

            if not order.order_id.startswith('RS-'):
                if quantity_update: 
                    data = {
                        "line_items": [
                            {
                                "id" : int(line_item_site_id),
                                "quantity": update_item.quantity
                            }
                        ]
                    }
                    wcapi.put(f'orders/{order_site_id}',data)
                    
                if sku_update:
                    if sku_update.startswith('tempsku'):
                        return Response({'error': 'Not Allowed to update with variation not have SKU'}, error=400)    
                    variation = Variation.objects.filter(site_id=site.site_id, sku=sku_update).first()
                    meta_data = variation.meta_data
                    meta_ids = line_item.meta_data_id
                    if meta_data == None:
                        meta_data = []
                    if meta_ids == None:
                        meta_ids = []
                    index = 0
                    for i in meta_data:
                        if index == len(meta_ids):
                            continue
                        i['id'] = meta_ids[index]
                        index+=1
                        
                    if  len(meta_ids) > len(meta_data):
                        temp = meta_ids[len(meta_data):]
                        for i in temp:
                            meta_data.append({"id" : i, "key" : "",  "value" : "" })
                    
                    data = {
                        "line_items": [
                            {
                                "id" : int(line_item_site_id),
                                "product_id": int(variation.product_site_id),
                                "meta_data": meta_data,
                            }
                        ]
                    }
                    wcapi.put(f'orders/{order_site_id}',data)
            
            line_aft = { key : getattr(line_item,key) for key in line_itempr}
            for key, value in line_itempr.items():
                if line_aft[key] != value:
                    UserActionLog.objects.create(
                        user=request.user,
                        action='Update Item',
                        object_name = 'Order',
                        object_id = order.order_id,
                        details= f'Change {key} of item {line_item_id} from {value} to ' + line_aft[key],
                    )
            cache.clear()  
            return Response(serializer.data, status=http_status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=http_status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        if not order.order_id.startswith('RS-'):
            data = {
                    "line_items": [
                        {
                            "id" : int(line_item_site_id),
                            "quantity": 0
                        }
                    ]
                }    
            wcapi.put(f'orders/{order_site_id}',data)
        UserActionLog.objects.create(
            user=request.user,
            action='Delete Item',
            object_name = 'Order',
            object_id = order.order_id,
            details= f'Delete item with sku {line_item.sku.sku}'
        )
        line_item.delete()
        cache.clear()
        return Response(status=200)


# ----------------BATCH UPDATE---------------
@swagger_auto_schema(
        method='PUT',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'order_id': openapi.Schema(type=openapi.TYPE_STRING),
                'status': openapi.Schema(type=openapi.TYPE_INTEGER),
            },
            required=['order_id']
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                }
            ),
            404: 'Order not found',
        }
    )
@swagger_auto_schema(
        method='DELETE',
        manual_parameters=[
            openapi.Parameter('order_id', openapi.IN_QUERY, description="Order id to delete (SEM-1,SEM-2...)", type=openapi.TYPE_STRING),
        ],
        responses={
            2001: 'Success',
            204: 'No Content',
            400: 'Bad Request',
            404: 'Not Found',
        },
    )
@api_view(['PUT','DELETE'])
def batch_update_orders(request):
    if request.method == 'PUT':
        order_ids = request.data.get('order_id').split(',')
        status_update = request.data.get('status')
        
        orders = Order.objects.filter(order_id__in = order_ids)
        line_items = Order_Line_Item.objects.filter(order_id__in=order_ids)
        
        order_check = orders.filter(status = 6)
        if order_check.exists():
            order_check = list(order_check.values_list('order_id', flat=True))
            return Response({'error': f'Order ID {order_check} is completed and not allowed to change status'}, status=400)        
        if status_update not in [0,1,7,8,9]:
            return Response({'error': f'Not allowed to change status'}, status=400)
        else:
            order_check = orders.exclude(status=0)
            if status_update in [1,8,9] and order_check.exists():
                order_check = list(order_check.values_list('order_id', flat=True))
                return Response({'error': f'Order ID {order_check} is not need approved and not allowed to change status'}, status=400)
            if status_update == 1: 
                if line_items.filter(sku__sku__istartswith='tempsku').exists():
                    order_check = list(line_items.filter(sku__sku__istartswith='tempsku').values_list('order_id', flat=True).distinct())
                    return Response({'error': f'Order ID {order_check} have item not have sku and not allowed to change status'}, status=400)
                order_check = order_check.filter(payment_status=0) 
                if order_check.exists():
                    order_check = list(order_check.values_list('order_id', flat=True))
                    return Response({'error': f'Order ID {order_check} is not paid not allowed to approved'}, status=400)
                    
        action_log = []
        for order in orders:
            if order.status != status_update:
                action_log.append(
                    UserActionLog(
                        user=request.user,
                        action='Update',
                        object_name = 'Order',
                        object_id = order.order_id,
                        details= f'status change from {get_string_status(status_mapping, order.status)} to {get_string_status(status_mapping, status_update)}'
                    )
                )
        UserActionLog.objects.bulk_create(action_log)
        orders.update(status=status_update)
        update_item_status(line_items)    
        
        if status_update==6:
            batch_ids = list(line_items.values_list('batch_id', flat = True).distinct())
            batchs = Batch.objects.filter(batch_id__in = batch_ids)
            line_items.update(batch_id=None)
            for batch in batchs:
                if batch.number_items == 0:
                    batch.delete()
            
        sync_to_woo(orders, 'update')
        cache.clear()
        return Response({'success': 'Orders updated successfully'}, status=200)
    
    elif request.method == 'DELETE':
        order_id_delete = request.GET.get('order_id').split(",")
        order_delete = Order.objects.filter(order_id__in = order_id_delete)
        
        sync_to_woo(order_delete, 'delete')
        order_delete.delete()
         
        cache.clear()
        return Response({'success': 'Orders delete successfully'}, status=200)

@swagger_auto_schema(
        method='PUT',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'line_item_id': openapi.Schema(type=openapi.TYPE_STRING),
                'status': openapi.Schema(type=openapi.TYPE_INTEGER),
                'tag': openapi.Schema(type=openapi.TYPE_INTEGER),
            },
            required=['line_item_id']
        ),
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                }
            ),
            404: 'Item not found',
        }
    ) 
@swagger_auto_schema(
        method='DELETE',
        manual_parameters=[
            openapi.Parameter('line_item_id', openapi.IN_QUERY, description="Line item id to delete (SEM-12323,SEM-22323...)", type=openapi.TYPE_STRING),
        ],
        responses={
            200: 'Success',
            204: 'No Content',
            400: 'Bad Request',
            404: 'Not Found',
        },
    )
@api_view(['PUT','DELETE'])
def batch_update_items(request): 
    if request.method == 'PUT':
        item_ids = request.data.get('line_item_id').split(',')
        status_update = request.data.get('status')
        tag_update = request.data.get('tag')
        
        line_items = Order_Line_Item.objects.filter(line_item_id__in=item_ids)
        if status_update:
            line_items.update(status=status_update)
            order_ids = line_items.values_list('order_id', flat=True).distinct()
            orders = Order.objects.filter(order_id__in=order_ids)
            update_order_status(orders)
            sync_to_woo(orders, 'update')
        if tag_update:
            line_items.update(tag=status_update)
        
        #  UserActionLog.objects.create(
        #     user=request.user,
        #     action='Batch Update Item',
        #     details= f'Batch Update Item {str_item}',
        # )
        cache.clear()
        return Response({'success': 'Update Items Successful'}, status=200)
                        
    if request.method == 'DELETE':
        item_ids_delete = request.GET.get('line_item_id')
        item_ids_delete = item_ids_delete.split(",")
        
        for line_item_id in item_ids_delete:  
            item_instance = Order_Line_Item.objects.get(line_item_id=line_item_id)
            line_item_site_id = item_instance.line_item_id.split('-')[1]
            
            # Get order instance
            order_instance = item_instance.order_id
            site_id = order_instance.site_id.site_id
            site = order_instance.site_id
            order_site_id = order_instance.order_id.split('-')[-1]
            
            # Update on Woo
            data = {
                "line_items": [
                    {
                        "id" : int(line_item_site_id),
                        "quantity": 0
                    }
                ]
            }
            wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
            wcapi.put(f'orders/{order_site_id}',data)
            item_instance.delete()
        #  UserActionLog.objects.create(
        #     user=request.user,
        #     action='Batch Delete Item',
        #     details= f'Batch Update Item {item_ids_delete}',
        # )  
        cache.clear()
        return Response({'success': 'Delete sucessful'}, status = 200)      
   

# -------------BATCH--------------
@swagger_auto_schema(
        methods=['GET'],
        manual_parameters=[
            openapi.Parameter('status', in_=openapi.IN_QUERY, description='Filter batches by status', type=openapi.TYPE_STRING),
            openapi.Parameter('export', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='true to export many batch, no fill to export all'),
            openapi.Parameter('export_batch_id', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='id of batchs to export'),
            openapi.Parameter('order_by', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='field to sort'),
            openapi.Parameter('order_type', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='type sort asc or desc'),
            openapi.Parameter('page', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='page'),
            openapi.Parameter('per_page', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='records per page'),
            openapi.Parameter('export_sample_template', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='true to get sample template khi up tracking'),
        ],
        responses={
            200: 'List of batches retrieved successfully',
            404: 'Not Found. Check the error message for details.',
            500: 'Internal server error. Check the error message for details.',
        }
    )
@swagger_auto_schema(
        methods=['POST'],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'id': openapi.Schema(type=openapi.TYPE_STRING, description='order_id or item id to create comma separated string (KATC-1,KATC-2,...)'),
                'change_batch': openapi.Schema(type=openapi.TYPE_STRING, description='true to change batch'),
                'type_create' : openapi.Schema(type=openapi.TYPE_STRING,description='order to input order id, item to input line item id'),
                'supplier' : openapi.Schema(type=openapi.TYPE_STRING,description='supplier of batch')
            },
            required=['line_item_id']
        ),
        responses={
            201: 'Batches created successfully',
            400: 'Bad Request. Check the error message for details.',
            404: 'Not Found. Check the error message for details.',
            500: 'Internal server error. Check the error message for details.',
        }
    )
@api_view(['GET','POST'])
def read_or_create_batches(request):
    if request.method == 'GET':
        status_filter = request.GET.get('status')
        export = request.GET.get('export')
        export_batch_id = request.GET.get('export_batch_id')
        page = request.GET.get('page', 1)
        per_page = request.GET.get('per_page', 10)
        order_by = request.GET.get('order_by', 'date_modified')
        order_type = request.GET.get('order_type', 'desc')
        export_sample_template = request.GET.get('export_sample_template', 'false')
        
        if export_sample_template == 'true':
            df_sample = pd.DataFrame(columns=['Order ID', 'Order Number','Tracking Number', 'Courier Code'])
            return Response({'csv': generate_export_link(df_sample, 'sample_template_batch')})

            
        if order_type == 'asc':
            order_by_field = order_by
        elif order_type == 'desc':
            order_by_field = '-' + order_by
        
        queryset = Batch.objects.all().order_by(order_by_field)
        if status_filter:
            status_filter = status_filter.split(',')
            queryset = queryset.filter(status__in = status_filter)
        
        if export == 'true':
            if export_batch_id:
                export_batch_id = export_batch_id.split(',')
                queryset = queryset.filter(batch_id__in=export_batch_id)

            queryset = queryset.select_related('line_items', 'line_items__sku', 'line_items__order_id')
            data = queryset.values(
                'line_items__order_id__order_id',
                'line_items__order_id__order_number',
                'line_items__line_item_id',
                'batch_id',
                'line_items__quantity',
                'line_items__item_name',
                'line_items__sku__attributes_id',
                'supplier',
                'line_items__shippings__tracking_number'
            )
            df = pd.DataFrame.from_records(data)

            column_mapping = {
                'line_items__order_id__order_id': 'Order ID',
                'line_items__order_id__order_number': 'Order Number',
                'line_items__line_item_id': 'Line Item ID',
                'batch_id': 'Batch ID',
                'line_items__quantity': 'Quantity',
                'line_items__item_name': 'Product Name',
                'line_items__sku__attributes_id': 'Attributes',
                'supplier': 'Supplier',
                'line_items__shippings__tracking_number': 'Tracking Number',
            }
            df.rename(columns=column_mapping, inplace=True)

            return Response({'csv': generate_export_link(df, 'export_batchs')})
    
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        serializer = BatchSerializer(page_obj, many=True)
        
        return Response({
            'page': page,
            'per_page': per_page,
            'total_pages': paginator.num_pages,
            'total_rows': paginator.count,
            'results': serializer.data
        })

    elif request.method == 'POST':
        try:
            change_batch = request.data.get('change_batch', False)
            type_create = request.data.get('type_create', 'order')
            supplier = request.data.get('supplier')
            ids = request.data.get('id').split(',')
            
            if not supplier:
                return Response({'error': "Supplier is Required"}, status=400)
            
            if type_create == 'order':
                line_items = Order_Line_Item.objects.filter(order_id__order_id__in=ids)
            elif  type_create == 'item':
                line_items = Order_Line_Item.objects.filter(line_item_id__in=ids)
                
            item_not_have_sku = line_items.filter(sku__sku__startswith='tempsku_').values_list('order_id__order_id', flat=True).distinct()
            item_not_approved = line_items.exclude(status__in=[1,2,3]).values_list('order_id__order_id', flat=True).distinct()
            item_have_batch = line_items.filter(batch_id__isnull=False).values_list('order_id__order_id', flat=True).distinct()

            if item_not_have_sku:
                return Response({'error': f'Order with IDS {list(item_not_have_sku)} do not have SKU and is not allowed to create batch'}, status=400)
            if item_not_approved:
                return Response({'error': f'Order with IDS {list(item_not_approved)} do not have status Approved and is not allowed to create batch'}, status=400)
            if change_batch != 'true' and item_have_batch:
                return Response({'error': f'Order with IDS {list(item_have_batch)} is assigned to another batchs and is not allowed to create batch'}, status=400)
                 
            # Create the batch
            batch = Batch.objects.create(
                supplier=supplier, 
                date_created = datetime.now(),
                # created_by = request.user
            )

            # Assign the batch to all the items
            line_items.update(batch_id=batch, status=2) 
            order_ids = line_items.values_list('order_id', flat=True).distinct()
            orders = Order.objects.filter(order_id__in=order_ids)
            update_order_status(orders)
            
            UserActionLog.objects.create(
                user=request.user,
                action='Create',
                object_name = 'Batch',
                object_id = batch.batch_id,
            )
            UserActionLog.objects.bulk_create([
                UserActionLog(
                        user=request.user,
                        action='Add Batch',
                        object_name = 'Order',
                        object_id = order.order_id,
                        details= f'add to batch {batch.batch_id}'
                )
                for order in orders
            ])
                        
            cache.clear()    
            return Response({'success': f'Batch {batch.batch_id} create successful'}, status=200)
        
        except Exception as e:
            return Response({'error': f'Error creating batches: {str(e)}'}, status=500)
        
@swagger_auto_schema(
        method='GET',
        manual_parameters=[
            openapi.Parameter('export', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='true to export'),
            openapi.Parameter('export_field_order', openapi.IN_QUERY, description="field of order to export (order_id,order_number,...) if not input will return all field", type=openapi.TYPE_STRING),
            openapi.Parameter('export_field_item', openapi.IN_QUERY, description="item_name,batch_id,supplier,quantity,subtotal_amount,total_amount,sku,tag,status  if not input will return all field", type=openapi.TYPE_STRING),
            openapi.Parameter('order_of_fields', openapi.IN_QUERY, description="order of fields to exports", type=openapi.TYPE_STRING),
        ],
        responses={200: openapi.Response('Successful Response', openapi.Schema(type=openapi.TYPE_OBJECT))},
    )
@swagger_auto_schema(
        methods=['PUT'],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'action': openapi.Schema(type=openapi.TYPE_STRING, description='delete to remove item, add to add item'),
                'type_update': openapi.Schema(type=openapi.TYPE_STRING, description='order to input order id, item to input line item id'),
                'id': openapi.Schema(type=openapi.TYPE_STRING, description='order_id or item id to update comma separated string (KATC-1,KATC-2,...)'),
                'change_batch': openapi.Schema(type=openapi.TYPE_STRING, description='true to change batch'),
                'supplier': openapi.Schema(type=openapi.TYPE_STRING, description='supplier to change with action = edit'),
            }
        ),
        responses={200: openapi.Response('Successful Response', openapi.Schema(type=openapi.TYPE_OBJECT))},
    )
@api_view(['GET', 'PUT', 'DELETE'])
def rud_a_batch(request, batch_id):
    batch = get_object_or_404(Batch, batch_id=batch_id)
    line_items = batch.line_items.all()
    order_ids = list(line_items.values_list('order_id__order_id', flat=True).distinct())
    orders = Order.objects.filter(order_id__in=order_ids)
    
    if request.method == 'GET':
        export = request.GET.get('export', 'false')
        
        if export == 'true':
            export_field_order_request = request.GET.get('export_field_order')
            export_field_item_request = request.GET.get('export_field_item')
            order_of_fields = request.GET.get('order_of_fields')
            
            exclude_order_field = ['line_items', 'shipping_name', 'number_items']
            if export_field_order_request:
                export_field_order_request = export_field_order_request.split(',')
                export_field_order = [f'order_id__{field}' for field in export_field_order_request  if field not in exclude_order_field]
            else:
                export_field_order = []
            export_field_order.extend(['order_id__order_id', 'order_id__order_number', 'order_id__first_name', 'order_id__last_name']) 
            
            
            exclude_item_field = ['order_id', 'date_created', 'date_modified', 'shippings', 'meta_data_id','order_id']
            if export_field_item_request:
                export_field_item_request = export_field_item_request.split(',')
                export_field_item = [field for field in export_field_item_request  if field not in exclude_item_field]
            else:
                export_field_item = []

            export_field_item.extend(['shippings__tracking_number', 'shippings__courier_code', 'shippings__valid']) 
            
            df = pd.DataFrame.from_records(line_items.values(*export_field_order, *export_field_item))
            df['shippings__tracking_number'] = df.apply(lambda row: row['shippings__tracking_number'] if row['shippings__valid'] == 1 else None, axis=1)
            df = df.drop(columns=['shippings__valid'])
            
            df['order_id__shipping_name'] = df['order_id__first_name'] + ' ' + df['order_id__last_name']
            drop_col = []
            
            for column in ['first_name', 'last_name', 'shipping_name']:
                if export_field_order_request:
                    if column not in export_field_order_request:
                        drop_col.append('order_id__'+column)
                else:
                    drop_col.append('order_id__'+column)
            df =df.drop(columns=drop_col).drop_duplicates(subset=['order_id__order_id', 'shippings__tracking_number'])
            
            if order_of_fields:
                order_of_fields = [
                    'order_id__' + field if field in export_field_order_request 
                    else field if field in export_field_item_request 
                    else field
                    for field in order_of_fields.split(',')
                ]
                # order_of_fields = ['shippings__tracking_number','shippings__courier_code'] + order_of_fields
                df = df[order_of_fields]
            
             # Change status from int to string
            if 'order_id__status' in export_field_order:
                df['order_id__status'] = df['order_id__status'].apply(lambda x: get_string_status(status_mapping, x))
            if 'order_id__payment_status' in export_field_order:
                df['order_id__payment_status'] = df['order_id__payment_status'].apply(lambda x: get_string_status(payment_status,x))
            # if 'status' in export_field_item:
            #     df['status'] = df['status'].apply(lambda x: get_string_status(item_status,x))
            if 'tag' in export_field_item:
                df['tag'] = df['tag'].apply(lambda x: get_string_status(item_tag,x))
            if 'order_id__coupon_code' in export_field_order:
                df['order_id__coupon_code'] = df['order_id__coupon_code'].apply(lambda x: np.nan if not x else x)
            
            column_mapping = {
                'order_id__order_id': 'Order ID',
                'order_id__order_number': 'Order Number',
                'line_item_id': 'Line Item ID',
                'batch_id': 'Batch ID',
                'shippings__tracking_number': 'Tracking Number',
                'shippings__courier_code': 'Courier Code',
                'order_id__order_id': 'Order ID',
                'order_id__site_id': 'Site ID',
                'order_id__transaction_id': 'Transaction ID',
                'order_id__status': 'Status',
                'order_id__fulfill_status': 'Fulfill Status',
                'order_id__payment_status': 'Payment Status',
                'order_id__first_name': 'First Name',
                'order_id__last_name': 'Last Name',
                'order_id__shipping_name': 'Shipping Name',
                'order_id__email': 'Email',
                'order_id__phone': 'Phone',
                'order_id__address_1': 'Address 1',
                'order_id__address_2': 'Address 2',
                'order_id__city': 'City',
                'order_id__state_code': 'State Code',
                'order_id__postcode': 'Postcode',
                'order_id__country_code': 'Country Code',
                'order_id__currency': 'Currency',
                'order_id__shipping_first_name': 'Shipping First Name',
                'order_id__shipping_last_name': 'Shipping Last Name',
                'order_id__shipping_phone': 'Shipping Phone',
                'order_id__shipping_address_1': 'Shipping Address 1',
                'order_id__shipping_address_2': 'Shipping Address 2',
                'order_id__shipping_city': 'Shipping City',
                'order_id__shipping_state_code': 'Shipping State Code',
                'order_id__shipping_postcode': 'Shipping Postcode',
                'order_id__shipping_country_code': 'Shipping Country Code',
                'order_id__payment_method': 'Payment Method',
                'order_id__payment_method_title': 'Payment Method Title',
                'order_id__discount_amount': 'Discount Amount',
                'order_id__coupon_code': 'Coupon Code',
                'order_id__refund_amount': 'Refund Amount',
                'order_id__shipping_amount': 'Shipping Amount',
                'order_id__total_amount': 'Total Amount',
                'order_id__date_paid': 'Date Paid',
                'order_id__date_created': 'Date Created',
                'order_id__date_modified': 'Date Modified',
                'order_id__date_completed': 'Date Completed',
                'item_name': 'Line Item Name',
                'sku__attributes_id': 'Attributes',
                'sku': 'Line Item SKU',
                'quantity': 'Line Item Quantity',
                'subtotal_amount': 'Line Item Subtotal Amount',
                'total_amount': 'Line Item Total Amount',
                'price': 'Line Item Price',
                'status': 'Line Item Status',
                'tag': 'Line Item Tag',
            }
            df.rename(columns=column_mapping, inplace=True)
            
            return Response({'csv': generate_export_link(df, f'export_batch_{batch.batch_id}')})
        
        res_data = BatchSerializer(batch).data
        res_data['line_items'] = OrderLineItemSerializer(line_items, many=True).data
        return Response(res_data)
    
    if request.method == 'PUT':
        try:
            if batch.status == 2:
                return Response({'error': 'Batch is completed and not allowed to update'}, status =400)
            
            action = request.data.get('action')
            
            if action in ['add', 'delete']:
                change_batch = request.data.get('change_batch', 'false')
                ids = request.data.get('id','').split(',')
                type_update = request.data.get('type_update', 'order')
                
                if type_update == 'item':
                    update_items = Order_Line_Item.objects.filter(line_item_id__in = ids)
                elif type_update == 'order':
                    update_items = Order_Line_Item.objects.filter(order_id__order_id__in = ids)
            
            if action == 'edit':
                batch.supplier = request.data.get('supplier')
                batch.save()
                res_data = BatchSerializer(batch).data
                return Response({'success': res_data})
            elif action == 'add':
                batch_ids = list(update_items.values_list('batch_id', flat = True).distinct())
                item_not_have_sku = line_items.filter(sku__sku__startswith='tempsku_').values_list('order_id__order_id', flat=True).distinct()
                item_not_approved = line_items.exclude(status__in=[1,2,3]).values_list('order_id__order_id', flat=True).distinct()
                item_have_batch = line_items.filter(batch_id__isnull=False).values_list('order_id__order_id', flat=True).distinct()
                
                if item_not_have_sku:
                    return Response({'error': f'Order with IDS {list(item_not_have_sku)} do not have SKU and is not allowed to create batch'}, status=400)
                if item_not_approved:
                    return Response({'error': f'Order with IDS {list(item_not_approved)} do not have status Approved and is not allowed to create batch'}, status=400)
                
                if change_batch != 'true':
                    if item_have_batch:
                        return Response({'error': f'Order with IDS {list(item_have_batch)} is assigned to another batchs and is not allowed to create batch'}, status=400)

                UserActionLog.objects.bulk_create(
                    [
                        UserActionLog(
                            user=request.user,
                            action='Add Batch',
                            object_name = 'Order',
                            object_id = order.order_id,
                            details= f'add to batch {batch.batch_id}' 
                        )
                        for order in orders 
                    ]      
                )
                
                update_items.update(batch_id=batch, status = 2)
                batch.date_modified = datetime.now()
                batch.save()
                batchs = Batch.objects.filter(batch_id__in = batch_ids)
                for batch in batchs:
                    if batch.number_items == 0:
                        batch.delete()
            elif action == 'delete':
                UserActionLog.objects.bulk_create(
                    [
                        UserActionLog(
                            user=request.user,
                            action='Remove Batch',
                            object_name = 'Order',
                            object_id = order.order_id,
                            details= f'remove from batch {batch.batch_id}' 
                        )
                        for order in orders 
                    ]      
                )
                
                update_items.update(batch_id=None, status=1)
                batch.date_modified = datetime.now()
                batch.save()
                if batch.number_items == 0:
                    batch.delete()
                
            order_ids = update_items.values_list('order_id', flat=True).distinct()
            orders = Order.objects.filter(order_id__in=order_ids) 
            update_order_status(orders)
            
            cache.clear()
            return Response({'success': 'Update Batch Successful'})
        except Exception as e:
            return Response({'error': f'Server get error: {e}'}, status=500)
    
    if request.method == 'DELETE':
        UserActionLog.objects.bulk_create(
            [
                UserActionLog(
                    user=request.user,
                    action='Remove Batch',
                    object_name = 'Order',
                    object_id = order.order_id,
                    details= f'remove from batch {batch.batch_id}' 
                )
                for order in orders 
            ]      
        )
        UserActionLog.objects.create(
                user=request.user,
                action='Delete',
                object_name = 'Batch',
                object_id = batch.batch_id,
            )
        line_items.update(batch_id=None, status=1)
        update_order_status(orders)
        batch.delete()
        
        cache.clear()
        return Response({'success': 'Delete Batch Successful'})


# ----------------SHIPPING--------------
@swagger_auto_schema(
        method='GET',
        manual_parameters=[
            openapi.Parameter('page', in_=openapi.IN_QUERY, description='Page number for pagination', type=openapi.TYPE_INTEGER),
            openapi.Parameter('per_page', in_=openapi.IN_QUERY, description='Number of items per page', type=openapi.TYPE_INTEGER),
            openapi.Parameter('order_by', in_=openapi.IN_QUERY, description='Field to order results by', type=openapi.TYPE_STRING),
            openapi.Parameter('order_type', in_=openapi.IN_QUERY, description='Order type (asc or desc)', type=openapi.TYPE_STRING),
            openapi.Parameter('order_id', in_=openapi.IN_QUERY, description='Comma-separated list of order IDs to filter', type=openapi.TYPE_STRING),
            openapi.Parameter('delivery_status', in_=openapi.IN_QUERY, description='Comma-separated list of delivery statuses to filter', type=openapi.TYPE_STRING),
            openapi.Parameter('site_id', in_=openapi.IN_QUERY, description='Comma-separated list of site IDs to filter', type=openapi.TYPE_STRING),
            openapi.Parameter('order_number', in_=openapi.IN_QUERY, description='Order number to filter', type=openapi.TYPE_STRING),
            openapi.Parameter('tracking_number', in_=openapi.IN_QUERY, description='Tracking number to filter', type=openapi.TYPE_STRING),
            openapi.Parameter('start_order_date_created', in_=openapi.IN_QUERY, description='Start date for filtering orders created', type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
            openapi.Parameter('end_order_date_created', in_=openapi.IN_QUERY, description='End date for filtering orders created', type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
        ],
        responses={
            200: openapi.Response('Successful response', ShippingSerializer),
            400: 'Bad Request. Check the error message for details.',
        },
    )
@api_view(['GET'])
def read_or_create_shippings(request):
    if request.method == 'GET':
        # Get parameters from the query string
        page = request.GET.get('page', 1)
        per_page = request.GET.get('per_page', 10)
        order_by = request.GET.get('order_by', 'update_date')
        order_type = request.GET.get('order_type', 'desc')
        order_id_filter = request.GET.get('order_id')
        delivery_status_filter = request.GET.get('delivery_status')
        site_filter = request.GET.get('site_id')
        order_number_filter = request.GET.get('order_number')
        tracking_number_filter = request.GET.get('tracking_number')
        start_order_created_str = request.GET.get('start_order_date_created')
        end_order_created_str = request.GET.get('end_order_date_created')
        

        # Validate and sanitize parameters
        try:
            page = int(page)
            per_page = int(per_page)
        except ValueError:
            return Response({'error': 'Invalid page or per_page value'}, status=400)
    
        if order_type == 'asc':
            order_by_field = order_by
        elif order_type == 'desc':
            order_by_field = '-' + order_by
        else:
            return Response({'error': 'Invalid order_type value'}, status=400)
        
        queryset = Shipping.objects.all().order_by(order_by_field)
        
        if start_order_created_str:
            start_order_created = datetime.fromisoformat(start_order_created_str)
            queryset = queryset.filter(line_item_id__order_id__date_created__gte = start_order_created).distinct()
        
        if end_order_created_str:
            end_order_created = datetime.fromisoformat(end_order_created_str) + timedelta(days=1)
            queryset = queryset.filter(line_item_id__order_id__date_created__lt = end_order_created).distinct()
        
        if tracking_number_filter:
            queryset = queryset.filter(tracking_number__icontains = tracking_number_filter)
            
        if delivery_status_filter:
            delivery_status_filter = delivery_status_filter.split(",")
            queryset = queryset.filter(delivery_status__in = delivery_status_filter)
        
        if site_filter:
            site_filter = site_filter.split(",")
            queryset = queryset.filter(line_item_id__order_id__site_id__in = site_filter).distinct()
            
        if order_number_filter:
            queryset = queryset.filter(line_item_id__order_id__order_number__icontains = order_number_filter).distinct()
        
        if order_id_filter:
            order_id_filter = order_id_filter.split(",")
            queryset = Shipping.objects.filter(line_item_id__order_id__order_id__in = order_id_filter).distinct()

        if per_page == -1:    
            serializer = ShippingSerializer(queryset, many=True)
            data = {
                'total_rows': len(queryset.distinct()),
                'results': serializer.data
            }
        else:
            paginator = Paginator(queryset.distinct(), per_page)
            page_obj = paginator.get_page(page)
            serializer = ShippingSerializer(page_obj, many=True)
            data = {
                'page': page,
                'per_page': per_page,
                'total_pages': paginator.num_pages,
                'total_rows': paginator.count,
                'results': serializer.data
            }
            
        return Response(data)


# -------------SITE--------------
@swagger_auto_schema(
        method='GET',
        manual_parameters=[
            openapi.Parameter('site', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='search by site id'),
            openapi.Parameter('status', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Active, Disabled'),
            openapi.Parameter('refresh_site_id', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='refresh'),
        ],
        responses={
            200: openapi.Response('Successful Response', SiteSerializer(many=True)),
        },
    )
@api_view(['GET'])
def view_sites(request):
    if request.method == 'GET':
        site_search = request.GET.get('site_id')
        status_filter = request.GET.get('status')
        refresh_site_id = request.GET.get('refresh_site_id')
        queryset = Site.objects.all()
        print(refresh_site_id)
        if refresh_site_id:
            site = Site.objects.get(site_id=refresh_site_id)
            etl_variation(refresh_site_id)
            etl_order(refresh_site_id, site)
            
            return Response({'success': 'Complete refresh data'})
        
        if site_search:
            queryset = queryset.filter(site_id__icontains = site_search)
        
        if status_filter:
            status_filter = status_filter.split(',')
            queryset = queryset.filter(status__in = status_filter)
        
        serializer = SiteSerializer(queryset, many=True)
        return Response(serializer.data, status=200)
    
    if request.method == 'POST':
        try:
            create_data = request.data
            if Site.objects.filter(site_id=create_data['site_id']).exists():
                return Response({'error': f'Site ID is exist'}, status=400)
            wcapi = init_connection(create_data['link'], create_data['authentication']['key'], create_data['authentication']['secret'])
            if wcapi == None:
                return Response({'error': 'Have problem in authentication please recheck key and secret'}, status=400)
                
            serializer = SiteSerializer(data=create_data)
            if serializer.is_valid():
                site = Site.objects.create(
                    site_id = create_data['site_id'],
                    link = create_data['link'],
                    name = create_data['name'],
                    platform = create_data['platform'],
                    authentication = create_data['authentication'],
                    status = create_data['status']
                )
                return Response({'success': 'Site create successful'}, status=200)
            else:
                return Response({'error': 'Invalid data provided'}, status=400)

        except Exception as e:
            return Response({'error': f'Failed to create Site because {e}'}, status=400)
            
@swagger_auto_schema(
        method='PUT',
        request_body=SiteSerializer,
        responses={
            200: openapi.Response('Successful Response', SiteSerializer),
            400: 'Bad Request',
            404: 'Not Found',
        },
    )
@api_view(['PUT', 'GET', 'DELETE'])
def rud_a_site(request, site_id):
    site = get_object_or_404(Site, site_id=site_id)
    
    if request.method == 'GET':
        serializer = SiteSerializer(site)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        sitepr = {key : getattr(site,key) for key in request.data.keys()}
        
        serializer = SiteSerializer(site, data=request.data)
        if serializer.is_valid():
            serializer.save()
            # UserActionLog.objects.create(
            #     user=request.user,
            #     action='Update Site',
            #     details= f'Update site {site_id} with previous data {sitepr}',
            # )
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        # UserActionLog.objects.create(
        #     user=request.user,
        #     action='Delete Site',
        #     details= f'Delete site {site_id} ',
        # )
        site.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ------------------SKU----------------------
@swagger_auto_schema(
    method='GET',
    manual_parameters=[
        openapi.Parameter('page', openapi.IN_QUERY, description='Page number for pagination', type=openapi.TYPE_INTEGER, default=1),
        openapi.Parameter('per_page', openapi.IN_QUERY, description='Number of items per page', type=openapi.TYPE_INTEGER, default=10),
        openapi.Parameter('order_by', openapi.IN_QUERY, description='Field to order variations by', type=openapi.TYPE_STRING, default='sku'),
        openapi.Parameter('order_type', openapi.IN_QUERY, description='Order type (asc or desc)', type=openapi.TYPE_STRING, default='desc'),
        openapi.Parameter('sku', openapi.IN_QUERY, description='Search for variations by SKU', type=openapi.TYPE_STRING),
        openapi.Parameter('site_id', openapi.IN_QUERY, description='Filter variations by site ID(s)', type=openapi.TYPE_STRING),
        openapi.Parameter('product_site_name', openapi.IN_QUERY, description='Search for variations by product site name', type=openapi.TYPE_STRING),
        openapi.Parameter('attributes', openapi.IN_QUERY, description='Search for variations by attributes', type=openapi.TYPE_STRING),
        openapi.Parameter('export', openapi.IN_QUERY, description='true to export', type=openapi.TYPE_STRING),
        openapi.Parameter('export_variation_id', openapi.IN_QUERY, description='id to export', type=openapi.TYPE_STRING),
        openapi.Parameter('is_tempsku', openapi.IN_QUERY, description='true to filter varation not have sku', type=openapi.TYPE_STRING),
        openapi.Parameter('refresh', openapi.IN_QUERY, description='true Refresh variations data', type=openapi.TYPE_STRING),
    ],
    responses={
        200: openapi.Response('Successful Response', VariationSerializer(many=True)),
        400: openapi.Response('Bad Request', VariationSerializer()),
    },
 ) 
@api_view(['GET'])
def read_variations(request):
    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 10)
    order_by = request.GET.get('order_by', 'sku')
    order_type = request.GET.get('order_type', 'desc')
    sku_search = request.GET.get('sku')
    site_filter = request.GET.get('site_id')
    name_search = request.GET.get('product_site_name')
    atb_search = request.GET.get('attributes')
    refresh = request.GET.get('refresh', 'false')
    export = request.GET.get('export', 'false')
    export_variation_id = request.GET.get('export_variation_id')
    is_tempsku = request.GET.get('is_tempsku', 'none')
    
    
    # Validate and sanitize parameters
    if refresh == 'true':
        if site_filter:
            etl_variation(site_filter)
    try:
        page = int(page)
        per_page = int(per_page)
    except ValueError:
        return Response({'error': 'Invalid page or per_page value'}, status=400)
    
    if order_type == 'asc':
        order_by_field = order_by
    elif order_type == 'desc':
        order_by_field = '-' + order_by
    else:
        return Response({'error': 'Invalid order_type value'}, status=400)
    if order_by != 'product_id':
        queryset = Variation.objects.all().order_by(order_by_field)
    else:
        queryset = Variation.objects.all().order_by('sku' if order_type == 'asc' else '-sku')
  
    if site_filter:
        site_filter = site_filter.split(",") 
        queryset = queryset.filter(site_id__in = site_filter)
        
    if sku_search:
        queryset = search_string(queryset, 'sku' , sku_search)
            
    if name_search:
        queryset = search_string(queryset, 'product_site_name' , name_search)
  
    if atb_search:
        queryset = search_string(queryset, 'attributes_id' , atb_search)
    
    if is_tempsku== 'true':
        queryset = Variation.objects.filter(sku__sku__istartswith='tempsku')
    if is_tempsku== 'false':
        queryset = Variation.objects.exclude(sku__sku__istartswith='tempsku')
        
    if export == 'true':
        if export_variation_id:
            export_variation_id = export_variation_id.split(',')
            queryset = queryset.filter(id__in= export_variation_id)
        
        df = pd.DataFrame.from_records(queryset.values('site_id','product_site_id','product_site_name','attributes','sku') )
        df_pro_site = pd.DataFrame(Product_Site.objects.all().values('site_id','product_site_id','link'))
        df = df.merge(df_pro_site,on=['site_id', 'product_site_id'], how='left')
        
        column_mapping = {
                'site_id': 'Site ID',
                'product_site_id': 'Product Site ID',
                'product_site_name': 'Product Site Name',
                'link': 'Link',
                'attributes': 'Attributes',
                'sku': 'SKU'
        }
        df.rename(columns=column_mapping, inplace=True)
        df['Attributes'] = df['Attributes'].apply(lambda x: x if x is not None else [])
        max_len = df['Attributes'].apply(len).max()
        new_columns = [f'Attribute_{i+1}' for i in range(max_len)]
        df[new_columns] = pd.DataFrame(df['Attributes'].to_list(), columns=new_columns)
        df = df.drop('Attributes', axis=1)
        df = df[[col for col in df.columns if col != 'SKU'] + ['SKU']]
        df['New SKU'] = np.nan
        return Response({'csv': generate_export_link(df, f'export_sku')})
     
    if per_page == -1:    
        serializer = VariationSerializer(queryset, many=True)
        data = {
            'total_rows': len(queryset),
            'results': serializer.data
        }
    
    else:
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        serializer = VariationSerializer(page_obj, many=True)
        data = {
            'page': page,
            'per_page': per_page,
            'total_pages': paginator.num_pages,
            'total_rows': paginator.count,
            'results': serializer.data
        }
        
    return Response(data)

@swagger_auto_schema(
    method='GET',
    manual_parameters=[
        openapi.Parameter('page', openapi.IN_QUERY, description='Page number for pagination', type=openapi.TYPE_INTEGER, default=1),
        openapi.Parameter('per_page', openapi.IN_QUERY, description='Number of items per page', type=openapi.TYPE_INTEGER, default=10),
        openapi.Parameter('order_by', openapi.IN_QUERY, description='Field to order variations by', type=openapi.TYPE_STRING, default='product_id'),
        openapi.Parameter('order_type', openapi.IN_QUERY, description='Order type (asc or desc)', type=openapi.TYPE_STRING, default='desc'),
        openapi.Parameter('product_id', openapi.IN_QUERY, description='Search for products by product_id', type=openapi.TYPE_STRING),
        openapi.Parameter('site_id', openapi.IN_QUERY, description='Filter products by site ID(s)', type=openapi.TYPE_STRING),
        openapi.Parameter('product_site_name', openapi.IN_QUERY, description='Search for products by product site name', type=openapi.TYPE_STRING),
        openapi.Parameter('refresh', openapi.IN_QUERY, description='true Refresh variations data', type=openapi.TYPE_STRING),
    ],
    responses={
        200: openapi.Response('Successful Response', ProductSiteSerializer(many=True)),
        400: openapi.Response('Bad Request', ProductSiteSerializer()),
    },
 ) 
@api_view(['GET'])
def read_product_sites(request):
    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 10)
    order_by = request.GET.get('order_by', 'product_id')
    order_type = request.GET.get('order_type', 'desc')
    product_id_search = request.GET.get('product_id')
    site_filter = request.GET.get('site_id')
    name_search = request.GET.get('product_site_name')
    refresh = request.GET.get('refresh', False)
    
    # Validate and sanitize parameters
    if refresh == True:
        if site_filter:
            etl_variation(site_filter)
    try:
        page = int(page)
        per_page = int(per_page)
    except ValueError:
        return Response({'error': 'Invalid page or per_page value'}, status=400)
    
    if order_type == 'asc':
        order_by_field = order_by
    elif order_type == 'desc':
        order_by_field = '-' + order_by
    else:
        return Response({'error': 'Invalid order_type value'}, status=400)
    queryset = Product_Site.objects.all().order_by(order_by_field)
  
    if site_filter:
        site_filter = site_filter.split(",") 
        queryset = queryset.filter(site_id__in = site_filter)
    
    if product_id_search:
        queryset = search_string(queryset, 'product_id' , product_id_search)
            
    if name_search:
        queryset = search_string(queryset, 'product_site_name' , name_search)
        
    if per_page == -1:    
        serializer = ProductSiteSerializer(queryset, many=True)
        data = {
            'total_rows': len(queryset),
            'results': serializer.data
        }
    
    else:
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        serializer = ProductSiteSerializer(page_obj, many=True)
        data = {
            'page': page,
            'per_page': per_page,
            'total_pages': paginator.num_pages,
            'total_rows': paginator.count,
            'results': serializer.data
        }
        
    return Response(data)


# -------------------UPFILE-------------------
@api_view(['POST'])
def upload_sku_file(request):
    parser_classes = (FileUploadParser,)
    uploaded_file = request.FILES.get('file', None)

    dict_site_id = {site.site_id: site for site in Site.objects.all()}
    dict_sku = {sku_instance.sku: sku_instance for sku_instance in SKU.objects.all()}
    
    if not uploaded_file:
        return Response({'error': 'No file uploaded'},status=400)

    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, keep_default_na=False)
        elif uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file)
        else:
            return Response({'error': 'Invalid file format'},status=400)
        
        columns_to_check = [
            'Site ID', 'Product Site ID','SKU', 'New SKU'
        ]
        
        # Find missing columns
        missing_columns = [column for column in columns_to_check if column not in df.columns]

        # Check and return missing columns
        if missing_columns:
            return Response({'error': f"Missing Columns: {missing_columns}"}, status=400)
       
        unique_site_id = df['Site ID'].unique()
        df['Product Site ID'] = df['Product Site ID'].astype(str)
        df['Product ID'] = df['New SKU'].str.split('_').str[0]
        df['Product ID Length'] = df['New SKU'].str.split('_').str.len()
        
        df_error = df[df['Product ID Length']<=1]['New SKU'].unique() 
        if len(df_error) > 0:
            return Response({'error': f'Can not get Product ID from New SKU {df_error}'}, status=400)
        
        df_check = df.drop_duplicates(subset=['Site ID', 'Product Site ID', 'Product ID']).groupby(['Site ID', 'Product Site ID'])['Product ID'].count().reset_index(name='unique_product_count')
        df_error = df_check[df_check['unique_product_count'] > 1]
        for idx, row in df_error.iterrows():
            return Response({'error': f'Product Site ID of Site {row["Site ID"]} have more than one Product ID get from New SKU'}, status=400)
        
        site_not_exist = [site_id for site_id in unique_site_id if site_id not in dict_site_id]
        if site_not_exist:
            return Response({'error': f'Site {site_not_exist} not exist in system'}, status=400)
        
        sku_not_exist = [sku for sku in df['SKU'].unique() if sku not in dict_sku]
        if sku_not_exist:
            return Response({'error': f'SKUs {sku_not_exist} not exist in system'}, status=400)
        
        if len(df[df['New SKU'].isna()] > 0):
            return Response({'error': f'There are some empty values in New SKU'}, status=400)
        
        for site_id in unique_site_id:
            df_check = df[df['Site ID'] == site_id]
            pro_id_file = set(df_check['Product Site ID'].unique())
            pro_id_sys = set(Product_Site.objects.filter(site_id=site_id).values_list('product_site_id', flat=True))
            pro_not_in_sys = pro_id_file - pro_id_sys
            if pro_not_in_sys:
                return Response({'error': f'Product Site IDs {pro_not_in_sys} not exist in Site {site_id}'}, status=400)
        
        df_product_site_sys = pd.DataFrame(Product_Site.objects.filter(site_id__in=unique_site_id).values()).rename(columns={'site_id_id': 'Site ID', 'product_site_id': 'Product Site ID'})
        df_product_site_file = df.drop_duplicates(subset=['Site ID', 'Product Site ID']).copy()
        df_product_site_sys = df_product_site_sys.merge(df_product_site_file, on = ['Site ID', 'Product Site ID'], how='inner')

        df_error = df_product_site_sys[~df_product_site_sys['product_id'].str.startswith('temp') & (df_product_site_sys['product_id'] != df_product_site_sys['Product ID'])]
        if len(df_error) > 0:
            for idx, row in df_error.iterrows():
                return Response({'error': f'Product Site ID {row["Product Site ID"]} of Site {row["Site ID"]} is assigned to another Product ID {row["product_id"]}'}, status=400)
        
        sku_with_multiple_new_sku = df.groupby('SKU')['New SKU'].nunique().reset_index()
        sku_with_multiple_new_sku = sku_with_multiple_new_sku[sku_with_multiple_new_sku['New SKU'] > 1]['SKU'].tolist()
        if sku_with_multiple_new_sku:
            return Response({'error': f"SKUs with 2 or more New SKU values: {sku_with_multiple_new_sku}"}, status=400)
        
        df_product_site_sys = df_product_site_sys[df_product_site_sys['product_id'].str.startswith('temp')]
        for idx, row in df_product_site_sys.iterrows():
            old_product_id = row['product_id']
            new_product_id = row['Product ID']
            Product_Site.objects.filter(product_id=old_product_id).update(product_id=new_product_id)
            SKU.objects.filter(product_id=old_product_id).update(product_id=new_product_id)
        
        temp_sku = []
        old_sku = []
        for idx, row in df.iterrows():
            sku_instance = dict_sku.get(row["New SKU"]) 
            if sku_instance == None:
                sku_instance = SKU.objects.create(
                    sku=row['New SKU'],
                    product_id =row['Product ID'],
                    attributes_id = dict_sku.get(row["SKU"]).attributes_id,
                    attributes = dict_sku.get(row["SKU"]).attributes
                )
                dict_sku.update({sku_instance.sku: sku_instance})         
           
            Variation.objects.filter(sku__sku=row['SKU']).update(sku=sku_instance)
            if row['SKU'].startswith('tempsku_') and row['SKU'] not in temp_sku:
                Order_Line_Item.objects.filter(sku__sku=row['SKU']).update(sku=sku_instance)
                temp_sku.append(row['SKU'])
            if not row['SKU'].startswith('tempsku_') and row['SKU'] not in old_sku:
                Order_Line_Item.objects.filter(sku__sku=row['SKU']).update(sku=sku_instance)
                old_sku.append(row['SKU'])
                
        SKU.objects.filter(sku__in=temp_sku).delete()       
        SKU.objects.filter(sku__in=old_sku).update(is_oldsku=1)
        
        cache.clear()
        return Response({'success': 'Data uploaded successfully'}, status =200)

    except Exception as e:
        return Response({'error': f'Server get error: {str(e)}'}, status = 500)

@swagger_auto_schema(
        method='POST',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'batch_id': openapi.Schema(type=openapi.TYPE_STRING, description='batch_id to import'),
                'file': openapi.Schema(type=openapi.TYPE_FILE, description='File to upload'),
                'replace_or_add_new': openapi.Schema(type=openapi.TYPE_FILE, description='if replace must be input replace_tracking'),
                'replace_tracking': openapi.Schema(type=openapi.TYPE_STRING, description='comma separated tracking number in system will be replace (optional)'),
            }
        ),
        responses={200: openapi.Response('Successful Response', openapi.Schema(type=openapi.TYPE_OBJECT))},
    )
@api_view(['POST'])
def upload_tracking_file(request):
    with open('/home/mkt-en/ecom_operation/dashboard/etl/Carrier_New.json', "r") as file:
        courier_data = json.load(file)
    compiled_rules = [(item.get("_code"), re.compile(item["_rule"])) for item in courier_data if item.get("_rule") is not None]
    def determine_courier(row):
        tracking_number = row['Tracking Number']
        courier_code = row['Courier Code']

        if pd.notna(courier_code):
            return courier_code

        for code, rule in compiled_rules:
            if rule.fullmatch(tracking_number):
                return code

        return 'ERROR'
  
    parser_classes = (FileUploadParser,)
    uploaded_file = request.FILES.get('file', None)
    batch_id = request.data.get('batch_id')
    order_id = request.data.get('order_id')

    if uploaded_file is None:
        return Response({'error': 'No file uploaded'},status=400)   
        
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, dtype={'Tracking Number': str})
        elif uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file, dtype={'Tracking Number': str})
        else:
            return Response({'error': 'Invalid file format'}, status=400)
        
        # Find missing columns
        columns_to_check = ['Order ID', 'Tracking Number', 'Courier Code']
        missing_columns = [column for column in columns_to_check if column not in df.columns]
        if missing_columns:
            return Response({'error': f"Missing Columns: {missing_columns}"}, status=400)
        
        df_error = df[df['Tracking Number'].isna()]
        if len(df_error) > 0:
            return Response({'error': f'There are some empty tracking number'}, status=400)
        
        df['Tracking Number'] = df['Tracking Number'].astype(str)
        df['Courier Code'] = df.apply(determine_courier, axis=1)

        df_error = df[df['Courier Code']=='ERROR']
        if len(df_error) > 0:
            return Response({'error': f'Failed to detect carrier of some tracking in: {generate_export_link(df_error,"error_carrier")}'}, status=400)
        
        dict_key_api = {key.name: key for key in Key_API.objects.all()}
        
        # VALIDATE
        order_ids = set(df['Order ID'].unique())
        tracking_numbers = set(df['Tracking Number'].unique())
        
        # Check for duplicate tracking numbers
        duplicate_rows = df[df.duplicated(subset=['Tracking Number'])]
        duplicate_list = duplicate_rows['Tracking Number'].values.tolist()
        if duplicate_list:
            return Response({'error': f"Duplicate Tracking Numbers: {duplicate_list}"}, status=400)

        order_objects = Order.objects.filter(order_id__in=order_ids)
        
        if batch_id:
            # Get the batch
            batch = Batch.objects.get(batch_id=batch_id)

            # Get line items for the batch
            line_items_order_ids = set(batch.line_items.values_list('order_id__order_id', flat=True).distinct())  # Update the reference

            # Check if Order IDs not in the batch
            order_ids_not_in_batch = order_ids - line_items_order_ids
            if order_ids_not_in_batch:
                return Response({'error': f"Order IDs: {list(order_ids_not_in_batch)} not exist in Batch {batch.batch_id}"}, status=400)
        
        if order_id:
            if len(order_ids) > 1:
                return Response({'error': f"File upload have many Order IDs"}, status=400)

            if order_id not in order_ids:
                return Response({'error': f"File upload must have track of order {order_id}"}, status=400)
            
            
        # Check if Tracking Numbers already exist in the system
        existing_tracking_numbers = set(Shipping.objects.filter(tracking_number__in=tracking_numbers).values_list('tracking_number', flat=True))
        if existing_tracking_numbers:
            return Response({'error': f"Tracking Numbers: {list(existing_tracking_numbers)} already exist in the system"}, status=400)

        # Check order that have Tracking Number
        replace_or_add_new = request.data.get('replace_or_add_new')
        order_have_tracking = order_objects.filter(line_items__shippings__tracking_number__isnull=False,line_items__shippings__valid=1).distinct()

        if order_have_tracking.exclude(status__in=[4,5]).exists():
            return Response({'error': f'Order with IDs {list(order_have_tracking.exclude(status=4).values_list("order_id", flat=True))} not have status shippping and not allow to update new tracking'}, status=400)
        elif order_have_tracking.count() > 0:
            if replace_or_add_new:
                if replace_or_add_new == 'replace':
                    replace_tracking = request.data.get('replace_tracking').split(',')
                    Shipping.objects.filter(tracking_number__in=replace_tracking).update(valid=0)
            else:
                return Response({'error': [
                    {
                        'order_id': order.order_id,
                        'tracking_number': list(order.line_items.filter(shippings__valid=1).values_list('shippings__tracking_number', flat=True).distinct())
                    }
                    for order in order_have_tracking
                ]}, status= 444) 
        
        # PUSH DATA
        df['order_site_id'] = np.where(df['Order ID'].str.startswith('RS-'), np.nan, df['Order ID'].str.split('-').str[-1])

        df = pd.merge(df, 
            pd.DataFrame.from_records(
                order_objects.values()
            ).rename(columns={
                'order_id': 'Order ID',
                'site_id_id': 'site_id'
            }),
            on='Order ID', how='left')

        # line_items = batch.line_items.filter(order_id__order_id__in=order_ids)
        line_items = Order_Line_Item.objects.filter(order_id__order_id__in=order_ids)
        df_items = pd.DataFrame(line_items.values('line_item_id', 'order_id__order_number', 'order_id__order_id')).rename(columns={
                'order_id__order_id': 'order_id',
                'order_id__order_number': 'order_number',
            })
        
        tkmore_paypal_carrier = {
            'yunexpress': 'YUNEXPRESS',
            'jcex': 'CN_JCEX',
            'sfb2c': 'SFB2C',
            'usps': 'USPS',
            'china-post': 'CN_CHINA_POST_EMS'
        }
        
        action_log = []
        batch_size = 40
        error_tracking_number = []
        success_tracking_number = []
        dict_site_id = {site.site_id: site for site in Site.objects.filter(status='Active')}
        for i in range(0, len(df), batch_size):
            batch_data = df[i:i + batch_size]
            
            # Post to TrackingMore
            up_tracking_data = [
                {
                    'order_number': row['Order Number'],
                    'tracking_number': row['Tracking Number'],
                    'courier_code': row['Courier Code'],
                    'destination_code': row['country_code'],
                    'lang': 'en'
                }
                for index, row in batch_data.drop_duplicates(subset='Tracking Number').iterrows()
            ]
            
            headers = {
                    'Content-Type': 'application/json',
                    'Tracking-Api-Key': dict_key_api.get('TrackingMore').authentication['key']
                }
            response = requests.post(
                    "https://api.trackingmore.com/v3/trackings/create", 
                    data=json.dumps(up_tracking_data), 
                    headers=headers
                )
            if response.json()['code'] == 200:
                batch_success_tracking = [i['tracking_number'] for i in response.json()['data']['success']]
                success_tracking_number.extend(batch_success_tracking)
                error_tracking_number.extend([i for i in response.json()['data']['error']])
                update_tracking = []
                
                today = datetime.now(timezone.utc)
                if len(batch_success_tracking) > 0:
                    params = {
                        'items_amount': 2000,
                        'pages_amount' : 1,
                        'tracking_numbers': ','.join(batch_success_tracking)
                    }
                    URL = 'https://api.trackingmore.com/v3/trackings/get'
                    for attempt in range(1, 6):
                        response = requests.get(url = URL, headers=headers, params = params)
                        if response.json()['code'] == 200:
                            tracking_data = response.json()['data']
                            break
                
                    for tracking in tracking_data:         
                        order_id = df[df['Tracking Number']==tracking['tracking_number']]['Order ID'].iloc[0]
                        for idx, item in df_items[df_items['order_id']==order_id].iterrows():
                            temp = tracking.copy()
                            temp['line_item_id']  = item['line_item_id']
                            update_tracking.append(temp)
                        action_log.append(
                                UserActionLog(
                                    user=request.user,
                                    action='Add Tracking',
                                    object_name = 'Order',
                                    object_id = order_id,
                                    details= f'add tracking number ' + str(tracking['tracking_number']) 
                                )
                            )
                    load_shipping(update_tracking)
                    
                    # Filter batch data with tracking number is success up to Tracking More and not resend order
                    batch_data = batch_data[(batch_data['Tracking Number'].isin(batch_success_tracking)) & (~batch_data['Order ID'].str.startswith('RS-'))]
                    
                    #POST TRACKING TO WOOCOMMERCE
                    for site_id in batch_data['site_id'].unique():
                        site = dict_site_id.get(site_id)
                        wcapi_v1 = API(
                                url=site.link,
                                consumer_key=site.authentication['key'],
                                consumer_secret=site.authentication['secret'],
                                version= 'wc/v1',
                                timeout=60,
                                user_agent = urlparse(site.link).netloc
                            )
                        data = {
                            'orders': [
                                {
                                    'order_id': int(row['order_site_id']),
                                    'items': [
                                        {
                                            'line_item_id': int(item['line_item_id'].split('-')[-1]),
                                            'tracking_number': row['Tracking Number'],
                                            'carrier_slug': row['Courier Code']
                                        }
                                        for idx, item in df_items[df_items['order_id']==row['Order ID']].iterrows()
                                    ],
                                    'status' : 'wc-completed'
                                }
                                for idx, row in batch_data[batch_data['site_id']==site_id].iterrows()
                            ]
                        }
                        wcapi_v1.post('orders/tracking', data)

                    #POST TRACKING TO STRIPE
                    batch_stripe = batch_data[batch_data['payment_method'].eq('stripe')]
                    for idx, row in batch_stripe.iterrows():
                        stripe.api_key = dict_key_api.get(row['payment_method_title']).authentication['secret']
                        trans_id = row['transaction_id']
                        data = {
                            'address': {
                                'city': row['city'],
                                'country': row['country_code'],
                                'line1': row['address_1'],
                                'line2': row['address_2'],
                                'postal_code': row['postcode'],
                                'state': row['state_code']
                            },
                            'carrier': row['Courier Code'],
                            'name': f"{row['first_name']} {row['last_name']}",
                            'phone': row['phone'],
                            'tracking_number': row['Tracking Number']
                        }
                    
                        if trans_id.startswith('ch_'):
                            stripe.Charge.modify(trans_id, shipping=data)
                        elif trans_id.startswith('pi_'):
                            stripe.PaymentIntent.modify(trans_id, shipping=data)
                    
                    #POST TRACKING TO PAYPAL
                    batch_paypal = batch_data[batch_data['payment_method'].eq('paypal_express')]
                    for payment_name in batch_paypal['payment_method_title'].unique():
                        PAYPAL_HOST = "https://api-m.paypal.com/v1"
                        PAYPAL_KEY = dict_key_api.get(payment_name)
                        CLIENT_ID = PAYPAL_KEY.authentication['key']
                        CLIENT_SECRET = PAYPAL_KEY.authentication['secret']

                        response = requests.post(
                            PAYPAL_HOST+'/oauth2/token',
                            auth=HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET),
                            headers={"Content-Type": "application/x-www-form-urlencoded"},
                            data= {"grant_type": "client_credentials"}
                        )
                        token = response.json()['access_token']             
                        headers = {
                            'Authorization': f'Bearer {token}',
                            'Content-Type': 'application/json',
                        }
                        trackers = []
                        for idx, row in batch_paypal[batch_paypal['payment_method_title']==payment_name].iterrows():
                            temp = { 
                                "transaction_id": row['transaction_id'], 
                                "tracking_number": row['Tracking Number'],
                                "carrier": tkmore_paypal_carrier.get(row['Courier Code'], 'OTHER'), 
                                "status": "SHIPPED"
                            }
                            if temp['carrier'] == 'OTHER':
                                temp['carrier_name_other'] == batch_data['Courier Code']
                            trackers.append(temp)
                            
                        for i in range(0, len(trackers), 20):
                            data = {
                                'trackers': trackers[i:i + 20]
                            }
                            requests.post(PAYPAL_HOST+'/shipping/trackers-batch',  headers=headers, data=json.dumps(data))
        
        line_item_success = line_items.filter(shippings__tracking_number__in = success_tracking_number)
        order_success = line_item_success.values_list('order_id__order_id', flat=True).distinct()
        line_item_id = line_item_success.values_list('line_item_id', flat=True)
        line_item_success.update(status = 3)
        order_success_objects = order_objects.filter(order_id__in=order_success)
        order_success_objects.update(status = 4)
                
        UserActionLog.objects.bulk_create(action_log)
        

        batches = Batch.objects.filter(line_items__line_item_id__in = line_item_id).distinct()
        for batch in batches:
            if batch.number_orders == batch.number_orders_fulfilled:
                batch.status = 2
                batch.save()
            else:
                batch.status = 0
                batch.save()
        
        shipping_email_order = order_success_objects.filter(site_id__auto_send_mail = 1, site_id__email__isnull = False)
        email_template = Email_Template.objects.get(id=3)
        for order in shipping_email_order:
            send_email(order, email_template, order.site_id.email, order.email, list(line_item_id))  
        
        cache.clear()
        if len(error_tracking_number) > 0:
            df_error = pd.DataFrame(error_tracking_number)
            return Response({'error': f'Some Tracking Number failed to upload to TrackingMore download in: {generate_export_link(df_error,"error_tracking")}'},status=400)
        
        
        return Response({'success': f'Data upload successful'})
        
    except Exception as e:
        return Response({'error': f'Server Error to processing the file: {str(e)}'}, status=500)

#-------------------- Coupon and gateway --------------
@swagger_auto_schema(
        method='GET',
        manual_parameters=[
            openapi.Parameter('site_id', in_=openapi.IN_QUERY, description='Filter gateway by site id', type=openapi.TYPE_STRING),
        ],
        responses={
            200: openapi.Response('Successful Response', SiteSerializer(many=True)),
        },
    )
@api_view(['GET'])
def view_gateway(request):
    site_filter = request.GET.get('site_id')
    if not site_filter:
        return Response({'error': f'site_id is required'}, status=400)
    site = Site.objects.get(site_id=site_filter)
    wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
    data = get_gateways(wcapi)
    # data = [
    #     {
    #        'id': item['id'],
    #        'title': item['title'],
    #        'description': item['description'],
    #        'method_title': item['method_title'],
    #        'method_description': item['method_description'],
    #        'method_supports': item['method_supports']
    #     }
    #     for item in data
    #     if item["enabled"] == True
    # ]
    return Response({'results': data}, status=200)

@swagger_auto_schema(
        method='GET',
        manual_parameters=[
            openapi.Parameter('site_id', in_=openapi.IN_QUERY, description='Filter gateway by site id', type=openapi.TYPE_STRING),
        ],
        responses={
            200: openapi.Response('Successful Response'),
        },
    )
@swagger_auto_schema(
        method='POST',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'site_id': openapi.Schema(type=openapi.TYPE_STRING),
                'code': openapi.Schema(type=openapi.TYPE_STRING),
                'amount': openapi.Schema(type=openapi.TYPE_STRING),
                'discount_type': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=['percent', 'fixed_cart','fixed_product']
                ),
                'description': openapi.Schema(type=openapi.TYPE_STRING),
                'date_expires_gmt': openapi.Schema(type=openapi.TYPE_STRING),
                'individual_use': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'product_ids': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_STRING)
                ),
                'excluded_product_ids': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_STRING)
                ),
                'usage_limit': openapi.Schema(type=openapi.TYPE_INTEGER),
                'usage_limit_per_user': openapi.Schema(type=openapi.TYPE_INTEGER),
                'limit_usage_to_x_items': openapi.Schema(type=openapi.TYPE_INTEGER),
                'free_shipping': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'exclude_sale_items': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'minimum_amount': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'maximum_amount': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'email_restrictions': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_STRING)
                ),
            },
            required=['site_id','code','amount','discount_type'] 
        ),
        responses={
            200: openapi.Response('Created'),
            400: 'Bad Request',
        },
    )
@swagger_auto_schema(
        method='PUT',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'id': openapi.Schema(type=openapi.TYPE_STRING),
                'site_id': openapi.Schema(type=openapi.TYPE_STRING),
                'code': openapi.Schema(type=openapi.TYPE_STRING),
                'amount': openapi.Schema(type=openapi.TYPE_STRING),
                'discount_type': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=['percent', 'fixed_cart','fixed_product']
                ),
                'description': openapi.Schema(type=openapi.TYPE_STRING),
                'date_expires_gmt': openapi.Schema(type=openapi.TYPE_STRING),
                'individual_use': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'product_ids': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_STRING)
                ),
                'excluded_product_ids': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_STRING)
                ),
                'usage_limit': openapi.Schema(type=openapi.TYPE_INTEGER),
                'usage_limit_per_user': openapi.Schema(type=openapi.TYPE_INTEGER),
                'limit_usage_to_x_items': openapi.Schema(type=openapi.TYPE_INTEGER),
                'free_shipping': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'exclude_sale_items': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'minimum_amount': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'maximum_amount': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'email_restrictions': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_STRING)
                ),
            },
            required=['site_id','id'] 
        ),
        responses={
            200: openapi.Response('Updated'),
            400: 'Bad Request',
        },
    )
@swagger_auto_schema(
        method='DELETE',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'id': openapi.Schema(type=openapi.TYPE_STRING),
                'site_id': openapi.Schema(type=openapi.TYPE_STRING),
            },
            required=['site_id','id'] 
        ),
        responses={
            200: openapi.Response('deleted'),
            400: 'Bad Request',
        },
    )
@api_view(['GET', 'POST', 'PUT', "DELETE"])
def view_coupon(request):
    if request.method == 'GET':
        site_filter = request.GET.get('site_id')
        dict_site_id = {site.site_id: site for site in Site.objects.filter(status='Active')}
        if site_filter:
            site_filter = site_filter.split(',')
            dict_site_id = {site.site_id: site for site in Site.objects.filter(status='Active', site_id__in=site_filter)}
            return Response({'error': f'site_id is required'}, status=400)
        
        result_data = []
        
        for site_id, site in dict_site_id.items():
            wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])
            data = get_coupons(wcapi)
            for coupon in data:
                coupon['site_id'] = site_id
                result_data.append(coupon)
            return Response({'results': result_data}, status=200)

    if request.method == 'POST':
        data = request.data
        if 'site_id' in data:
            site_id = data.pop('site_id')
        else:
            return Response({'error': 'site_id is required'}, status=400)
        site = get_object_or_404(Site, site_id=site_id)
        wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])

        
        response = wcapi.post("coupons", data)
        if response.status_code == 201:
            cache.clear()
            return Response({'success': 'Coupon code created successfully'}, status=200)
        else:
            return Response({'error': f'Failed to create coupon code with error: {response.json()["message"]}'}, status=400)
    
    if request.method == 'PUT':
        data = request.data
        site_id = data.pop('site_id')
        coupon_id = data.pop('id')
        
        site = get_object_or_404(Site, site_id=site_id)
        wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])

        
        response = wcapi.put(f"coupons/{coupon_id}", data)
        if response.status_code == 200:
            cache.clear()
            return Response({'success': 'Coupon code updated successfully'}, status=200)
        else:
            return Response({'error': f'Failed to update coupon code with error: {response.json()["message"]}'}, status=400)
    
    if request.method == 'DELETE':
        data = request.data
        site_id = data.pop('site_id')
        coupon_id = data.pop('id')
        
        site = get_object_or_404(Site, site_id=site_id)
        wcapi = init_connection(site.link, site.authentication['key'], site.authentication['secret'])

        
        response = wcapi.delete(f"coupons/{coupon_id}", params={"force": True})
        if response.status_code == 200:
            cache.clear()
            return Response({'success': 'Coupon code updated successfully'}, status=200)
        else:
            return Response({'error': f'Failed to update coupon code with error: {response.json()["message"]}'}, status=400)
        

# -----------------TEMPLATE EXPORT----------------
@swagger_auto_schema(
        method='GET',
        manual_parameters=[
            openapi.Parameter('name', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='search name'),
            openapi.Parameter('object_export', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='filter object_export comma separated'),
        ],
        responses={
            200: openapi.Response('Successful Response', TemplateExportSerializer(many=True)),
        },
    )
@swagger_auto_schema(
        method='POST',
        request_body=TemplateExportSerializer,
        responses={
            200: openapi.Response('Successful Response', TemplateExportSerializer),
            400: 'Bad Request',
            404: 'Not Found',
        },
    )
@api_view(['GET','POST'])
def read_or_create_templates(request):
    if request.method == 'GET':
        name_search = request.GET.get('name')
        object_export = request.GET.get('object_export')
        queryset = Template_Export.objects.all()
        
        if name_search:
            queryset = queryset.filter(name__icontains = name_search)
        if object_export:
            object_export = object_export.split(',')
            queryset = queryset.filter(object_export__in = object_export)
            
        serializer = TemplateExportSerializer(queryset, many=True)
        return Response({'results': serializer.data}, status=200)
    if request.method == 'POST':
        try:
            if Template_Export.objects.filter(name=request.data['name']).exists():
                return Response({'error': f'Name of template is exist'}, status=400)
            
            serializer = TemplateExportSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response({'success': 'Template create successful'}, status=200)
            else:
                print(serializer.errors)
                return Response({'error': 'Invalid data provided'}, status=400)

        except Exception as e:
            return Response({'error': f'Failed to create template because {e}'}, status=400)
            
@swagger_auto_schema(
        method='PUT',
        request_body=TemplateExportSerializer,
        responses={
            200: openapi.Response('Successful Response', TemplateExportSerializer),
            400: 'Bad Request',
            404: 'Not Found',
        },
    )
@api_view(['PUT', 'GET', 'DELETE'])
def rud_a_template(request, template_id):
    template = get_object_or_404(Template_Export, id=template_id)
    
    if request.method == 'GET':
        serializer = TemplateExportSerializer(template)
        return Response(serializer.data)
    
    elif request.method == 'PUT': 
        serializer = TemplateExportSerializer(template, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        else:
            return Response({'error': serializer.errors}, status=400)

    elif request.method == 'DELETE':
        template.delete()
        return Response(status=200)


# --------------------NOTIFICATION-------------------
@swagger_auto_schema(
        method='GET',
        manual_parameters=[
            openapi.Parameter('page', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='page'),
            openapi.Parameter('per_page', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='per page -1 to all'),
            openapi.Parameter('start_date', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='notifications greater start date'),
            openapi.Parameter('end_date', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='notifications less than end date'),
        ],
        responses={
            200: openapi.Response('Successful Response', NotificationSerializer(many=True)),
        },
    )
@api_view(['GET'])
def read_notifications(request):
    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 10)
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    try:
        page = int(page)
        per_page = int(per_page)
    except ValueError:
        return Response({'error': 'Invalid page or per_page value'}, status=400)
    
    
    queryset = Notification.objects.all().order_by('-timestamp')
    
    if start_date:
        queryset = queryset.filter(timestamp__gte = start_date)

    if end_date:
        queryset = queryset.filter(timestamp__lte = end_date)
    
    if per_page == -1:    
        serializer = NotificationSerializer(queryset, many=True)
        data = {
            'total_rows': len(queryset),
            'results': serializer.data
        }
    else:
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        serializer = NotificationSerializer(page_obj, many=True)
        data = {
            'page': page,
            'per_page': per_page,
            'total_pages': paginator.num_pages,
            'total_rows': paginator.count,
            'results': serializer.data
        }
        
    return Response(data)


# -------------------USER_ACTION_LOG---------------
@swagger_auto_schema(
        method='GET',
        manual_parameters=[
            openapi.Parameter('page', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='page'),
            openapi.Parameter('per_page', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='per page -1 to all'),
            openapi.Parameter('start_date', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='log greater start date'),
            openapi.Parameter('end_date', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='log less than end date'),
            openapi.Parameter('object_name', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='object name filter (Order, Batch, ...)'),
            openapi.Parameter('object_id', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Search object id of object to filter'),
            openapi.Parameter('username', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Search object id of object to filter'),
            openapi.Parameter('action', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Search object id of object to filter'),
        ],
        responses={
            200: openapi.Response('Successful Response', UserActionLogSerializer(many=True)),
        },
    )
@api_view(['GET'])
def read_action_logs(request):
    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 10)
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    object_name = request.GET.get('object_name')
    object_id = request.GET.get('object_id')
    action = request.GET.get('action')
    username = request.GET.get('username')
    
    try:
        page = int(page)
        per_page = int(per_page)
    except ValueError:
        return Response({'error': 'Invalid page or per_page value'}, status=400)
    
    
    queryset = UserActionLog.objects.all().order_by('-timestamp')
    
    if start_date:
        queryset = queryset.filter(timestamp__gte = start_date)

    if end_date:
        queryset = queryset.filter(timestamp__lte = end_date)
        
    if action:
        action = action.split(',')
        queryset = queryset.filter(action__in = action)
    
    if object_name:
        queryset = search_string(queryset,"object_name", object_name)
        
    if object_id:
        queryset = search_string(queryset,"object_id", object_id)
    
    if username:
        queryset = search_string(queryset,"user__username", username)
    
    if per_page == -1:    
        serializer = UserActionLogSerializer(queryset, many=True)
        data = {
            'total_rows': len(queryset),
            'results': serializer.data
        }
    else:
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        serializer = UserActionLogSerializer(page_obj, many=True)
        data = {
            'page': page,
            'per_page': per_page,
            'total_pages': paginator.num_pages,
            'total_rows': paginator.count,
            'results': serializer.data
        }
        
    return Response(data)



# -------------------EMAIL_TEMPLATE--------------------
@swagger_auto_schema(
        method='GET',
        manual_parameters=[
            openapi.Parameter('name', in_=openapi.IN_QUERY, type=openapi.TYPE_STRING, description='search name'),
        ],
        responses={
            200: openapi.Response('Successful Response', TemplateExportSerializer(many=True)),
        },
    )
@api_view(['GET'])
def read_email_template(request):
    if request.method == 'GET':
        name_search = request.GET.get('name')
        queryset = Email_Template.objects.all()
                
        if name_search:
            queryset = search_string(queryset, 'name', name_search)
    
        serializer = EmailTemplateSerializer(queryset, many=True)
        data = serializer.data
        # for template in data:
        #     file_path = f'/home/mkt-en/ecom_operation/dashboard/static/template_email/{template["file_name"]}'
        #     with open(file_path, 'r', encoding='utf-8') as file:
        #         # Read the content of the file
        #         html_content = file.read()
        #         template['html'] = html_content
        return Response({'results':data }, status=200)

@api_view(['PUT', 'GET', 'DELETE'])
def rud_an_email_template(request, template_id):
    template = get_object_or_404(Email_Template, id=template_id)
    
    if request.method == 'GET':
        serializer = EmailTemplateSerializer(template)
        data = serializer.data
        
        return Response(data)
    
    elif request.method == 'PUT': 
        update_data = request.data
        html_content = update_data.pop('html')
        
        serializer = EmailTemplateSerializer(template, data=update_data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        else:
            return Response({'error': serializer.errors}, status=400)

    elif request.method == 'DELETE':
        template.delete()
        return Response(status=200)

@swagger_auto_schema(
        method='POST',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'order_id': openapi.Schema(type=openapi.TYPE_STRING),
                'email_template': openapi.Schema(type=openapi.TYPE_INTEGER)
            },
            required=['order_id', 'email_template']  # Add required fields
        ),
        responses={
            200: openapi.Response('Success'),
            400: 'Bad Request',
        },
    )
@api_view(['POST'])
def send_mail(request):  
    order_ids = request.data['order_id'].split(',')
    orders = Order.objects.filter(order_id__in = order_ids)
    sites = Site.objects.filter(site_id__in=orders.values_list('site_id',flat=True).distinct())
    for site in sites:
        if site.email == None:
            return Response({'error': f"Failed to send email because site {site.site_id} not have email"}, status=400)
    email_template = Email_Template.objects.get(id = request.data['email_template'])
    
    error_email = []
    for order in orders:
        try:
            send_email(order, email_template, order.site_id.email, order.email)
        except Exception as e:
            print(e)
            error_email.append(order.order_id)
    
    if error_email:
        return Response({'error': f'Failed to send email with Order IDs {error_email}'}, status=400)    
    else:
        return Response({'scucces': f'Send Email Success'}, status=200)

@swagger_auto_schema(
    method='POST',
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['name', 'subject', 'condition', 'content'],
        properties={
            'name': openapi.Schema(type=openapi.TYPE_STRING),
            'subject': openapi.Schema(type=openapi.TYPE_STRING),
            'condition': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'order_number': openapi.Schema(type=openapi.TYPE_STRING),
                    'tkn_status': openapi.Schema(type=openapi.TYPE_STRING),
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'sku': openapi.Schema(type=openapi.TYPE_STRING),
                    'date_paid_to_now': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'comparison': openapi.Schema(type=openapi.TYPE_STRING),
                            'value': openapi.Schema(type=openapi.TYPE_INTEGER),
                        }
                    ),
                    'tkn_created_to_now': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'comparison': openapi.Schema(type=openapi.TYPE_STRING),
                            'value': openapi.Schema(type=openapi.TYPE_INTEGER),
                        }
                    ),
                    'tkn_updated_to_now': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'comparison': openapi.Schema(type=openapi.TYPE_STRING),
                            'value': openapi.Schema(type=openapi.TYPE_INTEGER),
                        }
                    ),
                    'tkn_active_to_now': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'comparison': openapi.Schema(type=openapi.TYPE_STRING),
                            'value': openapi.Schema(type=openapi.TYPE_INTEGER),
                        }
                    ),
                }
            ),
            'content': openapi.Schema(type=openapi.TYPE_STRING),
        },
    )
)
@api_view(['GET','POST'])
def read_or_create_automail(request):
    if request.method == 'GET':
        name_search = request.GET.get('name')
        queryset = Auto_Email_Template.objects.all()
        
        if name_search:
            queryset = queryset.filter(name__icontains = name_search)
        
        serializer = AutoEmailTemplateSerializer(queryset, many=True)
        return Response({'results': serializer.data}, status=200)
    
    if request.method == 'POST':
        serializer = AutoEmailTemplateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'success': 'Template create successful'}, status=200)
        else:
            return Response({'error': 'Invalid data provided'}, status=400)

@api_view(['PUT', 'GET', 'DELETE'])
def rud_an_automail(request, automail_id):
    template = get_object_or_404(Auto_Email_Template, id=automail_id)
    
    if request.method == 'GET':
        serializer = AutoEmailTemplateSerializer(template)
        return Response(serializer.data)
    
    elif request.method == 'PUT': 
        serializer = AutoEmailTemplateSerializer(template, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        else:
            return Response({'error': serializer.errors}, status=400)

    elif request.method == 'DELETE':
        template.delete()
        return Response(status=200)


# ----------------CONTACT_FORM------------------------
@api_view(['POST'])
def upload_image(request):
    serializer = UploadedImageSerializer(data=request.data)
    if serializer.is_valid():
        instance = serializer.save()
        image_url = request.build_absolute_uri(instance.image.url)
        
        # Return the URL of the uploaded image in the response
        return Response({'image_url': image_url}, status=200)
    
    else:
        return Response(serializer.errors, status=400)
    
# ---------------------TICKET----------------------------
@api_view(['GET','POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def read_or_create_ticket(request):
    if request.method == 'GET':
        page = request.GET.get('page', 1)
        per_page = request.GET.get('per_page', 10)
        order_id = request.GET.get('order_id')
        
        try:
            page = int(page)
            per_page = int(per_page)
        except ValueError:
            return Response({'error': 'Invalid page or per_page value'}, status=400)
        
        queryset = Ticket.objects.all()
        
       
        if order_id:
            order_id = order_id.split(',')
            queryset = queryset.filter(order_id__in = order_id)
        
        if per_page == -1:    
            serializer = TicketSerializer(queryset, many=True)
            data = {
                'total_rows': len(queryset),
                'results': serializer.data
            }
        else:
            paginator = Paginator(queryset, per_page)
            page_obj = paginator.get_page(page)
            serializer = TicketSerializer(page_obj, many=True)
            data = {
                'page': page,
                'per_page': per_page,
                'total_pages': paginator.num_pages,
                'total_rows': paginator.count,
                'results': serializer.data
            }
        
        return Response(data, status=200)
    
    if request.method == 'POST':
        try:
            data = request.data
            order = get_object_or_404(Order, order_id=data['order_id'])
            Ticket.objects.update_or_create(
                ticket_id = data['ticket_id'],
                defaults = {
                    'order_id': order, 
                    'date_created': data['date_created']
                }
            )
            return Response({'success': 'Ticket created successfully'})
        except Exception as e:
            return Response({'error': f'Failed to create ticket because {e}'}, status=500)

@api_view(['PUT'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def rud_a_ticket(request,ticket_id):
    if request.method == 'PUT':
        ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
        try:
            serializer = TicketSerializer(ticket, data=request.data) 
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=200)
            else:
                return Response({'error': serializer.errors}, status=400)


        except Exception as e:
            return Response({'error': f'Failed to update ticket because {e}'}, status=400)