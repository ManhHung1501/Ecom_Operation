from jinja2 import Environment, FileSystemLoader
from urllib.parse import urlparse
import requests 
import re
import json


# send mail
def get_courier_dict(API_KEY):
    url = "https://api.trackingmore.com/v4/couriers/all"
    headers = {
        "Content-Type": "application/json",
        "Tracking-Api-Key": {API_KEY}
    }
    response = requests.get(url, headers=headers) 
    courier_dict = {}
    if response.status_code == 200:
        print("Request successful")
        courier_dict = {courier['courier_code']: courier for courier in response.json()['data']}
        sub_courier_map = {
                'GLS': '100305',
                'CDL': '100263',
                'HAILIFY': '100502',
                'JFK HAILIFY': '100502',
                'PIGGY': '100425',
                'PiggyShip': '100425',
                'AUSTRALIAN POSTAL CORPORATION': '1151',
                'Gofo': '100996',
                'Lasership': '100052',
                'CA-POST': '3041',
                'CN-EUB': '3011',
                'DFW UNI': '100134',
                'EVRI': '100331',
                'JFK PB': '21051',
                'LaserShip': '100052',
                'LAX OSM': '21051',
                'LAX PB': '21051',
                'LAX UNI': '100134',
                'MIA OSM': '21051',
                'MIA UNI': '100134',
                'OnTrac': '100049',
                'ORD PB': '21051',
                'ORD UNI': '100134',
                'UDS': '100217',
                'UniUni': '100134',
                'UPS': '100002',
                'US FHE': '190008',
                'USPS': '21051',
                'YunExpress': '190008'
            }
        sub_courier_input = ['GLS', 'CDL','HAILIFY','JFK HAILIFY','PIGGY','PiggyShip']
        for k,v in sub_courier_map.items():
            courier_url = 'https://t.17track.net/en#nums=******'
            if k in sub_courier_input:
                courier_url = courier_url + f'&fc={v}'
            courier_dict.update(
                {
                    k: {'courier_url': courier_url}
                }
            )
    return courier_dict
            
def send_html_email(api_key, subject,from_email, to_email, html_content):
    sendgrid_url = 'https://api.sendgrid.com/v3/mail/send'

    # Construct the request headers
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    # Construct the request payload
    payload = {
        'personalizations': [
            {
                'to': [{'email': to_email}],
                'subject': subject,
            },
        ],
        'from': {'email': from_email},
        'content': [{'type': 'text/html', 'value': html_content}],
    }
    try:
        response = requests.post(sendgrid_url, headers=headers, data=json.dumps(payload))
        return response.headers['X-Message-Id']
    except requests.exceptions.RequestException as e:
        print(f"Error sending email: {str(e)}")

def remove_chinese_characters(input_string):
        # Define a regular expression to match Chinese characters
        chinese_characters_pattern = re.compile('[\u4e00-\u9fa5]+')

        # Use the regular expression to replace Chinese characters with an empty string
        result = re.sub(chinese_characters_pattern, '', input_string)

        return result
    
def convert_metadata(input_list):
    result_string = ""
    for item in input_list:
        result_string += f"{item['key']} {item['value']} | "
    result_string = result_string[:-3]
    return result_string

def render_template_email(email_template, courier_dict, order, variation_df, line_item_id=None):
    # Create a Jinja2 environment with the template folder
    env = Environment(loader=FileSystemLoader('/home/mkt-en/ecom_operation/dashboard/static/template_email'))

    # Load the HTML template
    template = env.get_template(email_template.file_name)

    address_parts = [part for part in [order.address_1, order.address_2] if part is not None]
    full_address = ' '.join(address_parts)
    name_parts = [part for part in [order.first_name, order.last_name] if part is not None]
    full_name = ' '.join(name_parts)
    params = {
        'order': {
            'domain': urlparse(order.site_id.link).netloc,
            'order_number': order.order_number,
            'customer_name':  full_name,
            'subtotal': round(order.total_amount - order.shipping_amount, 2),
            'shipping': order.shipping_amount,
            'total_paid': order.total_amount,
            'email': order.email,
            'phone': order.phone,
            'address': full_address,
            'city': order.city,
            'state_code': order.state_code,
            'postcode': order.postcode,
            'country_code': order.country_code,
            'payment_method': order.payment_method.capitalize() if order.payment_method != None else None ,
            'date_paid': order.date_paid.date().strftime("%m/%d/%Y") if order.date_paid != None else None ,
        }
    }
    
    items = []
    line_items = order.line_items.all()
    if line_item_id != None:
        line_items = line_items.filter(line_item_id__in=line_item_id)
    for item in line_items:
        temp = {
                    'image_url': item.image_url,
                    'product_name': item.item_name,
                    'attributes': convert_metadata(variation_df[(variation_df['site_id']==order.site_id.site_id) & (variation_df['sku']==item.sku.sku)]['meta_data'].iloc[0]),
                    'price': item.price,
                    'quantity': item.quantity,
                    'total': item.total_amount,
                    'tracking_numbers': [
                        {
                            'tracking_number': tracking.tracking_number,
                            'tracking_url' : courier_dict.get(tracking.courier_code)['courier_url'].replace('******',tracking.tracking_number) if courier_dict.get(tracking.courier_code)['courier_url'] != None else None,
                        }
                        for tracking in item.shippings.all()
                    ]
                }
        tracking_numbers = []
        for shipping in item.shippings.all():
            sub_tracking = shipping.shipping_details.all().filter(tracking_detail__icontains="Shipment information received Last mile tracking number:").first()
            tk_number =  shipping.tracking_number
            courier_code = shipping.courier_code
            
            if sub_tracking:
                tracking_detail = sub_tracking.tracking_detail
                tracking_number_start = tracking_detail.find("Shipment information received Last mile tracking number:") + len("Shipment information received Last mile tracking number:")
                tracking_number_end = tracking_detail.find(" - Last mile tracking carrier:")
                tk_number = tracking_detail[tracking_number_start:tracking_number_end].strip()

                # Extracting carrier
                carrier_start = tracking_detail.find(" - Last mile tracking carrier:", tracking_number_end) + len(" - Last mile tracking carrier:")
                courier_code = remove_chinese_characters(tracking_detail[carrier_start:]).strip()
            tracking_numbers.append(
                {
                    'tracking_number': tk_number,
                    'courier_code': courier_code,
                    'tracking_url' : courier_dict.get(courier_code)['courier_url'].replace('******',tk_number) if courier_dict.get(courier_code)['courier_url'] != None else None,
                }
            )
        temp['tracking_numbers'] = tracking_numbers
        items.append(temp)
    
    params['order']['items'] = items
            
    # Render the template with order information
    rendered_html = template.render(**params)

    return rendered_html

