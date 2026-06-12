import frappe

def create_entry():
    COMPANY  = "THE ECO SATVA - KOTA"
    DEFERRED = "Deferred Room Rev - IN000004"
    INCOME   = "410001 - Direct - Walk-In Customers - IN000004"
    AR_ACC   = "162600 - WalkIn- Trade Receivables - IN000004"
    CUSTOMER = "Walk-in Customer"
    BANK_ACC = "163113 - Hdfc Bank Limited -57500001594753-KOTA - IN000004"

    sgst = frappe.db.get_value("Account", {"account_number": "294300", "company": COMPANY}, ["name","tax_rate"])
    cgst = frappe.db.get_value("Account", {"account_number": "294001", "company": COMPANY}, ["name","tax_rate"])

    # 1. Sales Invoice on March 15th
    si = frappe.get_doc({
        "doctype": "Sales Invoice",
        "naming_series": "RWAK-.YY.-.#####",
        "customer": CUSTOMER,
        "posting_date": "2026-03-15",
        "due_date": "2026-03-17",
        "company": COMPANY,
        "debit_to": AR_ACC,
        "currency": "INR",
        "gst_category": "Unregistered",
        "place_of_supply": "08-Rajasthan",
        "taxes_and_charges": "Output GST In-state - IN000004",
        "cost_center": "Main - IN000004",
        "disable_rounded_total": True,
        "taxes": [
            {"charge_type":"On Net Total","account_head":sgst[0],"rate":sgst[1],"gst_tax_type":"sgst","description":"SGST"},
            {"charge_type":"On Net Total","account_head":cgst[0],"rate":cgst[1],"gst_tax_type":"cgst","description":"CGST"},
        ],
        "items": [
            {
                "item_code": "FO1002", "qty": 1, "rate": 1000,
                "income_account": INCOME, "deferred_revenue_account": DEFERRED,
                "service_start_date": "2026-03-15", "service_end_date": "2026-03-15", "enable_deferred_revenue": 1,
            },
            {
                "item_code": "FO1002", "qty": 1, "rate": 1000,
                "income_account": INCOME, "deferred_revenue_account": DEFERRED,
                "service_start_date": "2026-03-16", "service_end_date": "2026-03-16", "enable_deferred_revenue": 1,
            },
            {
                "item_code": "FO1002", "qty": 1, "rate": 1000,
                "income_account": INCOME, "deferred_revenue_account": DEFERRED,
                "service_start_date": "2026-03-17", "service_end_date": "2026-03-17", "enable_deferred_revenue": 1,
            }
        ],
    })
    si.insert(ignore_permissions=True)
    si.submit()
    frappe.db.commit()
    print("SINV Created:", si.name)

    # 2. Daily Journal Entries
    CC = "Main - IN000004"
    nights = [
        ("2026-03-15", 1000, "March 15th"),
        ("2026-03-16", 1000, "March 16th"),
        ("2026-03-17", 1000, "March 17th"),
    ]

    vouchers = [si.name]
    for dt, amt, label in nights:
        je = frappe.new_doc("Journal Entry")
        je.company = COMPANY
        je.posting_date = dt
        je.voucher_type = "Journal Entry"
        je.user_remark = f"Nightly Deferred Recognition – {label} | Ref: {si.name}"
        je.append("accounts", {"account": DEFERRED, "debit_in_account_currency": amt, "credit_in_account_currency": 0, "cost_center": CC})
        je.append("accounts", {"account": INCOME, "debit_in_account_currency": 0, "credit_in_account_currency": amt, "cost_center": CC})
        je.flags.ignore_mandatory = True
        je.save(ignore_permissions=True)
        je.submit()
        frappe.db.commit()
        vouchers.append(je.name)
        print(f"{label} JE: {je.name} | submitted")

    # 3. Payment Entry on check-out (March 17th)
    si.reload()
    pay_amt = si.outstanding_amount
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.posting_date = "2026-03-17"
    pe.company = COMPANY
    pe.party_type = "Customer"
    pe.party = CUSTOMER
    pe.paid_from = AR_ACC
    pe.paid_to = BANK_ACC
    pe.paid_amount = pay_amt
    pe.received_amount = pay_amt
    pe.reference_no = "CASH_FINAL_TEST"
    pe.reference_date = "2026-03-17"
    pe.source_exchange_rate = 1
    pe.target_exchange_rate = 1
    pe.append("references", {
        "reference_doctype": "Sales Invoice",
        "reference_name": si.name,
        "allocated_amount": pay_amt,
        "outstanding_amount": pay_amt,
        "total_amount": si.grand_total,
    })
    pe.save(ignore_permissions=True)
    pe.submit()
    frappe.db.commit()
    vouchers.append(pe.name)
    print("PE Created:", pe.name)
    
    with open('/home/kkrish/Desktop/kcs/development/my-frappe-bench/apps/ecohotels/ecohotels/vouchers_list.txt', 'w') as f:
        f.write(",".join(vouchers))
