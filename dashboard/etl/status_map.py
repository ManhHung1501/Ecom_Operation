payment_status = {
        'pending': 0,
        'paid': 1,
        'refunded': 2,
        'holding': 3
    }

item_status = {
        'checking': 0,
        'approved': 1,
        'fulfilled': 2,
        'shipping': 3,
        'delivered': 4,
        'cancelled': 5
    }

item_tag = {
    'unhold' : 0,
    'holding': 1
}

tracking_status_mapping = {
    'pending': 0,
    'notfound': 1,
    'expired': 2,
    'undelivered': 3,
    'exception': 4,
    'transit': 5,
    'pickup': 6,
    'delivered': 7,
    'InfoReceived': 8
}

status_mapping = {
    'need_approved' : 0,
    'approved' : 1, 
    'partially_fulfilled' : 2,
    'fulfilled': 3,
    'shipping' : 4,
    'active' : 5,
    'delivered' : 6,
    'cancelled' : 7,
    'on-hold': 8,
    'cs-hold' : 9         
}


sys_to_woo = {
    0 : 'pending',
    1 : 'processing',
    2 : 'processing',
    3 : 'processing',
    4 : 'shipped',
    5 : 'shipped',
    6 : 'completed',
    7 : 'cancelled',
    8 : 'on-hold',
    9 : 'cs-hold'
}
