import frappe
from frappe.utils import getdate, get_first_day, add_days
from datetime import date
import calendar

def get_context(context):
	pass

@frappe.whitelist()
def get_default_company():
	try:
		return frappe.db.get_value("Company", {"abbr": "IN000004"}, "name")
	except Exception:
		return None

def is_within_cache_period(date):
	posting_date = getdate(date)
	one_month_ago = add_days(getdate(), -30)
	return posting_date >= one_month_ago

def get_from_cache(date, company):
	rows = frappe.db.sql("""
		SELECT metric_type, metric_name, prev_date_value, prev_date_percent, prev_units, prev_price, mtd_value, mtd_percent, ytd_value, ytd_percent
		FROM `tabDRR Cache`
		WHERE posting_date = %s AND company = %s
	""", (date, company), as_dict=True)
	
	if not rows:
		return None
	
	room_data = {}
	costs = []
	total_cost = {}
	outlets = []
	total_fb_revenue = {}
	ota_commission = {"prev_date": 0, "mtd": 0, "ytd": 0}
	fb_consumption = {"prev_date": 0, "mtd": 0, "ytd": 0}
	hk_consumption = {"prev_date": 0, "mtd": 0, "ytd": 0}
	payroll = {"prev_date": 0, "mtd": 0, "ytd": 0}
	addons_revenue = {"prev_date": 0, "mtd": 0, "ytd": 0}

	for row in rows:
		if row["metric_type"] == "room":
			if row["metric_name"] in ["arr", "net_arr", "revpar", "room_revenue", "total_room_revenue"]:
				room_data[row["metric_name"]] = {
					"prev_date": row["prev_date_value"],
					"mtd": row["mtd_value"],
					"ytd": row["ytd_value"]
				}
			else:
				room_data[row["metric_name"]] = {
					"prev_date": {"value": row["prev_date_value"], "percent": row["prev_date_percent"]},
					"mtd": {"value": row["mtd_value"], "percent": row["mtd_percent"]},
					"ytd": {"value": row["ytd_value"], "percent": row["ytd_percent"]}
				}
		elif row["metric_type"] == "cost":
			if row["metric_name"] == "total_cost":
				total_cost = {"prev_date": row["prev_date_value"], "mtd": row["mtd_value"], "ytd": row["ytd_value"]}
			elif row["metric_name"] == "ota_commission":
				ota_commission = {"prev_date": row["prev_date_value"], "mtd": row["mtd_value"], "ytd": row["ytd_value"]}
			elif row["metric_name"] == "fb_consumption":
				fb_consumption = {"prev_date": row["prev_date_value"], "mtd": row["mtd_value"], "ytd": row["ytd_value"]}
			elif row["metric_name"] == "hk_consumption":
				hk_consumption = {"prev_date": row["prev_date_value"], "mtd": row["mtd_value"], "ytd": row["ytd_value"]}
			elif row["metric_name"] == "payroll_full_time":
				payroll = {"prev_date": row["prev_date_value"], "mtd": row["mtd_value"], "ytd": row["ytd_value"]}
			else:
				costs.append({
					"name": row["metric_name"],
					"prev_date": row["prev_date_value"],
					"prev_units": row["prev_units"] or 0,
					"prev_price": row["prev_price"] or 0,
					"mtd": row["mtd_value"],
					"ytd": row["ytd_value"]
				})
		elif row["metric_type"] == "outlet":
			if row["metric_name"] == "total_fb_revenue":
				total_fb_revenue = {"prev_date": row["prev_date_value"], "mtd": row["mtd_value"], "ytd": row["ytd_value"]}
			else:
				outlets.append({
					"name": row["metric_name"],
					"prev_date": row["prev_date_value"],
					"mtd": row["mtd_value"],
					"ytd": row["ytd_value"]
				})
		elif row["metric_type"] == "fb":
			if row["metric_name"] == "addons_revenue":
				addons_revenue = {"prev_date": row["prev_date_value"], "mtd": row["mtd_value"], "ytd": row["ytd_value"]}

	# Return data if we have either room data or cost data
	if room_data or costs or outlets:
		return {"room_revenue": room_data, "addons_revenue": addons_revenue, "fb_consumption": fb_consumption, "hk_consumption": hk_consumption, "ota_commission": ota_commission, "payroll": payroll, "costs": costs, "total_cost": total_cost, "outlets": outlets, "total_fb_revenue": total_fb_revenue}
	return None

