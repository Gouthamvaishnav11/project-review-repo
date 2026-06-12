frappe.pages['drr-report'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Daily Revenue Report',
		single_column: true
	});

	wrapper.drr_report_page = page;
	$(page.body).html(get_filter_html() + '<div id="drr-report-container"></div>');

	const yesterday = frappe.datetime.add_days(frappe.datetime.get_today(), -1);

	wrapper.date_control = frappe.ui.form.make_control({
		parent: $('#drr-date-wrapper'),
		df: {
			fieldname: 'date',
			fieldtype: 'Date',
			default: yesterday,
			change: () => refresh_report(wrapper)
		},
		render_input: true
	});
	wrapper.date_control.set_value(yesterday);

	wrapper.company_control = frappe.ui.form.make_control({
		parent: $('#drr-company-wrapper'),
		df: {
			fieldname: 'company',
			fieldtype: 'Link',
			options: 'Company',
			default: frappe.defaults.get_user_default('Company'),
			placeholder: 'Select Hotel',
			change: () => refresh_report(wrapper)
		},
		render_input: true
	});

	frappe.call({
		method: 'ecohotels.ecohotels.page.drr_report.drr_report.get_default_company',
		callback: (r) => {
			if (r.message) {
				wrapper.company_control.set_value(r.message);
			}
		}
	});

	setTimeout(() => refresh_report(wrapper), 500);
}

function refresh_report(wrapper) {
	const date = wrapper.date_control?.get_value();
	const company = wrapper.company_control?.get_value();
	if (!date || !company) return;

	frappe.call({
		method: 'ecohotels.ecohotels.page.drr_report.drr_report.get_drr_data',
		args: { date, company },
		callback: (r) => {
			const data = r.message || {};
			$('#drr-report-container').html(get_report_html(data));
			// Outlet dropdown handlers
			$('#drr-report-container').off('click', '.outlet-row.expandable, .outlet-card.expandable');
			$('#drr-report-container').on('click', '.outlet-row.expandable, .outlet-card.expandable', function () {
				const outletName = $(this).data('outlet');
				const isExpanded = $(this).hasClass('expanded');
				$(this).toggleClass('expanded', !isExpanded);
				$(`.outlet-calc-row[data-parent="${outletName}"]`).toggle(!isExpanded);
				$(`.outlet-calc-card-row[data-parent="${outletName}"]`).toggle(!isExpanded);
			});
			// Show data source in console for debugging
			console.log(`📊 DRR Data Source: ${data.source || 'unknown'} | Date: ${date} | Company: ${company}`);
		}
	});
}

function get_filter_html() {
	return `
		<div class="drr-filters-container">
			<div class="drr-filter-row">
				<div class="drr-filter-item" id="drr-date-wrapper"></div>
				<div class="drr-filter-item" id="drr-company-wrapper"></div>
			</div>
		</div>
		<style>
			.drr-filters-container {
				max-width: 900px;
				margin: 0 auto;
				padding: 20px 20px 0 20px;
			}
			.drr-filter-row {
				display: flex;
				gap: 16px;
				align-items: flex-end;
			}
			.drr-filter-item {
				min-width: 200px;
			}
			.drr-filter-item .form-group {
				margin-bottom: 0;
			}
			.drr-filter-item .control-label {
				display: none;
			}
			.drr-filter-item .form-control {
				background: var(--subtle-fg);
				border: 1px solid var(--border-color);
				border-radius: var(--border-radius);
				padding: 8px 12px;
				font-size: 13px;
			}
			@media (max-width: 768px) {
				.drr-filters-container { padding: 12px; }
				.drr-filter-row { flex-direction: column; gap: 10px; }
				.drr-filter-item { min-width: 100%; width: 100%; }
			}
		</style>
	`;
}