def render_template_with_tracking(order, tracking_number, email_template):
    env = Environment(loader=FileSystemLoader('/home/mkt-en/ecom_operation/dashboard/static/template_email'))

    # Load the HTML template
    
    template = env.get_template(email_template.file_name)

    address_parts = [part for part in [order.address_1, order.address_2] if part is not None]
    full_address = ' '.join(address_parts)
    name_parts = [part for part in [order.first_name, order.last_name] if part is not None]
    full_name = ' '.join(name_parts)
    
    params = {
        'order': {
            'domain': urlparse(order.site_id.link).netloc,
            'order_number': order.order_number,
            'customer_name':  full_name,
            'subtotal': round(order.total_amount - order.shipping_amount, 2),
            'shipping': order.shipping_amount,
            'total_paid': order.total_amount,
            'email': order.email,
            'phone': order.phone,
            'address': full_address,
            'city': order.city,
            'state_code': order.state_code,
            'postcode': order.postcode,
            'country_code': order.country_code,
            'payment_method': order.payment_method.capitalize() if order.payment_method != None else None ,
            'date_paid': order.date_paid.date().strftime("%m/%d/%Y") if order.date_paid != None else None ,
        }
    }
    
    
    with open('/home/mkt-en/ecom_operation/dashboard/etl/Carrier_New.json', "r") as file:
        courier_data = json.load(file)
        courier_data = {str(courier["key"]): courier for courier in courier_data}
    
    sub_courier_map = {
            'GLS': '100305',
            'CDL': '100263',
            'HAILIFY': '100502',
            'JFK HAILIFY': '100502',
            'PIGGY': '100425',
            'PiggyShip': '100425',
            'AUSTRALIAN POSTAL CORPORATION': '1151',
            'Gofo': '100996',
            'Lasership': '100052',
            'CA-POST': '3041',
            'CN-EUB': '3011',
            'DFW UNI': '100134',
            'EVRI': '100331',
            'JFK PB': '21051',
            'LaserShip': '100052',
            'LAX OSM': '21051',
            'LAX PB': '21051',
            'LAX UNI': '100134',
            'MIA OSM': '21051',
            'MIA UNI': '100134',
            'OnTrac': '100049',
            'ORD PB': '21051',
            'ORD UNI': '100134',
            'UDS': '100217',
            'UniUni': '100134',
            'UPS': '100002',
            'US FHE': '190008',
            'USPS': '21051',
            'YunExpress': '190008'
        }
    sub_courier_input = ['GLS', 'CDL','HAILIFY','JFK HAILIFY','PIGGY','PiggyShip']
    
    for k,v in sub_courier_map.items():
        courier_url = 'https://t.17track.net/en#nums=******'
        if k in sub_courier_input:
            courier_url = courier_url + f'&fc={v}'
        courier_data[v].update({'tracking_url': courier_url})

        
    tracking_detail = tracking_number.shipping_details.all().filter(tracking_detail__icontains="Shipment information received Last mile tracking number:").first().tracking_detail
    tracking_number_start = tracking_detail.find("Shipment information received Last mile tracking number:") + len("Shipment information received Last mile tracking number:")
    tracking_number_end = tracking_detail.find(" - Last mile tracking carrier:")
    sub_tracking = tracking_detail[tracking_number_start:tracking_number_end].strip()

    # Extracting carrier
    carrier_start = tracking_detail.find(" - Last mile tracking carrier:", tracking_number_end) + len(" - Last mile tracking carrier:")
    courier_code = remove_chinese_characters(tracking_detail[carrier_start:]).strip()
    
    courier_info = courier_data.get(sub_courier_map.get(courier_code))
    if courier_info:
        params['tracking'] = {
            'tracking_number': sub_tracking,
            'tracking_url': courier_info['tracking_url'].replace('******', sub_tracking),
            'courier_code': courier_info['_name'],
            'website': courier_info.get('_url'),
            'courier_phone': courier_info.get('_tel'),
        }
    
        rendered_html = template.render(**params)

        return rendered_html
    
    else:
        return None