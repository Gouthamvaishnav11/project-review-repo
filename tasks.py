import frappe
from frappe.utils import getdate, add_days, now_datetime, get_first_day
from datetime import date
import calendar


def get_fy_start_date(posting_date):
	"""Get Financial Year start date (April 1) for given posting date.
	FY: April to March (e.g., April 2025 to March 2026)
	"""
	posting_date = getdate(posting_date)
	if posting_date.month >= 4:  # April or later
		return date(posting_date.year, 4, 1)
	else:  # Jan, Feb, March
		return date(posting_date.year - 1, 4, 1)


def get_last_month_payroll_for_cache(company, posting_date):
	"""Get total payroll amount from last month's GL entries (account 581000)."""
	try:
		posting_date = getdate(posting_date)
		
		# Calculate last month's date range dynamically
		if posting_date.month == 1:  # January
			last_month_start = date(posting_date.year - 1, 12, 1)
			last_month_end = date(posting_date.year - 1, 12, 31)
		else:
			last_month_start = date(posting_date.year, posting_date.month - 1, 1)
			# Get last day of previous month
			_, last_day = calendar.monthrange(posting_date.year, posting_date.month - 1)
			last_month_end = date(posting_date.year, posting_date.month - 1, last_day)
		
		# Get account details for payroll (account_number = '581000')
		acc = frappe.db.sql(
			"""
			SELECT name, lft, rgt
			FROM `tabAccount`
			WHERE company = %s AND account_number = '581000'
			ORDER BY name
			LIMIT 1
			""",
			(company,),
			as_dict=True,
		)
		if not acc:
			return 0.0
		lft, rgt = int(acc[0]["lft"]), int(acc[0]["rgt"])
		
		# Get sum of (debit - credit) for last month
		row = frappe.db.sql(
			"""
			SELECT
				COALESCE(SUM(gl.debit - gl.credit), 0) AS total_payroll
			FROM `tabGL Entry` gl
			JOIN `tabAccount` a ON a.name = gl.account AND a.company = gl.company
			WHERE gl.company = %s
				AND a.lft >= %s AND a.rgt <= %s
				AND gl.posting_date BETWEEN %s AND %s
				AND gl.docstatus = 1
				AND IFNULL(gl.is_cancelled, 0) = 0
			""",
			(company, lft, rgt, last_month_start, last_month_end),
			as_dict=True,
		)
		
		if not row:
			return 0.0
		return float(row[0].get("total_payroll") or 0)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Last Month Payroll Error")
		return 0.0


def refresh_drr_cache():
	"""Refresh DRR Cache - Frappe scheduler automatically logs execution"""
	try:
		today = getdate()
		one_month_ago = add_days(today, -30)
		
		frappe.db.sql("DELETE FROM `tabDRR Cache` WHERE posting_date < %s", one_month_ago)
		
		companies = frappe.get_all("Company", pluck="name")
		
		for company in companies:
			for i in range(31):
				date = add_days(today, -i)
				cache_drr_data(str(date), company)
		
		frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "DRR Cache Refresh Error")
		raise  # Re-raise so Frappe logs it as Failed