function get_report_html(response) {
	const data = response.room_revenue || {};
	const costs = response.costs || [];
	const totalCost = response.total_cost || {};
	const fbConsumption = response.fb_consumption || {};
	const hkConsumption = response.hk_consumption || {};
	const otaCommission = response.ota_commission || {};
	const payroll = response.payroll || {};
	const outlets = response.outlets || [];
	const totalFbRevenue = response.total_fb_revenue || {};
	const addonsRevenue = response.addons_revenue || {};
	const hasRoomData = data && Object.keys(data).length > 0;
	const hasCostData = costs && costs.length > 0;
	const hasOtaCommission = otaCommission && (otaCommission.prev_date || otaCommission.mtd || otaCommission.ytd);
	const hasHkConsumption = hkConsumption && (hkConsumption.prev_date || hkConsumption.mtd || hkConsumption.ytd);
	const hasPayroll = payroll && (payroll.prev_date || payroll.mtd || payroll.ytd);
	const hasOutletData = outlets && outlets.length > 0;
	const hasAddonsRevenue = addonsRevenue && (addonsRevenue.prev_date || addonsRevenue.mtd || addonsRevenue.ytd);

	if (!hasRoomData && !hasCostData && !hasOutletData) {
		return '<div class="drr-container"><p class="text-muted text-center">No data available for selected date and company</p></div>';
	}

	const fmt = (v) => v ? v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00';
	const fmtCur = (v) => '₹ ' + fmt(v);
	const fmtPct = (d) => `${fmt(d?.value || 0)} - (${(d?.percent || 0).toFixed(1)}%)`;
	const fmtVal = (d) => fmt(d?.value || 0);  // Value only, no percentage
	const getCalc = (o) => o?.calc || {};
	const getNum = (obj, key) => (obj && obj[key] != null) ? Number(obj[key]) : 0;
	const getValueRow = (c, field, k) => fmtCur(getNum(c[field], k));
	const getRawTotal = (c, k) => {
		const raw = getNum(c.raw_category_total, k);
		if (raw) return raw;
		return getNum(c.food, k) + getNum(c.alcoholic, k) + getNum(c.non_alcoholic, k);
	};
	const getOutletRevenue = (o, k) => {
		const c = getCalc(o);
		const gross = getNum(c.total_gross_sales, k);
		if (gross) return gross;
		const net = o.net_sales || {};
		return getNum(net, k) || getNum(o, k);
	};
	const getDeductionsTotal = (c, k) => {
		const nonChg = getNum(c.non_chargeable_items_amount, k);
		const disc = getNum(c.discount_amount, k);
		return nonChg + disc;
	};
	const fmtUtilityName = (c) => {
		const serviceName = c.name.replace(' Charges', '').replace('/Gas Supply', '');
		const units = Math.round(c.prev_units || 0);
		const price = fmt(c.prev_price || 0);
		return `Utility - ${serviceName} (${units}@${price})`;
	};

	const roomMetrics = [
		{ name: 'Total Rooms', key: 'total_rooms_physical', noPct: true },  // Physical total rooms
		{ name: 'Out of Service (OOS)', key: 'out_of_service', noPct: true },  // OOS not counted in sellable rooms
		{ name: 'Total Sellable Rooms', key: 'total_rooms' },
		{ name: 'Rooms Occupied(Paid)', key: 'rooms_occupied' },
		{ name: 'Complimentary', key: 'complimentary' },
		{ name: 'House Use (HU)', key: 'house_use' }
	];

	const revenueMetrics = [
		{ name: 'ARR', key: 'arr' },
		{ name: 'Net ARR', key: 'net_arr' },
		{ name: 'RevPar', key: 'revpar' },
		{ name: 'Room Revenue', key: 'room_revenue' }
	];

	let rowIdx = 1;

	return `
		<style>
			.drr-container { max-width: 900px; margin: 0 auto; padding: 20px; }
			.drr-section { background: var(--card-bg); border-radius: var(--border-radius-lg); box-shadow: var(--card-shadow); margin-bottom: 24px; overflow: hidden; border: 1px solid var(--border-color); }
			.drr-table { width: 100%; border-collapse: collapse; font-size: 13px; }
			.drr-table thead { background: var(--subtle-fg); }
			.drr-table th { padding: 12px 16px; text-align: right; font-weight: 600; color: var(--text-muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border-color); }
			.drr-table th:first-child { text-align: left; width: 5%; }
			.drr-table th:nth-child(2) { text-align: left; width: 35%; }
			.drr-table td { padding: 10px 16px; border-bottom: 1px solid var(--border-color); color: var(--text-color); }
			.drr-table td:first-child { text-align: center; color: var(--text-muted); font-size: 12px; }
			.drr-table td:nth-child(2) { text-align: left; }
			.drr-table td:not(:first-child):not(:nth-child(2)) { text-align: right; }
			.drr-table tbody tr:hover { background: var(--subtle-fg); }
			.drr-table .row-section-total { background: #e8f4fd; font-weight: 600; }
			.drr-table .row-section-total td { border-top: 2px solid var(--border-color); border-bottom: 2px solid var(--border-color); color: var(--text-color); padding: 12px 16px; }
			.drr-table .row-total { background: var(--subtle-fg); font-weight: 600; }
			.drr-table .row-total td { border-top: 2px solid var(--border-color); color: var(--text-color); padding: 12px 16px; }
			.drr-table .row-total-revenue { background: #e6f7e6; font-weight: 700; }
			.drr-table .row-total-revenue td { border-top: 2px solid #28a745; border-bottom: 2px solid #28a745; color: #28a745; padding: 12px 16px; }
			.drr-table .outlet-row.expandable { cursor: pointer; }
			.drr-table .outlet-row .expand-icon { display: inline-block; margin-left: 6px; transition: transform 0.15s; color: var(--text-muted); }
			.drr-table .outlet-row.expanded .expand-icon { transform: rotate(90deg); }
			.drr-table .outlet-calc-row td { font-size: 12px; color: var(--text-color); padding-top: 6px; padding-bottom: 6px; }
			.drr-table .outlet-calc-row td:nth-child(2) { padding-left: 28px; color: var(--text-muted); }
			.drr-table .outlet-calc-row.outlet-sep-row td { padding-top: 2px; padding-bottom: 2px; }
			.drr-table .outlet-calc-row.outlet-sep-row td:nth-child(2) { color: var(--text-muted); }
			.drr-table .outlet-calc-row.outlet-total-row td { font-weight: 600; background-color: #f5f5f5; }
			.drr-mobile { display: none; }
			@media (max-width: 768px) {
				.drr-container { padding: 10px; }
				.drr-section { border-radius: var(--border-radius); margin-bottom: 16px; }
				.drr-table { display: none; }
				.drr-mobile { display: block; }
				.drr-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 12px; margin-bottom: 10px; }
				.drr-card.outlet-card.expandable { cursor: pointer; }
				.drr-card .expand-icon { display: inline-block; margin-left: 6px; transition: transform 0.15s; color: var(--text-muted); }
				.drr-card.outlet-card.expanded .expand-icon { transform: rotate(90deg); }
				.drr-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; border-bottom: 1px solid var(--border-color); padding-bottom: 8px; }
				.drr-card-title { font-weight: 600; font-size: 13px; color: var(--text-color); }
				.drr-card-idx { font-size: 11px; color: var(--text-muted); background: var(--subtle-fg); padding: 2px 8px; border-radius: 10px; }
				.drr-card-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 12px; }
				.outlet-break-grid { display: grid; grid-template-columns: 1.3fr 1fr 1fr 1fr; gap: 6px 10px; font-size: 12px; margin-top: 8px; }
				.outlet-break-grid.outlet-calc-card-row { font-size: 12px; }
				.outlet-break-cell { padding: 3px 0; border-bottom: 1px dashed var(--border-color); }
				.outlet-break-cell.h { font-size: 11px; color: var(--text-muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; border-bottom: 1px solid var(--border-color); }
				.outlet-break-cell.label { color: var(--text-muted); }
				.outlet-break-cell.val { text-align: right; color: var(--text-color); font-weight: 500; }
				.outlet-break-cell.sep { border-bottom: 0; color: var(--text-muted); }
				.outlet-break-cell.total { font-weight: 700; border-bottom: 1px solid var(--border-color); background-color: #f5f5f5; padding: 4px 0; }
				.drr-card-label { color: var(--text-muted); }
				.drr-card-value { font-weight: 500; color: var(--text-color); text-align: right; }
				.drr-card.total { background: #e8f4fd; border-color: #b8d4f0; }
				.drr-card.total-revenue { background: #e6f7e6; border-color: #28a745; }
				.drr-card.total-revenue .drr-card-title { color: #28a745; }
				.drr-card.total-revenue .drr-card-value { color: #28a745; font-weight: 700; }
				.drr-card.cost-total { background: var(--subtle-fg); }
				.drr-section-title { font-size: 14px; font-weight: 700; color: var(--text-color); padding: 12px; background: var(--subtle-fg); margin: 0 -1px; border-bottom: 1px solid var(--border-color); }
			}
		</style>
		<div class="drr-container">
			<div class="drr-section">
				<table class="drr-table">
					<thead>
						<tr>
							<th>#</th>
							<th>Particulars</th>
							<th style="width: 20%">Prev Date</th>
							<th style="width: 20%">MTD</th>
							<th style="width: 20%">YTD</th>
						</tr>
					</thead>
					<tbody>
						${roomMetrics.map((m, i) => {
		const d = data[m.key] || {};
		const formatter = m.noPct ? fmtVal : fmtPct;
		return `<tr><td>${rowIdx++}</td><td>${m.name}</td><td>${formatter(d.prev_date)}</td><td>${formatter(d.mtd)}</td><td>${formatter(d.ytd)}</td></tr>`;
	}).join('')}
						${revenueMetrics.map((m) => {
		const d = data[m.key] || {};
		return `<tr><td>${rowIdx++}</td><td>${m.name}</td><td>${fmtCur(d.prev_date)}</td><td>${fmtCur(d.mtd)}</td><td>${fmtCur(d.ytd)}</td></tr>`;
	}).join('')}
						<tr class="row-section-total">
							<td>${rowIdx++}</td>
							<td>TOTAL ROOM REVENUE</td>
							<td>${fmtCur(data.total_room_revenue?.prev_date)}</td>
							<td>${fmtCur(data.total_room_revenue?.mtd)}</td>
							<td>${fmtCur(data.total_room_revenue?.ytd)}</td>
						</tr>
						${outlets.map((o) => {
		const c = getCalc(o);
		const hasCalc = !!(c && (c.food || c.alcoholic || c.non_alcoholic || c.total_gross_sales || c.total_tax));
		const net = o.net_sales || { prev_date: o.prev_date || 0, mtd: o.mtd || 0, ytd: o.ytd || 0 };
		return `
								<tr class="outlet-row ${hasCalc ? 'expandable' : ''}" data-outlet="${o.name}">
									<td>${rowIdx++}</td>
									<td>${o.name}${hasCalc ? '<span class="expand-icon">▶</span>' : ''}</td>
									<td>${fmtCur(getOutletRevenue(o, 'prev_date'))}</td>
									<td>${fmtCur(getOutletRevenue(o, 'mtd'))}</td>
									<td>${fmtCur(getOutletRevenue(o, 'ytd'))}</td>
								</tr>
								${hasCalc ? `
									<tr class="outlet-calc-row" data-parent="${o.name}" style="display:none;">
										<td></td>
										<td>Food</td>
										<td>${getValueRow(c, 'food', 'prev_date')}</td>
										<td>${getValueRow(c, 'food', 'mtd')}</td>
										<td>${getValueRow(c, 'food', 'ytd')}</td>
									</tr>
									<tr class="outlet-calc-row" data-parent="${o.name}" style="display:none;">
										<td></td>
										<td>Alcoholic</td>
										<td>${getValueRow(c, 'alcoholic', 'prev_date')}</td>
										<td>${getValueRow(c, 'alcoholic', 'mtd')}</td>
										<td>${getValueRow(c, 'alcoholic', 'ytd')}</td>
									</tr>
									<tr class="outlet-calc-row" data-parent="${o.name}" style="display:none;">
										<td></td>
										<td>Non alcoholic</td>
										<td>${getValueRow(c, 'non_alcoholic', 'prev_date')}</td>
										<td>${getValueRow(c, 'non_alcoholic', 'mtd')}</td>
										<td>${getValueRow(c, 'non_alcoholic', 'ytd')}</td>
									</tr>
									<tr class="outlet-calc-row outlet-total-row" data-parent="${o.name}" style="display:none;">
										<td></td>
										<td><strong>Total</strong></td>
										<td>${fmtCur(getRawTotal(c, 'prev_date'))}</td>
										<td>${fmtCur(getRawTotal(c, 'mtd'))}</td>
										<td>${fmtCur(getRawTotal(c, 'ytd'))}</td>
									</tr>
									<tr class="outlet-calc-row" style="display:none;" data-parent="${o.name}"></tr>
									<tr class="outlet-calc-row" data-parent="${o.name}" style="display:none;">
										<td></td>
										<td>Non Chargeable</td>
										<td>${getValueRow(c, 'non_chargeable_items_amount', 'prev_date')}</td>
										<td>${getValueRow(c, 'non_chargeable_items_amount', 'mtd')}</td>
										<td>${getValueRow(c, 'non_chargeable_items_amount', 'ytd')}</td>
									</tr>
									<tr class="outlet-calc-row" data-parent="${o.name}" style="display:none;">
										<td></td>
										<td>Discount</td>
										<td>${getValueRow(c, 'discount_amount', 'prev_date')}</td>
										<td>${getValueRow(c, 'discount_amount', 'mtd')}</td>
										<td>${getValueRow(c, 'discount_amount', 'ytd')}</td>
									</tr>
									<tr class="outlet-calc-row outlet-total-row" data-parent="${o.name}" style="display:none;">
										<td></td>
										<td><strong>Total</strong></td>
										<td>${fmtCur(getDeductionsTotal(c, 'prev_date'))}</td>
										<td>${fmtCur(getDeductionsTotal(c, 'mtd'))}</td>
										<td>${fmtCur(getDeductionsTotal(c, 'ytd'))}</td>
									</tr>
								` : ''}
							`;
	}).join('')}
						${hasAddonsRevenue ? `<tr><td>${rowIdx++}</td><td>AddOns Revenue</td><td>${fmtCur(addonsRevenue.prev_date)}</td><td>${fmtCur(addonsRevenue.mtd)}</td><td>${fmtCur(addonsRevenue.ytd)}</td></tr>` : ''}
						${hasOutletData ? `<tr class="row-section-total">
							<td>${rowIdx++}</td>
							<td>TOTAL F&B REVENUE</td>
							<td>${fmtCur(totalFbRevenue.prev_date)}</td>
							<td>${fmtCur(totalFbRevenue.mtd)}</td>
							<td>${fmtCur(totalFbRevenue.ytd)}</td>
						</tr>` : ''}
						<tr class="row-total-revenue">
							<td>${rowIdx++}</td>
							<td>TOTAL REVENUE</td>
							<td>${fmtCur((data.total_room_revenue?.prev_date || 0) + (totalFbRevenue.prev_date || 0))}</td>
							<td>${fmtCur((data.total_room_revenue?.mtd || 0) + (totalFbRevenue.mtd || 0))}</td>
						<td>${fmtCur((data.total_room_revenue?.ytd || 0) + (totalFbRevenue.ytd || 0))}</td>
					</tr>
						<tr><td>${rowIdx++}</td><td>F&B Consumption</td><td>${fmtCur(fbConsumption.prev_date || 0)}</td><td>${fmtCur(fbConsumption.mtd || 0)}</td><td>${fmtCur(fbConsumption.ytd || 0)}</td></tr>
					${hasHkConsumption ? `<tr><td>${rowIdx++}</td><td>HK Consumption</td><td>${fmtCur(hkConsumption.prev_date)}</td><td>${fmtCur(hkConsumption.mtd)}</td><td>${fmtCur(hkConsumption.ytd)}</td></tr>` : ''}
					${hasOtaCommission ? `<tr><td>${rowIdx++}</td><td>OTA Commission</td><td>${fmtCur(otaCommission.prev_date)}</td><td>${fmtCur(otaCommission.mtd)}</td><td>${fmtCur(otaCommission.ytd)}</td></tr>` : ''}
					${hasPayroll ? `<tr><td>${rowIdx++}</td><td>Payroll - Full time</td><td>${fmtCur(payroll.prev_date)}</td><td>${fmtCur(payroll.mtd)}</td><td>${fmtCur(payroll.ytd)}</td></tr>` : ''}
					${costs.map((c) => {
		return `<tr><td>${rowIdx++}</td><td>${fmtUtilityName(c)}</td><td>${fmtCur(c.prev_date)}</td><td>${fmtCur(c.mtd)}</td><td>${fmtCur(c.ytd)}</td></tr>`;
	}).join('')}
						<tr class="row-total">
							<td>${rowIdx++}</td>
							<td>TOTAL COST</td>
							<td>${fmtCur(totalCost.prev_date)}</td>
							<td>${fmtCur(totalCost.mtd)}</td>
							<td>${fmtCur(totalCost.ytd)}</td>
						</tr>
					</tbody>
				</table>
				<div class="drr-mobile">
					<div class="drr-section-title">Room Metrics</div>
					${roomMetrics.map((m, i) => {
		const d = data[m.key] || {};
		const formatter = m.noPct ? fmtVal : fmtPct;
		return `<div class="drr-card">
							<div class="drr-card-header"><span class="drr-card-title">${m.name}</span><span class="drr-card-idx">#${i + 1}</span></div>
							<div class="drr-card-row"><span class="drr-card-label">Prev Date</span><span class="drr-card-value">${formatter(d.prev_date)}</span></div>
							<div class="drr-card-row"><span class="drr-card-label">MTD</span><span class="drr-card-value">${formatter(d.mtd)}</span></div>
							<div class="drr-card-row"><span class="drr-card-label">YTD</span><span class="drr-card-value">${formatter(d.ytd)}</span></div>
						</div>`;
	}).join('')}
					<div class="drr-section-title">Revenue Metrics</div>
					${revenueMetrics.map((m, i) => {
		const d = data[m.key] || {};
		return `<div class="drr-card">
							<div class="drr-card-header"><span class="drr-card-title">${m.name}</span><span class="drr-card-idx">#${roomMetrics.length + i + 1}</span></div>
							<div class="drr-card-row"><span class="drr-card-label">Prev Date</span><span class="drr-card-value">${fmtCur(d.prev_date)}</span></div>
							<div class="drr-card-row"><span class="drr-card-label">MTD</span><span class="drr-card-value">${fmtCur(d.mtd)}</span></div>
							<div class="drr-card-row"><span class="drr-card-label">YTD</span><span class="drr-card-value">${fmtCur(d.ytd)}</span></div>
						</div>`;
	}).join('')}
					<div class="drr-card total">
						<div class="drr-card-header"><span class="drr-card-title">TOTAL ROOM REVENUE</span></div>
						<div class="drr-card-row"><span class="drr-card-label">Prev Date</span><span class="drr-card-value">${fmtCur(data.total_room_revenue?.prev_date)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">MTD</span><span class="drr-card-value">${fmtCur(data.total_room_revenue?.mtd)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">YTD</span><span class="drr-card-value">${fmtCur(data.total_room_revenue?.ytd)}</span></div>
					</div>
					${hasOutletData ? `<div class="drr-section-title">F&B Outlets</div>` : ''}
					${outlets.map((o, i) => {
		const c = getCalc(o);
		const hasCalc = !!(c && (c.food || c.alcoholic || c.non_alcoholic || c.total_gross_sales || c.total_tax));
		const net = o.net_sales || { prev_date: o.prev_date || 0, mtd: o.mtd || 0, ytd: o.ytd || 0 };
		return `<div class="drr-card outlet-card ${hasCalc ? 'expandable' : ''}" data-outlet="${o.name}">
							<div class="drr-card-header"><span class="drr-card-title">${o.name}${hasCalc ? ' <span class="expand-icon">▶</span>' : ''}</span><span class="drr-card-idx">#${roomMetrics.length + revenueMetrics.length + i + 2}</span></div>
							<div class="drr-card-row"><span class="drr-card-label">Prev Date</span><span class="drr-card-value">${fmtCur(getOutletRevenue(o, 'prev_date'))}</span></div>
							<div class="drr-card-row"><span class="drr-card-label">MTD</span><span class="drr-card-value">${fmtCur(getOutletRevenue(o, 'mtd'))}</span></div>
							<div class="drr-card-row"><span class="drr-card-label">YTD</span><span class="drr-card-value">${fmtCur(getOutletRevenue(o, 'ytd'))}</span></div>
							${hasCalc ? `
								<div class="outlet-break-grid outlet-calc-card-row" data-parent="${o.name}" style="display:none;">
									<div class="outlet-break-cell h">Particulars</div>
									<div class="outlet-break-cell h" style="text-align:right;">Prev</div>
									<div class="outlet-break-cell h" style="text-align:right;">MTD</div>
									<div class="outlet-break-cell h" style="text-align:right;">YTD</div>
									<div class="outlet-break-cell label">Food</div>
									<div class="outlet-break-cell val">${getValueRow(c, 'food', 'prev_date')}</div>
									<div class="outlet-break-cell val">${getValueRow(c, 'food', 'mtd')}</div>
									<div class="outlet-break-cell val">${getValueRow(c, 'food', 'ytd')}</div>
									<div class="outlet-break-cell label">Alcoholic</div>
									<div class="outlet-break-cell val">${getValueRow(c, 'alcoholic', 'prev_date')}</div>
									<div class="outlet-break-cell val">${getValueRow(c, 'alcoholic', 'mtd')}</div>
									<div class="outlet-break-cell val">${getValueRow(c, 'alcoholic', 'ytd')}</div>
									<div class="outlet-break-cell label">Non alcoholic</div>
									<div class="outlet-break-cell val">${getValueRow(c, 'non_alcoholic', 'prev_date')}</div>
									<div class="outlet-break-cell val">${getValueRow(c, 'non_alcoholic', 'mtd')}</div>
									<div class="outlet-break-cell val">${getValueRow(c, 'non_alcoholic', 'ytd')}</div>
									<div class="outlet-break-cell label total" style="margin-top: 4px;"><strong>Total</strong></div>
									<div class="outlet-break-cell val total">${fmtCur(getRawTotal(c, 'prev_date'))}</div>
									<div class="outlet-break-cell val total">${fmtCur(getRawTotal(c, 'mtd'))}</div>
									<div class="outlet-break-cell val total">${fmtCur(getRawTotal(c, 'ytd'))}</div>
									<div class="outlet-break-cell sep" style="margin-top: 6px;"></div>
									<div class="outlet-break-cell sep"></div>
									<div class="outlet-break-cell sep"></div>
									<div class="outlet-break-cell sep"></div>
									<div class="outlet-break-cell label">Non Chargeable</div>
									<div class="outlet-break-cell val">${getValueRow(c, 'non_chargeable_items_amount', 'prev_date')}</div>
									<div class="outlet-break-cell val">${getValueRow(c, 'non_chargeable_items_amount', 'mtd')}</div>
									<div class="outlet-break-cell val">${getValueRow(c, 'non_chargeable_items_amount', 'ytd')}</div>
									<div class="outlet-break-cell label">Discount</div>
									<div class="outlet-break-cell val">${getValueRow(c, 'discount_amount', 'prev_date')}</div>
									<div class="outlet-break-cell val">${getValueRow(c, 'discount_amount', 'mtd')}</div>
									<div class="outlet-break-cell val">${getValueRow(c, 'discount_amount', 'ytd')}</div>
									<div class="outlet-break-cell label total" style="margin-top: 4px;"><strong>Total</strong></div>
									<div class="outlet-break-cell val total">${fmtCur(getDeductionsTotal(c, 'prev_date'))}</div>
									<div class="outlet-break-cell val total">${fmtCur(getDeductionsTotal(c, 'mtd'))}</div>
									<div class="outlet-break-cell val total">${fmtCur(getDeductionsTotal(c, 'ytd'))}</div>
								</div>
							` : ''}
						</div>`;
	}).join('')}
					${hasAddonsRevenue ? `<div class="drr-card">
						<div class="drr-card-header"><span class="drr-card-title">AddOns Revenue</span></div>
						<div class="drr-card-row"><span class="drr-card-label">Prev Date</span><span class="drr-card-value">${fmtCur(addonsRevenue.prev_date)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">MTD</span><span class="drr-card-value">${fmtCur(addonsRevenue.mtd)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">YTD</span><span class="drr-card-value">${fmtCur(addonsRevenue.ytd)}</span></div>
					</div>` : ''}
					${hasOutletData ? `<div class="drr-card total">
						<div class="drr-card-header"><span class="drr-card-title">TOTAL F&B REVENUE</span></div>
						<div class="drr-card-row"><span class="drr-card-label">Prev Date</span><span class="drr-card-value">${fmtCur(totalFbRevenue.prev_date)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">MTD</span><span class="drr-card-value">${fmtCur(totalFbRevenue.mtd)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">YTD</span><span class="drr-card-value">${fmtCur(totalFbRevenue.ytd)}</span></div>
					</div>` : ''}
					<div class="drr-card total-revenue">
						<div class="drr-card-header"><span class="drr-card-title">TOTAL REVENUE</span></div>
						<div class="drr-card-row"><span class="drr-card-label">Prev Date</span><span class="drr-card-value">${fmtCur((data.total_room_revenue?.prev_date || 0) + (totalFbRevenue.prev_date || 0))}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">MTD</span><span class="drr-card-value">${fmtCur((data.total_room_revenue?.mtd || 0) + (totalFbRevenue.mtd || 0))}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">YTD</span><span class="drr-card-value">${fmtCur((data.total_room_revenue?.ytd || 0) + (totalFbRevenue.ytd || 0))}</span></div>
					</div>
					<div class="drr-section-title">Costs</div>
					<div class="drr-card">
						<div class="drr-card-header"><span class="drr-card-title">F&B Consumption</span></div>
						<div class="drr-card-row"><span class="drr-card-label">Prev Date</span><span class="drr-card-value">${fmtCur(fbConsumption.prev_date || 0)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">MTD</span><span class="drr-card-value">${fmtCur(fbConsumption.mtd || 0)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">YTD</span><span class="drr-card-value">${fmtCur(fbConsumption.ytd || 0)}</span></div>
					</div>
					${hasHkConsumption ? `<div class="drr-card">
						<div class="drr-card-header"><span class="drr-card-title">HK Consumption</span></div>
						<div class="drr-card-row"><span class="drr-card-label">Prev Date</span><span class="drr-card-value">${fmtCur(hkConsumption.prev_date)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">MTD</span><span class="drr-card-value">${fmtCur(hkConsumption.mtd)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">YTD</span><span class="drr-card-value">${fmtCur(hkConsumption.ytd)}</span></div>
					</div>` : ''}
					${hasOtaCommission ? `<div class="drr-card">
						<div class="drr-card-header"><span class="drr-card-title">OTA Commission</span></div>
						<div class="drr-card-row"><span class="drr-card-label">Prev Date</span><span class="drr-card-value">${fmtCur(otaCommission.prev_date)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">MTD</span><span class="drr-card-value">${fmtCur(otaCommission.mtd)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">YTD</span><span class="drr-card-value">${fmtCur(otaCommission.ytd)}</span></div>
					</div>` : ''}
					${hasPayroll ? `<div class="drr-card">
						<div class="drr-card-header"><span class="drr-card-title">Payroll - Full time</span></div>
						<div class="drr-card-row"><span class="drr-card-label">Prev Date</span><span class="drr-card-value">${fmtCur(payroll.prev_date)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">MTD</span><span class="drr-card-value">${fmtCur(payroll.mtd)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">YTD</span><span class="drr-card-value">${fmtCur(payroll.ytd)}</span></div>
					</div>` : ''}
					${costs.map((c, i) => {
		return `<div class="drr-card">
							<div class="drr-card-header"><span class="drr-card-title">${fmtUtilityName(c)}</span><span class="drr-card-idx">#${roomMetrics.length + revenueMetrics.length + i + 2}</span></div>
							<div class="drr-card-row"><span class="drr-card-label">Prev Date</span><span class="drr-card-value">${fmtCur(c.prev_date)}</span></div>
							<div class="drr-card-row"><span class="drr-card-label">MTD</span><span class="drr-card-value">${fmtCur(c.mtd)}</span></div>
							<div class="drr-card-row"><span class="drr-card-label">YTD</span><span class="drr-card-value">${fmtCur(c.ytd)}</span></div>
						</div>`;
	}).join('')}
					<div class="drr-card cost-total">
						<div class="drr-card-header"><span class="drr-card-title">TOTAL COST</span></div>
						<div class="drr-card-row"><span class="drr-card-label">Prev Date</span><span class="drr-card-value">${fmtCur(totalCost.prev_date)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">MTD</span><span class="drr-card-value">${fmtCur(totalCost.mtd)}</span></div>
						<div class="drr-card-row"><span class="drr-card-label">YTD</span><span class="drr-card-value">${fmtCur(totalCost.ytd)}</span></div>
					</div>
				</div>
			</div>
		</div>
	`;
}