def get_utility_costs_direct(date, company):
	try:
		posting_date = getdate(date)
		month_start = get_first_day(posting_date)
		year_start = getdate(f"{posting_date.year}-01-01")
		
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
		
		costs = []
		total_prev = total_mtd = total_ytd = 0
		for svc in services:
			prev_data = prev_map.get(svc, {"amount": 0, "units": 0, "price": 0})
			mtd = mtd_map.get(svc, 0)
			ytd = ytd_map.get(svc, 0)
			costs.append({
				"name": svc,
				"prev_date": prev_data["amount"],
				"prev_units": prev_data["units"],
				"prev_price": prev_data["price"],
				"mtd": mtd,
				"ytd": ytd
			})
			total_prev += prev_data["amount"]
			total_mtd += mtd
			total_ytd += ytd
		
		return {"costs": costs, "total_cost": {"prev_date": total_prev, "mtd": total_mtd, "ytd": total_ytd}}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Utility Cost Error")
		return {"costs": [], "total_cost": {"prev_date": 0, "mtd": 0, "ytd": 0}}

def get_outlet_revenue_direct(date, company):
	"""Get F&B outlet revenue from DRR POS table"""
	try:
		metrics = (
			"Net Sales",
			"Food",
			"Alcoholic",
			"Non_alcoholic",
			"Non Chargeable Items Amount",
			"Discount Amount",
			"Total Gross Sales",
			"Total Tax",
		)
		
		pos_rows = frappe.db.sql(f"""
			SELECT p.outlet, p.outlet_name, pt.name1, pt.prev_date, pt.mtd, pt.ytd
			FROM `tabDRR POS` p
			JOIN `tabDRR POS Table` pt ON pt.parent = p.name
			WHERE p.posting_date = %s AND p.company = %s AND pt.name1 IN {metrics}
			ORDER BY p.outlet_name
		""", (date, company), as_dict=True)

		by_outlet = {}
		
		def _f(x):
			try:
				return float(x or 0)
			except Exception:
				return 0.0

		for r in pos_rows:
			outlet_name = r.get("outlet_name") or r.get("outlet")
			metric = r.get("name1")
			
			if outlet_name not in by_outlet:
				by_outlet[outlet_name] = {
					"name": outlet_name,
					"net_sales": {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0},
					"calc": {
						"food": {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0},
						"alcoholic": {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0},
						"non_alcoholic": {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0},
						"non_chargeable_items_amount": {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0},
						"discount_amount": {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0},
						"total_gross_sales": {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0},
						"total_tax": {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0},
						"raw_category_total": {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0},
					},
				}

			bucket = by_outlet[outlet_name]
			vals = {"prev_date": _f(r.get("prev_date")), "mtd": _f(r.get("mtd")), "ytd": _f(r.get("ytd"))}
			
			if metric == "Net Sales":
				bucket["net_sales"] = vals
			elif metric == "Food":
				bucket["calc"]["food"] = vals
			elif metric == "Alcoholic":
				bucket["calc"]["alcoholic"] = vals
			elif metric == "Non_alcoholic":
				bucket["calc"]["non_alcoholic"] = vals
			elif metric == "Non Chargeable Items Amount":
				bucket["calc"]["non_chargeable_items_amount"] = vals
			elif metric == "Discount Amount":
				bucket["calc"]["discount_amount"] = vals
			elif metric == "Total Gross Sales":
				bucket["calc"]["total_gross_sales"] = vals
			elif metric == "Total Tax":
				bucket["calc"]["total_tax"] = vals

		# Compute raw category totals and outlet totals
		total_prev = total_mtd = total_ytd = 0.0
		outlets = []
		for outlet in by_outlet.values():
			calc = outlet.get("calc", {})
			for k in ("prev_date", "mtd", "ytd"):
				calc["raw_category_total"][k] = (
					float(calc["food"].get(k, 0) or 0)
					+ float(calc["alcoholic"].get(k, 0) or 0)
					+ float(calc["non_alcoholic"].get(k, 0) or 0)
				)
			outlet["calc"] = calc
			# Use Total Gross Sales for total F&B revenue (to match UI display)
			total_prev += float(calc.get("total_gross_sales", {}).get("prev_date") or 0)
			total_mtd += float(calc.get("total_gross_sales", {}).get("mtd") or 0)
			total_ytd += float(calc.get("total_gross_sales", {}).get("ytd") or 0)
			outlets.append(outlet)

		# Keep stable ordering
		outlets.sort(key=lambda o: (o.get("name") or ""))

		return {
			"outlets": outlets,
			"total_fb_revenue": {"prev_date": total_prev, "mtd": total_mtd, "ytd": total_ytd},
		}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Outlet Revenue Error")
		return {"outlets": [], "total_fb_revenue": {"prev_date": 0, "mtd": 0, "ytd": 0}}