def cache_drr_data(date, company):
	try:
		posting_date = getdate(date)
		month_start = get_first_day(posting_date)
		year_start = getdate(f"{posting_date.year}-01-01")

		def get_fb_consumption_rollup():
			# Account 510000 is a group account; GL is posted to leaf children.
			# ERPNext UI rolls-up balances by summing the whole subtree.
			acc = frappe.db.sql(
				"""
				SELECT name, lft, rgt
				FROM `tabAccount`
				WHERE company = %s AND account_number = '510000'
				ORDER BY name
				LIMIT 1
				""",
				(company,),
				as_dict=True,
			)
			if not acc:
				return {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0}
			lft, rgt = int(acc[0]["lft"]), int(acc[0]["rgt"])

			row = frappe.db.sql(
				"""
				SELECT
					COALESCE(SUM(CASE WHEN gl.posting_date = %(posting_date)s THEN (gl.debit - gl.credit) ELSE 0 END), 0) AS prev_date,
					COALESCE(SUM(CASE WHEN gl.posting_date BETWEEN %(month_start)s AND %(posting_date)s THEN (gl.debit - gl.credit) ELSE 0 END), 0) AS mtd,
					COALESCE(SUM(CASE WHEN gl.posting_date BETWEEN %(year_start)s AND %(posting_date)s THEN (gl.debit - gl.credit) ELSE 0 END), 0) AS ytd
				FROM `tabGL Entry` gl
				JOIN `tabAccount` a ON a.name = gl.account AND a.company = gl.company
				WHERE gl.company = %(company)s
					AND a.lft >= %(lft)s AND a.rgt <= %(rgt)s
					AND gl.docstatus = 1
					AND IFNULL(gl.is_cancelled, 0) = 0
				""",
				{
					"company": company,
					"lft": lft,
					"rgt": rgt,
					"posting_date": posting_date,
					"month_start": month_start,
					"year_start": year_start,
				},
				as_dict=True,
			)
			if not row:
				return {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0}
			r = row[0]
			return {
				"prev_date": float(r.get("prev_date") or 0),
				"mtd": float(r.get("mtd") or 0),
				"ytd": float(r.get("ytd") or 0),
			}

		def get_payroll_rollup():
			"""Calculate payroll using prorated formula based on last month's payroll."""
			# Get last month's payroll for prorated calculation
			last_month_payroll = get_last_month_payroll_for_cache(company, posting_date)

			# Calculate days in current month (handles leap years)
			days_in_current_month = calendar.monthrange(posting_date.year, posting_date.month)[1]

			# Calculate daily rate
			if days_in_current_month > 0 and last_month_payroll > 0:
				daily_rate = last_month_payroll / days_in_current_month
			else:
				daily_rate = 0.0

			# Calculate days elapsed in current month
			days_elapsed = posting_date.day

			# Calculate Prev Date and MTD using prorated formula
			prev_date = daily_rate
			mtd = daily_rate * days_elapsed

			# Get YTD from Financial Year start (April 1) to current date
			fy_start = get_fy_start_date(posting_date)

			# Get account details for YTD calculation
			acc = frappe.db.sql(
				"""
				SELECT name, lft, rgt
				FROM `tabAccount`
				WHERE company = %s AND account_number = '581000'
				ORDER BY name
				LIMIT 1
				""",
				(company,),
				as_dict=True,
			)
			if not acc:
				return {"prev_date": prev_date, "mtd": mtd, "ytd": 0.0}
			lft, rgt = int(acc[0]["lft"]), int(acc[0]["rgt"])

			# Get YTD from Financial Year start to posting date
			row = frappe.db.sql(
				"""
				SELECT
					COALESCE(SUM(CASE WHEN gl.posting_date BETWEEN %(fy_start)s AND %(posting_date)s THEN (gl.debit - gl.credit) ELSE 0 END), 0) AS ytd
				FROM `tabGL Entry` gl
				JOIN `tabAccount` a ON a.name = gl.account AND a.company = gl.company
				WHERE gl.company = %(company)s
					AND a.lft >= %(lft)s AND a.rgt <= %(rgt)s
					AND gl.docstatus = 1
					AND IFNULL(gl.is_cancelled, 0) = 0
				""",
				{
					"company": company,
					"lft": lft,
					"rgt": rgt,
					"posting_date": posting_date,
					"fy_start": fy_start,
				},
				as_dict=True,
			)
			if not row:
				return {"prev_date": prev_date, "mtd": mtd, "ytd": 0.0}
			r = row[0]
			return {
				"prev_date": prev_date,
				"mtd": mtd,
				"ytd": float(r.get("ytd") or 0),
			}
		
		def get_hk_consumption_rollup():
			# Account 546002 - HK Consumption
			# ERPNext UI rolls-up balances by summing the whole subtree.
			acc = frappe.db.sql(
				"""
				SELECT name, lft, rgt
				FROM `tabAccount`
				WHERE company = %s AND account_number = '546002'
				ORDER BY name
				LIMIT 1
				""",
				(company,),
				as_dict=True,
			)
			if not acc:
				return {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0}
			lft, rgt = int(acc[0]["lft"]), int(acc[0]["rgt"])

			row = frappe.db.sql(
				"""
				SELECT
					COALESCE(SUM(CASE WHEN gl.posting_date = %(posting_date)s THEN (gl.debit - gl.credit) ELSE 0 END), 0) AS prev_date,
					COALESCE(SUM(CASE WHEN gl.posting_date BETWEEN %(month_start)s AND %(posting_date)s THEN (gl.debit - gl.credit) ELSE 0 END), 0) AS mtd,
					COALESCE(SUM(CASE WHEN gl.posting_date BETWEEN %(year_start)s AND %(posting_date)s THEN (gl.debit - gl.credit) ELSE 0 END), 0) AS ytd
				FROM `tabGL Entry` gl
				JOIN `tabAccount` a ON a.name = gl.account AND a.company = gl.company
				WHERE gl.company = %(company)s
					AND a.lft >= %(lft)s AND a.rgt <= %(rgt)s
					AND gl.docstatus = 1
					AND IFNULL(gl.is_cancelled, 0) = 0
				""",
				{
					"company": company,
					"lft": lft,
					"rgt": rgt,
					"posting_date": posting_date,
					"month_start": month_start,
					"year_start": year_start,
				},
				as_dict=True,
			)
			if not row:
				return {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0}
			r = row[0]
			return {
				"prev_date": float(r.get("prev_date") or 0),
				"mtd": float(r.get("mtd") or 0),
				"ytd": float(r.get("ytd") or 0),
			}
		
		frappe.db.sql("""
			DELETE FROM `tabDRR Cache` 
			WHERE posting_date = %s AND company = %s
		""", (date, company))
		
		drr = frappe.db.get_value("DRR", {"posting_date": date, "company": company}, "name")
		
		if drr:
			rows = frappe.db.sql("""
				SELECT service_name, prev_date, mtd, ytd
				FROM `tabDRR Table`
				WHERE parent = %s
			""", drr, as_dict=True)
			
			data = {r["service_name"]: r for r in rows}
			total_rooms_physical = data.get("Total Rooms", {})  # Physical total rooms
			total_rooms = data.get("Available Rooms", {})  # Sellable rooms
			
			def calc_pct(val, total):
				return round((val / total * 100), 2) if total else 0
			
			# Total Rooms Physical (no percentage)
			d = total_rooms_physical
			insert_cache_row(
				date, company, "room", "total_rooms_physical",
				float(d.get("prev_date", 0)), 0,
				float(d.get("mtd", 0)), 0,
				float(d.get("ytd", 0)), 0
			)
			
			# Total Sellable Rooms (percentage against physical rooms)
			d = total_rooms
			insert_cache_row(
				date, company, "room", "total_rooms",
				float(d.get("prev_date", 0)), calc_pct(d.get("prev_date", 0), total_rooms_physical.get("prev_date", 0)),
				float(d.get("mtd", 0)), calc_pct(d.get("mtd", 0), total_rooms_physical.get("mtd", 0)),
				float(d.get("ytd", 0)), calc_pct(d.get("ytd", 0), total_rooms_physical.get("ytd", 0))
			)
			
			# Out of Service (no percentage)
			d = data.get("OOO Rooms", {})
			insert_cache_row(
				date, company, "room", "out_of_service",
				float(d.get("prev_date", 0)), 0,
				float(d.get("mtd", 0)), 0,
				float(d.get("ytd", 0)), 0
			)
			
			room_metrics = [
				("rooms_occupied", "Rooms Sold"),
				("complimentary", "Complimentary Rooms"),
				("house_use", "House Use Rooms")
			]
			
			for key, name in room_metrics:
				d = data.get(name, {})
				insert_cache_row(
					date, company, "room", key,
					float(d.get("prev_date", 0)), calc_pct(d.get("prev_date", 0), total_rooms.get("prev_date", 0)),
					float(d.get("mtd", 0)), calc_pct(d.get("mtd", 0), total_rooms.get("mtd", 0)),
					float(d.get("ytd", 0)), calc_pct(d.get("ytd", 0), total_rooms.get("ytd", 0))
				)
			
			revenue_metrics = [("arr", "ARR"), ("net_arr", "Net ARR"), ("revpar", "Revenue per available room (RevPAR)"), ("room_revenue", "Room Revenue")]
			for key, name in revenue_metrics:
				d = data.get(name, {})
				insert_cache_row(
					date, company, "room", key,
					float(d.get("prev_date", 0)), 0,
					float(d.get("mtd", 0)), 0,
					float(d.get("ytd", 0)), 0
				)

			# Total Room Revenue - now only room revenue, excluding AddOns
			revenue = data.get("Room Revenue", {})
			insert_cache_row(
				date, company, "room", "total_room_revenue",
				float(revenue.get("prev_date", 0)), 0,
				float(revenue.get("mtd", 0)), 0,
				float(revenue.get("ytd", 0)), 0
			)

			# AddOns Revenue - now cached as F&B component
			addons = data.get("AddOns Revenue", {})
			addons_prev = float(addons.get("prev_date", 0))
			addons_mtd = float(addons.get("mtd", 0))
			addons_ytd = float(addons.get("ytd", 0))
			insert_cache_row(date, company, "fb", "addons_revenue", addons_prev, 0, addons_mtd, 0, addons_ytd, 0)
		
		# Get item prices for utility services
		item_prices = frappe.db.sql("""
			SELECT item_code, price_list_rate
			FROM `tabItem Price`
			WHERE item_code IN ('SI000022', 'SI000021', 'SI000023', 'SI000024', 'GS010010')
		""", as_dict=True)
		price_map = {r["item_code"]: float(r["price_list_rate"] or 0) for r in item_prices}
		
		prev_date_data = frappe.db.sql("""
			SELECT ae.service, ae.service_name, SUM(ae.meter_reading) as units, SUM(ae.amount) as amount
			FROM `tabAccounting Entry` ae
			JOIN `tabUtility Meter Reading` umr ON ae.parent = umr.name
			WHERE umr.posting_date = %s AND umr.company = %s
			GROUP BY ae.service, ae.service_name
		""", (date, company), as_dict=True)
		
		mtd_data = frappe.db.sql("""
			SELECT ae.service_name, SUM(ae.amount) as amount
			FROM `tabAccounting Entry` ae
			JOIN `tabUtility Meter Reading` umr ON ae.parent = umr.name
			WHERE umr.posting_date BETWEEN %s AND %s AND umr.company = %s
			GROUP BY ae.service_name
		""", (month_start, posting_date, company), as_dict=True)
		
		ytd_data = frappe.db.sql("""
			SELECT ae.service_name, SUM(ae.amount) as amount
			FROM `tabAccounting Entry` ae
			JOIN `tabUtility Meter Reading` umr ON ae.parent = umr.name
			WHERE umr.posting_date BETWEEN %s AND %s AND umr.company = %s
			GROUP BY ae.service_name
		""", (year_start, posting_date, company), as_dict=True)
		
		prev_map = {r["service_name"]: {"amount": float(r["amount"]), "units": float(r["units"] or 0), "price": price_map.get(r["service"], 0)} for r in prev_date_data}
		mtd_map = {r["service_name"]: float(r["amount"]) for r in mtd_data}
		ytd_map = {r["service_name"]: float(r["amount"]) for r in ytd_data}
		
		services = ["Diesel Charges", "Electricity Charges", "LPG Charges/Gas Supply", "Solar Charges", "Water Charges"]
		total_prev = total_mtd = total_ytd = 0
		
		for svc in services:
			prev_data = prev_map.get(svc, {"amount": 0, "units": 0, "price": 0})
			mtd = mtd_map.get(svc, 0)
			ytd = ytd_map.get(svc, 0)
			insert_cache_row(date, company, "cost", svc, prev_data["amount"], 0, mtd, 0, ytd, 0, prev_data["units"], prev_data["price"])
			total_prev += prev_data["amount"]
			total_mtd += mtd
			total_ytd += ytd
		
		# Get OTA Commission from DRR Table and add to costs
		ota_prev = ota_mtd = ota_ytd = 0
		if drr:
			ota_data = data.get("OTA Commission", {})
			ota_prev = float(ota_data.get("prev_date", 0))
			ota_mtd = float(ota_data.get("mtd", 0))
			ota_ytd = float(ota_data.get("ytd", 0))
			insert_cache_row(date, company, "cost", "ota_commission", ota_prev, 0, ota_mtd, 0, ota_ytd, 0)

		# Payroll - Full time (roll-up for account 581000 subtree)
		payroll = get_payroll_rollup()
		payroll_prev = float(payroll.get("prev_date") or 0)
		payroll_mtd = float(payroll.get("mtd") or 0)
		payroll_ytd = float(payroll.get("ytd") or 0)
		insert_cache_row(date, company, "cost", "payroll_full_time", payroll_prev, 0, payroll_mtd, 0, payroll_ytd, 0)

		# F&B Consumption (roll-up for account 510000 subtree)
		fb = get_fb_consumption_rollup()
		fb_prev = float(fb.get("prev_date") or 0)
		fb_mtd = float(fb.get("mtd") or 0)
		fb_ytd = float(fb.get("ytd") or 0)
		insert_cache_row(date, company, "cost", "fb_consumption", fb_prev, 0, fb_mtd, 0, fb_ytd, 0)
		
		# HK Consumption (roll-up for account 546002 subtree)
		hk = get_hk_consumption_rollup()
		hk_prev = float(hk.get("prev_date") or 0)
		hk_mtd = float(hk.get("mtd") or 0)
		hk_ytd = float(hk.get("ytd") or 0)
		insert_cache_row(date, company, "cost", "hk_consumption", hk_prev, 0, hk_mtd, 0, hk_ytd, 0)
		
		# Total cost = Utilities + OTA Commission + Payroll + F&B Consumption + HK Consumption
		insert_cache_row(date, company, "cost", "total_cost", total_prev + ota_prev + payroll_prev + fb_prev + hk_prev, 0, total_mtd + ota_mtd + payroll_mtd + fb_mtd + hk_mtd, 0, total_ytd + ota_ytd + payroll_ytd + fb_ytd + hk_ytd, 0)

		# Cache F&B outlet data (this also caches total_fb_revenue)
		cache_outlet_data(date, company, month_start, year_start)

		# Update total_fb_revenue to include AddOns Revenue
		# Get the current total_fb_revenue from cache
		fb_total = frappe.db.sql("""
			SELECT prev_date_value, mtd_value, ytd_value
			FROM `tabDRR Cache`
			WHERE posting_date = %s AND company = %s AND metric_type = 'outlet' AND metric_name = 'total_fb_revenue'
		""", (date, company), as_dict=True)

		if fb_total:
			fb_total_prev = float(fb_total[0].get("prev_date_value", 0))
			fb_total_mtd = float(fb_total[0].get("mtd_value", 0))
			fb_total_ytd = float(fb_total[0].get("ytd_value", 0))

			# Add AddOns to total F&B revenue
			updated_fb_prev = fb_total_prev + addons_prev
			updated_fb_mtd = fb_total_mtd + addons_mtd
			updated_fb_ytd = fb_total_ytd + addons_ytd

			# Delete old total_fb_revenue entry
			frappe.db.sql("""
				DELETE FROM `tabDRR Cache`
				WHERE posting_date = %s AND company = %s AND metric_type = 'outlet' AND metric_name = 'total_fb_revenue'
			""", (date, company))

			# Insert updated total_fb_revenue
			insert_cache_row(date, company, "outlet", "total_fb_revenue", updated_fb_prev, 0, updated_fb_mtd, 0, updated_fb_ytd, 0)
		
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"DRR Cache Error: {date} - {company}")


