import frappe

def sales_order_dashboard(data):
    if not data:
        data = {}
    if "transactions" not in data:
        data["transactions"] = []
        
    # Standard SO dashboard already includes SI via items
    # We add a custom section for clarity if needed, or just let standard handle it.
    # To make it show up in a NEW section, we can add it here.
    data["transactions"].append({
        "label": "Booking Links (Soft)",
        "items": ["Sales Invoice"]
    })
    return data

def sales_invoice_dashboard(data):
    if not data:
        data = {}
    if "transactions" not in data:
        data["transactions"] = []
        
    data["transactions"].append({
        "label": "Booking Links (Soft)",
        "items": ["Sales Order"]
    })
    
    if "non_standard_fieldnames" not in data:
        data["non_standard_fieldnames"] = {}
    data["non_standard_fieldnames"]["Sales Order"] = "custom_linked_sales_order"
    
    return data