def get_fb_consumption_direct(date, company):
	try:
		posting_date = getdate(date)
		month_start = get_first_day(posting_date)
		year_start = getdate(f"{posting_date.year}-01-01")

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
		return {"prev_date": float(r.get("prev_date") or 0), "mtd": float(r.get("mtd") or 0), "ytd": float(r.get("ytd") or 0)}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "F&B Consumption Error")
		return {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0}


def get_payroll_direct(date, company):
	try:
		posting_date = getdate(date)
		
		# Get last month's payroll for prorated calculation
		last_month_payroll = get_last_month_payroll(company, posting_date)
		
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
		return {"prev_date": prev_date, "mtd": mtd, "ytd": float(r.get("ytd") or 0)}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Payroll Error")
		return {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0}


def get_fy_start_date(posting_date):
	"""Get Financial Year start date (April 1) for given posting date.
	FY: April to March (e.g., April 2025 to March 2026)
	"""
	posting_date = getdate(posting_date)
	if posting_date.month >= 4:  # April or later
		return date(posting_date.year, 4, 1)
	else:  # Jan, Feb, March
		return date(posting_date.year - 1, 4, 1)


def get_last_month_payroll(company, posting_date):
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


def get_hk_consumption_direct(date, company):
	try:
		posting_date = getdate(date)
		month_start = get_first_day(posting_date)
		year_start = getdate(f"{posting_date.year}-01-01")

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
		return {"prev_date": float(r.get("prev_date") or 0), "mtd": float(r.get("mtd") or 0), "ytd": float(r.get("ytd") or 0)}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "HK Consumption Error")
		return {"prev_date": 0.0, "mtd": 0.0, "ytd": 0.0}