def cache_outlet_data(date, company, month_start, year_start):
	"""Cache F&B outlet revenue data from DRR POS"""
	try:
		posting_date = getdate(date)
		
		# Get prev_date outlet data using Total Gross Sales (to match UI display)
		prev_outlets = frappe.db.sql("""
			SELECT dp.outlet_name, dpt.name1 as metric, dpt.prev_date, dpt.mtd, dpt.ytd
			FROM `tabDRR POS` dp
			JOIN `tabDRR POS Table` dpt ON dpt.parent = dp.name
			WHERE dp.posting_date = %s AND dp.company = %s AND dpt.name1 = 'Total Gross Sales'
		""", (date, company), as_dict=True)
		
		total_prev = total_mtd = total_ytd = 0
		
		for outlet in prev_outlets:
			prev_val = float(outlet.get("prev_date", 0) or 0)
			mtd_val = float(outlet.get("mtd", 0) or 0)
			ytd_val = float(outlet.get("ytd", 0) or 0)
			
			insert_cache_row(
				date, company, "outlet", outlet.get("outlet_name", "Unknown"),
				prev_val, 0, mtd_val, 0, ytd_val, 0
			)
			
			total_prev += prev_val
			total_mtd += mtd_val
			total_ytd += ytd_val
		
		# Insert total F&B revenue
		if prev_outlets:
			insert_cache_row(
				date, company, "outlet", "total_fb_revenue",
				total_prev, 0, total_mtd, 0, total_ytd, 0
			)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"DRR Cache Outlet Error: {date} - {company}")


def insert_cache_row(date, company, metric_type, metric_name, prev_val, prev_pct, mtd_val, mtd_pct, ytd_val, ytd_pct, prev_units=0, prev_price=0):
	frappe.db.sql("""
		INSERT INTO `tabDRR Cache` 
		(name, posting_date, company, metric_type, metric_name, prev_date_value, prev_date_percent, prev_units, prev_price, mtd_value, mtd_percent, ytd_value, ytd_percent, last_updated, owner, creation, modified, modified_by)
		VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Administrator', NOW(), NOW(), 'Administrator')
	""", (frappe.generate_hash(length=10), date, company, metric_type, metric_name, prev_val, prev_pct, prev_units, prev_price, mtd_val, mtd_pct, ytd_val, ytd_pct, now_datetime()))
