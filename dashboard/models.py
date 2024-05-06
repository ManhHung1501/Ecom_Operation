from os import defpath
from django.db import models
from django.db.models import fields, Max
from django.db.models.enums import Choices
from django.db.models.fields import AutoField
from django.contrib.auth.models import User
from django.contrib import admin
from django.utils import timezone


class Site(models.Model):
    site_id = models.CharField(max_length = 8, primary_key=True)
    link = models.URLField(max_length = 200, unique= True)
    name = models.CharField(max_length=50, null = True)
    platform = models.CharField(max_length=255, default='WooCommerce')
    authentication = models.JSONField(max_length=255)
    status = models.CharField(max_length=50, default='Active')
    email = models.EmailField(max_length=254, null = True)
    auto_send_mail = models.IntegerField(default = 0)
    def __str__(self):
        return self.link
    def get_deferred_fields(self) -> site_id:
        return super().get_deferred_fields()

class Key_API(models.Model):
    code = models.CharField(max_length = 200, default= 'default')
    name = models.CharField(max_length = 200, unique= True)
    # type_api = models.CharField(max_length=255)
    authentication = models.JSONField()
    # status = models.IntegerField(default=1)
    def __str__(self):
        return self.name
    def get_deferred_fields(self) -> name:
        return super().get_deferred_fields()
    
class Variation(models.Model):
    product_site_id = models.CharField(max_length=255)
    product_site_name = models.CharField(max_length=255, null = True)
    site_id = models.ForeignKey("Site", to_field="site_id", on_delete=models.CASCADE)
    attributes_id = models.CharField(max_length=255, default ='NA')
    attributes = models.JSONField(null =True)
    meta_data = models.JSONField(null =True)
    # sku = models.CharField(max_length=255)
    sku = models.ForeignKey("SKU", to_field="sku", on_delete=models.CASCADE,related_name='variations')
    date_modified = models.DateTimeField(auto_now=False, auto_now_add=False)
    class Meta:
        unique_together = ('site_id', 'product_site_id', 'attributes_id')

class SKU(models.Model):
    sku = models.CharField(max_length=255, primary_key = True)
    product_id = models.CharField(max_length=255, null = True)
    attributes_id = models.CharField(max_length=255)
    attributes = models.JSONField(null = True)
    quantity = models.IntegerField(default = 0)
    cost = models.FloatField(default = 0)
    child_sku = models.CharField(max_length = 50, null = True)
    is_oldsku = models.IntegerField(default = 0)
    
class Order(models.Model):
    order_id = models.CharField(max_length=50, primary_key = True)
    site_id = models.ForeignKey("Site", verbose_name="site", to_field="site_id", on_delete=models.CASCADE, default = 'SEM')
    order_number = models.CharField(max_length=200)
    transaction_id = models.CharField(max_length=100, null = True)
    status = models.IntegerField(default = 0)
    payment_status = models.IntegerField(default = 0)
    is_dispute = models.IntegerField(default = 0)
    dispute_resolved = models.IntegerField(null = True)
    first_name = models.CharField(max_length=255, null = True)
    last_name = models.CharField(max_length=255, null = True)
    email = models.EmailField(max_length=254, null = True)
    phone = models.CharField(max_length=50, null = True)
    address_1 = models.TextField(null=True)
    address_2 = models.TextField(null=True)
    city = models.CharField(max_length=255, null = True)
    state_code = models.CharField(max_length=255, null = True)
    postcode = models.CharField(max_length=255, null = True)
    country_code = models.CharField(max_length=10, null = True)
    currency = models.CharField(max_length=5)
    shipping_first_name = models.CharField(max_length=255, null = True)
    shipping_last_name = models.CharField(max_length=255, null = True)
    shipping_phone = models.CharField(max_length=50, null = True)
    shipping_address_1 = models.CharField(max_length=255, null=True)
    shipping_address_2 = models.CharField(max_length=255, null=True)
    shipping_city = models.CharField(max_length=255, null = True)
    shipping_state_code = models.CharField(max_length=255, null = True)
    shipping_postcode = models.CharField(max_length=255, null = True)
    shipping_country_code = models.CharField(max_length=10, null = True)
    payment_method = models.CharField(max_length=255, null = True)
    payment_method_title = models.CharField(max_length=255, null = True)
    discount_amount = models.FloatField(default = 0)
    coupon_code = models.JSONField(null=True)
    refund_amount = models.FloatField(default = 0)
    shipping_amount = models.FloatField(default = 0)
    total_amount = models.FloatField(default = 0)
    date_paid = models.DateTimeField(auto_now=False, auto_now_add=False, null = True)
    date_created = models.DateTimeField(auto_now=False, auto_now_add=False)
    date_modified = models.DateTimeField(auto_now=False, auto_now_add=False)
    date_completed = models.DateTimeField(auto_now=False, auto_now_add=False, null = True)
    
    @property
    def number_items(self):
        return self.line_items.all().count()
    @property
    def number_items_approved(self):
        return self.line_items.filter(status = 1).count()
    @property
    def number_items_fulfilled(self):
        return self.line_items.filter(status__in=[2,3,4,5]).count()
    @property
    def number_items_shipping(self):
        return self.line_items.filter(status = 3).count()
    @property
    def number_items_completed(self):
        return self.line_items.filter(status = 4).count()
    @property
    def number_items_cancelled(self):
        return self.line_items.filter(status = 5).count()
    
    @property
    def last_confirm_sent(self):
        return self.sent_emails.filter(email_template__id=1).order_by('-date_sent').first()
    @property
    def last_processing_sent(self):
        return self.sent_emails.filter(email_template__id=2).order_by('-date_sent').first()
    @property
    def last_shipping_sent(self):
        return self.sent_emails.filter(email_template__id=3).order_by('-date_sent').first()
    @property
    def last_to_country_sent(self):
        return self.sent_emails.filter(email_template__id=4).order_by('-date_sent').first()
    @property
    def last_to_po_sent(self):
        return self.sent_emails.filter(email_template__id=5).order_by('-date_sent').first()
    @property
    def last_delivery_sent(self):
        return self.sent_emails.filter(email_template__id=6).order_by('-date_sent').first()
    @property
    def last_po2days_sent(self):
        return self.sent_emails.filter(email_template__id=7).order_by('-date_sent').first()
    @property
    def last_shipping_usps_sent(self):
        return self.sent_emails.filter(email_template__id=8).order_by('-date_sent').first()
    
    
    class Meta:
        indexes = [
                models.Index(fields=['date_created']),
                models.Index(fields=['date_paid']),
                models.Index(fields=['status'])
            ]
       