def get_drr_data_direct(date, company):
	try:
		drr = frappe.db.get_value("DRR", {"posting_date": date, "company": company}, "name")
		room_data = {}
		
		if drr:
			rows = frappe.db.sql("""
				SELECT service_name, prev_date, mtd, ytd
				FROM `tabDRR Table`
				WHERE parent = %s
			""", drr, as_dict=True)
			
			data = {r["service_name"]: r for r in rows}
			
			total_rooms_physical = data.get("Total Rooms", {})  # Physical total rooms in hotel
			total_rooms = data.get("Available Rooms", {})  # Sellable rooms
			occupied = data.get("Rooms Sold", {})
			comp = data.get("Complimentary Rooms", {})
			hu = data.get("House Use Rooms", {})
			oos = data.get("OOO Rooms", {})
			arr = data.get("ARR", {})
			net_arr = data.get("Net ARR", {})
			revpar = data.get("Revenue per available room (RevPAR)", {})
			revenue = data.get("Room Revenue", {})
			addons = data.get("AddOns Revenue", {})
			
			def calc_pct(val, total):
				return round((val / total * 100), 2) if total else 0
			
			def build_metric(d, total_d, is_pct=True):
				return {
					"prev_date": {"value": float(d.get("prev_date", 0)), "percent": calc_pct(d.get("prev_date", 0), total_d.get("prev_date", 0)) if is_pct else 0},
					"mtd": {"value": float(d.get("mtd", 0)), "percent": calc_pct(d.get("mtd", 0), total_d.get("mtd", 0)) if is_pct else 0},
					"ytd": {"value": float(d.get("ytd", 0)), "percent": calc_pct(d.get("ytd", 0), total_d.get("ytd", 0)) if is_pct else 0}
				}
			
			room_data = {
				"total_rooms_physical": build_metric(total_rooms_physical, total_rooms_physical, is_pct=False),  # Physical total rooms (no %)
				"total_rooms": build_metric(total_rooms, total_rooms_physical),  # Sellable rooms
				"out_of_service": build_metric(oos, total_rooms_physical, is_pct=False),  # OOS not counted in percentage
				"rooms_occupied": build_metric(occupied, total_rooms),
				"complimentary": build_metric(comp, total_rooms),
				"house_use": build_metric(hu, total_rooms),
				"arr": {"prev_date": float(arr.get("prev_date", 0)), "mtd": float(arr.get("mtd", 0)), "ytd": float(arr.get("ytd", 0))},
				"net_arr": {"prev_date": float(net_arr.get("prev_date", 0)), "mtd": float(net_arr.get("mtd", 0)), "ytd": float(net_arr.get("ytd", 0))},
				"revpar": {"prev_date": float(revpar.get("prev_date", 0)), "mtd": float(revpar.get("mtd", 0)), "ytd": float(revpar.get("ytd", 0))},
				"room_revenue": {"prev_date": float(revenue.get("prev_date", 0)), "mtd": float(revenue.get("mtd", 0)), "ytd": float(revenue.get("ytd", 0))},
				"total_room_revenue": {
					"prev_date": float(revenue.get("prev_date", 0)),
					"mtd": float(revenue.get("mtd", 0)),
					"ytd": float(revenue.get("ytd", 0))
				}
			}
		
		# AddOns Revenue - now as separate F&B component
		addons_revenue = {
			"prev_date": float(addons.get("prev_date", 0)),
			"mtd": float(addons.get("mtd", 0)),
			"ytd": float(addons.get("ytd", 0))
		}
		
		# Get OTA Commission from DRR Table
		ota_commission = {"prev_date": 0, "mtd": 0, "ytd": 0}
		if drr:
			ota_data = data.get("OTA Commission", {})
			ota_commission = {
				"prev_date": float(ota_data.get("prev_date", 0)),
				"mtd": float(ota_data.get("mtd", 0)),
				"ytd": float(ota_data.get("ytd", 0))
			}
		
		utility_data = get_utility_costs_direct(date, company)
		fb_consumption = get_fb_consumption_direct(date, company)
		hk_consumption = get_hk_consumption_direct(date, company)
		payroll = get_payroll_direct(date, company)
		outlet_data = get_outlet_revenue_direct(date, company)

		# Add AddOns Revenue to total F&B revenue
		outlet_data["total_fb_revenue"]["prev_date"] += addons_revenue["prev_date"]
		outlet_data["total_fb_revenue"]["mtd"] += addons_revenue["mtd"]
		outlet_data["total_fb_revenue"]["ytd"] += addons_revenue["ytd"]

		# Add costs to total cost
		utility_data["total_cost"]["prev_date"] += ota_commission["prev_date"] + payroll["prev_date"] + fb_consumption["prev_date"] + hk_consumption["prev_date"]
		utility_data["total_cost"]["mtd"] += ota_commission["mtd"] + payroll["mtd"] + fb_consumption["mtd"] + hk_consumption["mtd"]
		utility_data["total_cost"]["ytd"] += ota_commission["ytd"] + payroll["ytd"] + fb_consumption["ytd"] + hk_consumption["ytd"]

		return {"room_revenue": room_data, "addons_revenue": addons_revenue, "fb_consumption": fb_consumption, "hk_consumption": hk_consumption, "ota_commission": ota_commission, "payroll": payroll, **utility_data, **outlet_data}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "DRR Report Error")
		return {"room_revenue": {}, "fb_consumption": {"prev_date": 0, "mtd": 0, "ytd": 0}, "hk_consumption": {"prev_date": 0, "mtd": 0, "ytd": 0}, "ota_commission": {"prev_date": 0, "mtd": 0, "ytd": 0}, "payroll": {"prev_date": 0, "mtd": 0, "ytd": 0}, "costs": [], "total_cost": {"prev_date": 0, "mtd": 0, "ytd": 0}, "outlets": [], "total_fb_revenue": {"prev_date": 0, "mtd": 0, "ytd": 0}}

