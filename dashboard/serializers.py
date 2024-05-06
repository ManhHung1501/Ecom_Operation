from rest_framework import serializers
from .models import Order, Order_Line_Item, Site, Batch, SKU, Shipping, Shipping_Detail, Variation, Template_Export, Notification, Product_Site, UserActionLog, Email_Template,Uploaded_Image,Auto_Email_Template, Ticket
        
        
class SKUSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKU
        fields = '__all__'
 
class VariationSerializer(serializers.ModelSerializer):
    product_id = serializers.ReadOnlyField(source='sku.product_id')
    price = serializers.SerializerMethodField()
    
    class Meta:
        model = Variation
        fields = '__all__' 
    
    def get_price(self, obj): 
        pr = Product_Site.objects.filter(product_id= obj.sku.product_id).first()
        return pr.price if pr != None else None

class ProductSiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product_Site
        fields = '__all__'
        
class SiteSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source='site_id')
    class Meta:
        model = Site
        fields = ['id','site_id','link','name','status']

class ShippingDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipping_Detail
        fields = '__all__'

class ShippingSerializer(serializers.ModelSerializer):
    shipping_details = ShippingDetailSerializer(many=True, read_only=True)
    id = serializers.ReadOnlyField(source='tracking_number')
    class Meta:
        model = Shipping
        fields = '__all__'

class OrderLineItemSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source='line_item_id')
    tracking_number = serializers.SerializerMethodField()
    order_number = serializers.ReadOnlyField(source='order_id.order_number')
    supplier = serializers.ReadOnlyField(source='batch_id.supplier')
    
    class Meta:
        model = Order_Line_Item
        fields = '__all__'
    
    def get_tracking_number(self, obj):
        return list(set(obj.shippings.values_list('tracking_number', flat=True).exclude(tracking_number=None)))

class OrderSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source='order_id')
    site_url = serializers.ReadOnlyField(source='site_id.link')
    tracking_number = serializers.SerializerMethodField()
    batch_id = serializers.SerializerMethodField()
    line_items = OrderLineItemSerializer(many=True, read_only=True)
    
    def get_tracking_number(self, obj):
        return list(set(obj.line_items.values_list('shippings__tracking_number', flat=True).exclude(shippings__tracking_number=None)))
    def get_batch_id(self, obj):
        return list(set(obj.line_items.values_list('batch_id__batch_id', flat=True).exclude(batch_id__batch_id=None)))
    
    class Meta:
        model = Order
        fields = '__all__'
        
class BatchSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source='batch_id')
    number_orders = serializers.SerializerMethodField()
    
    class Meta:
        model = Batch
        fields = '__all__'

    def get_number_orders(self, obj):
        return obj.number_orders
    
class TemplateExportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template_Export
        fields = '__all__'

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'

class UserActionLogSerializer(serializers.ModelSerializer):
    username = serializers.ReadOnlyField(source='user.username')
    
    class Meta:
        model = UserActionLog
        fields = '__all__'
        
class EmailTemplateSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Email_Template
        fields = '__all__' 
        
class AutoEmailTemplateSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Auto_Email_Template
        fields = '__all__'  
        
class UploadedImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Uploaded_Image
        fields = '__all__'

class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = '__all__'