class Order_Line_Item(models.Model):
    line_item_id = models.CharField(max_length=255, primary_key = True)
    order_id = models.ForeignKey("Order", to_field="order_id", on_delete=models.CASCADE,related_name='line_items')
    batch_id = models.ForeignKey("Batch", to_field="batch_id", on_delete=models.CASCADE, null = True, blank = True, related_name='line_items')
    sku = models.ForeignKey("SKU", to_field="sku", on_delete=models.CASCADE)
    image_url = models.URLField(null=True)
    item_name = models.CharField(max_length=255, null = True, blank = True)
    quantity = models.IntegerField(default = 1)
    price = models.FloatField(default = 0)
    subtotal_amount = models.FloatField(default = 0)
    total_amount = models.FloatField(default = 0)
    status = models.IntegerField(default = 0)
    tag = models.IntegerField(default = 0)
    meta_data_id = models.JSONField(null = True)
    date_modified = models.DateTimeField(auto_now=False, auto_now_add=False)
    date_created = models.DateTimeField(auto_now=False, auto_now_add=False)

class Batch(models.Model):
    batch_id = models.AutoField(primary_key = True)
    supplier = models.CharField(max_length=255, null = True, blank = True)
    date_created = models.DateTimeField(default = timezone.now)
    date_modified = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=255, null = True, blank = True)
    status = models.IntegerField(default = 0)
    
    @property
    def number_items(self):
        return self.line_items.all().count()

    @property
    def number_orders(self):
        return self.line_items.values('order_id').distinct().count()
    
    @property
    def number_orders_fulfilled(self):
        return self.line_items.filter(shippings__tracking_number__isnull=False).values('order_id').distinct().count()
       
class Shipping(models.Model):
    tracking_number = models.CharField(max_length=255, primary_key=True)
    order_number = models.CharField(max_length=100, null = False)
    line_item_id = models.ManyToManyField('Order_Line_Item', related_name='shippings')
    courier_code = models.CharField(max_length=100, null = True)
    created_at = models.DateTimeField(auto_now=False, auto_now_add=False, null=True)
    update_date = models.DateTimeField(auto_now=False, auto_now_add=False, null=True)
    shipping_date = models.DateTimeField(auto_now=False, auto_now_add=False, null=True)
    archived = models.IntegerField(default = 0)
    delivery_status = models.IntegerField(default = 0)
    updating = models.IntegerField(default = 0)
    destination = models.CharField(max_length=10, null = True)
    original = models.CharField(max_length=10, null = True)
    weight = models.CharField(max_length=100, null = True)
    substatus = models.CharField(max_length=50, null = True)
    status_info = models.CharField(max_length=50, null = True)
    previously = models.CharField(max_length=50, null = True)
    destination_track_number = models.CharField(max_length=100, null = True)
    exchange_number = models.CharField(max_length=100, null = True)
    consignee = models.CharField(max_length=100, null = True)
    scheduled_delivery_date = models.DateTimeField(auto_now=False, auto_now_add=False, null=True)
    scheduled_address = models.CharField(max_length=255, null = True)
    lastest_checkpoint_time = models.DateTimeField(auto_now=False, auto_now_add=False, null=True)
    transit_time = models.IntegerField(null = True)
    stay_time = models.IntegerField(null = True)
    origin_info = models.JSONField(null = True)
    destination_info = models.JSONField(null = True)
    upload_to_site = models.IntegerField(default = 0)
    upload_to_payment_gateway = models.IntegerField(default = 0)
    valid = models.IntegerField(default = 1)
    
    class Meta:
        indexes = [
                models.Index(fields=['created_at']),
                models.Index(fields=['update_date']),
                models.Index(fields=['delivery_status'])
            ]
    