@frappe.whitelist()
def get_drr_data(date, company):
	try:
		if is_within_cache_period(date):
			cached = get_from_cache(date, company)
			if cached and (cached.get("room_revenue") or cached.get("costs") or cached.get("outlets")):
				# Always fetch outlet data directly (needs detailed breakdown for dropdown)
				outlet_data = get_outlet_revenue_direct(date, company)
				cached["outlets"] = outlet_data.get("outlets", [])
				# Keep cached total_fb_revenue if it exists (includes AddOns Revenue)
				# Only use outlet total_fb_revenue if cached doesn't have it or it's empty
				cached_total_fb = cached.get("total_fb_revenue", {})
				if not cached_total_fb or (cached_total_fb.get("prev_date") == 0 and cached_total_fb.get("mtd") == 0 and cached_total_fb.get("ytd") == 0):
					cached["total_fb_revenue"] = outlet_data.get("total_fb_revenue", {"prev_date": 0, "mtd": 0, "ytd": 0})
				# Prefer cached fb_consumption (computed by DRR cache refresh). Only compute if missing.
				if not cached.get("fb_consumption"):
					cached["fb_consumption"] = get_fb_consumption_direct(date, company)
				# Prefer cached hk_consumption (computed by DRR cache refresh). Only compute if missing.
				if not cached.get("hk_consumption"):
					cached["hk_consumption"] = get_hk_consumption_direct(date, company)
				# Prefer cached payroll (computed by DRR cache refresh). Only compute if missing.
				if not cached.get("payroll"):
					cached["payroll"] = get_payroll_direct(date, company)
				cached["source"] = "cache"
				return cached
		
		result = get_drr_data_direct(date, company)
		result["source"] = "direct"
		return result
	except Exception:
		frappe.log_error(frappe.get_traceback(), "DRR Report Error")
		return {"room_revenue": {}, "addons_revenue": {"prev_date": 0, "mtd": 0, "ytd": 0}, "fb_consumption": {"prev_date": 0, "mtd": 0, "ytd": 0}, "hk_consumption": {"prev_date": 0, "mtd": 0, "ytd": 0}, "ota_commission": {"prev_date": 0, "mtd": 0, "ytd": 0}, "payroll": {"prev_date": 0, "mtd": 0, "ytd": 0}, "costs": [], "total_cost": {"prev_date": 0, "mtd": 0, "ytd": 0}, "outlets": [], "total_fb_revenue": {"prev_date": 0, "mtd": 0, "ytd": 0}, "source": "error"}
