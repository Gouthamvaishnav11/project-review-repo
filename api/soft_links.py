import frappe

@frappe.whitelist()
def get_soft_linked_docs(doctype, docname):
    """
    Find docs soft-linked via custom_booking_id and customer.
    Used for UI connections panel.
    """
    doc = frappe.get_doc(doctype, docname)
    customer = doc.customer
    booking_id = doc.get("custom_booking_id") or doc.get("custom_folio_no") # SO uses custom_folio_no sometimes
    
    if not booking_id or not customer:
        return []

    results = []
    
    if doctype == "Sales Order":
        # Find related Sales Invoices
        sis = frappe.db.get_all("Sales Invoice", filters={
            "custom_booking_id": booking_id,
            "customer": customer,
            "name": ["!=", docname]
        }, fields=["name", "status", "docstatus", "posting_date", "grand_total"])
        
        for si in sis:
            results.append({
                "doctype": "Sales Invoice",
                "name": si.name,
                "status": si.status,
                "docstatus": si.docstatus,
                "date": si.posting_date,
                "amount": si.grand_total
            })
            
    elif doctype == "Sales Invoice":
        # Find related Sales Orders
        sos = frappe.db.get_all("Sales Order", filters={
            "custom_booking_id": booking_id,
            "customer": customer,
            "name": ["!=", docname]
        }, fields=["name", "status", "docstatus", "transaction_date", "grand_total"])
        
        for so in sos:
            results.append({
                "doctype": "Sales Order",
                "name": so.name,
                "status": so.status,
                "docstatus": so.docstatus,
                "date": so.transaction_date,
                "amount": so.grand_total
            })

    return results

def create_custom_fields():
    """Create necessary custom fields for soft-linking."""
    fields = [
        {
            "doctype": "Custom Field",
            "dt": "Sales Invoice",
            "fieldname": "custom_linked_sales_order",
            "label": "Linked Sales Order",
            "fieldtype": "Link",
            "options": "Sales Order",
            "insert_after": "custom_booking_id"
        }
    ]
    for field_data in fields:
        if not frappe.db.exists("Custom Field", f"{field_data['dt']}-{field_data['fieldname']}"):
            frappe.get_doc(field_data).insert()
            print(f"Created field {field_data['fieldname']} on {field_data['dt']}")
        else:
            print(f"Field {field_data['fieldname']} on {field_data['dt']} already exists")