class Shipping_Detail(models.Model):  
    shipping_detail_id = models.AutoField(primary_key = True)
    tracking_number = models.ForeignKey("Shipping", to_field="tracking_number", on_delete=models.CASCADE, related_name='shipping_details')  
    checkpoint_date = models.DateTimeField(auto_now=False, auto_now_add=False)
    tracking_detail = models.TextField(null = True)
    location = models.CharField(max_length=255, null = True)
    checkpoint_delivery_status = models.CharField(max_length=50, null = True)
    checkpoint_delivery_substatus = models.CharField(max_length=50, null = True)
    origin_destination = models.IntegerField(default = 0)
    mail_to = models.CharField(max_length=255, null = True)
    data_sent = models.TextField(null = True)
    detail_index =  models.IntegerField(default = 0)
    class Meta:
        unique_together = ('tracking_number', 'detail_index')

class Supplier(models.Model):
    supplier_id = models.AutoField(primary_key = True)
    name = models.CharField(max_length=255, null = False)
    email = models.EmailField(max_length=254, null = True)
    phone = models.CharField(max_length=50, null = True)
    address = models.CharField(max_length=255, null = True)
    country = models.CharField(max_length=255, null = True)
    
class Product(models.Model):
    product_id = models.AutoField(primary_key = True)
    supplier = models.ForeignKey("Supplier", to_field="supplier_id", on_delete=models.CASCADE)
    product_name = models.CharField(max_length=255, null = True)
    date_created = models.DateTimeField(auto_now=False, auto_now_add=False)
    date_modified = models.DateTimeField(auto_now=False, auto_now_add=False)
    
class Product_Site(models.Model):
    product_id = models.CharField(max_length=255, null = True)
    site_id = models.ForeignKey("Site", to_field="site_id", on_delete=models.CASCADE)
    product_site_id = models.CharField(max_length=255, null = False)
    product_site_name = models.CharField(max_length=255, null = True)
    link = models.URLField(max_length = 200, null=True)
    price = models.FloatField(default = 0)
    date_created = models.DateTimeField(auto_now=False, auto_now_add=False, null=True)
    date_modified = models.DateTimeField(auto_now=False, auto_now_add=False, null=True)
    class Meta:
        unique_together = ('site_id', 'product_site_id')

class UserActionLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=255)
    object_name = models.CharField(max_length=255, null =True)
    object_id = models.CharField(max_length=255, null =True)
    details = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
class Template_Export(models.Model):
    name = models.CharField(max_length=255, unique=True, null=False)
    object_export = models.CharField(max_length=255, null=True)
    template = models.JSONField(null = True) 

class Notification(models.Model):
    type_noti = models.CharField(max_length=255, null=False)
    object_type = models.CharField(max_length=255, null=False)
    object_id = models.JSONField(null = True)
    details = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

class Email_Template(models.Model):
    name = models.CharField(max_length=255, null=False, unique=True)
    subject = models.CharField(max_length=255, null=True )
    file_name = models.CharField(max_length=255, null=False, unique=True)
    description = models.TextField(null=True)

class Email_Sent(models.Model):
    message_id = models.CharField(max_length=255, null=False, unique=True)
    order_id = models.ForeignKey("Order", to_field="order_id", on_delete=models.CASCADE,related_name='sent_emails')
    line_item = models.JSONField(null = True)
    email_template = models.ForeignKey("Email_Template", to_field="name", on_delete=models.CASCADE, null = True, blank = True, related_name='template')
    automail = models.ForeignKey("Auto_Email_Template", to_field="name", on_delete=models.CASCADE, null = True, blank = True, related_name='template')
    processed = models.JSONField(null = True) 
    dropped = models.JSONField(null = True) 
    delivered = models.JSONField(null = True) 
    deferred = models.JSONField(null = True) 
    bounce = models.JSONField(null = True)  
    open_event = models.JSONField(null = True) 
    click = models.JSONField(null = True) 
    date_sent= models.DateTimeField(default = timezone.now)

class Uploaded_Image(models.Model):
    image = models.ImageField(upload_to='uploads/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
class Auto_Email_Template(models.Model):
    name = models.CharField(max_length=255, null=False, unique=True)
    subject = models.CharField(max_length=255, null=True)
    condition = models.JSONField(null=False)
    content = models.TextField(null=False)

class Ticket(models.Model):
    ticket_id = models.CharField(max_length=255, null = False, unique = True)
    order_id = models.ForeignKey("Order", to_field="order_id", on_delete=models.CASCADE,related_name='tickets')
    date_created = models.DateTimeField()