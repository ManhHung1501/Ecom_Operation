import sys
import textwrap
sys.path.insert(0, '/home/mkt-en/ecom_operation')
import os
import django
# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecom_operation.settings')
django.setup()
from django.db import connection
from dashboard.models import Site
import pandas as pd


def import_site():
    
    cursor = connection.cursor()
    
    data = pd.read_excel('/home/mkt-en/ecom_operation/dashboard/etl/key.xlsx') 
    data['status'] = 'Active'
    data['platform'] = 'WooCommerce'
    data['name'] = data['id']
    data['link'] = 'https://' + data['domain']
    data['authentication'] = data.apply(lambda row: {'key':row['api_key'],'secret':row['api_secret']}, axis=1)
    Site.objects.bulk_create(
            [
            Site(
                site_id = item['id'],
                link = item['link'],
                name = item['name'],
                platform = item['platform'],
                authentication = item['authentication'],
                status = item['status']
            ) 
            for idx, item in data.iterrows()
            ],
            update_conflicts = True,
            update_fields= ['link','name', 'platform', 'authentication', 'status']
        )
    
import_site()