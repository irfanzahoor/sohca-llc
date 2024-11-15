# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.report.financial_statements import (
	get_columns,
	get_data,
	get_filtered_list_for_consolidated_report,
	get_period_list,
)


def execute(filters=None):
	period_list = get_period_list(
		filters.from_fiscal_year,
		filters.to_fiscal_year,
		filters.period_start_date,
		filters.period_end_date,
		filters.filter_based_on,
		filters.periodicity,
		company=filters.company,
	)

	income = get_data(
		filters.company,
		"Income",
		"Credit",
		period_list,
		filters=filters,
		accumulated_values=filters.accumulated_values,
		ignore_closing_entries=True,
		ignore_accumulated_values_for_fy=True,
	)

	asset = get_data(
		filters.company,
		"Asset",
		"Credit",
		period_list,
		filters=filters,
		accumulated_values=filters.accumulated_values,
		ignore_closing_entries=True,
		ignore_accumulated_values_for_fy=True,
	)
	
	income.extend(asset)
	
	expense = get_data(
		filters.company,
		"Expense",
		"Debit",
		period_list,
		filters=filters,
		accumulated_values=filters.accumulated_values,
		ignore_closing_entries=True,
		ignore_accumulated_values_for_fy=True,
	)

	liability = get_data(
		filters.company,
		"Liability",
		"Credit",
		period_list,
		filters=filters,
		accumulated_values=filters.accumulated_values,
		ignore_closing_entries=True,
		ignore_accumulated_values_for_fy=True,
	)
	
	expense.extend(liability)

	net_profit_loss = get_net_profit_loss(
		income, expense, period_list, filters.company, filters.presentation_currency
	)

	data = []
	data.extend(income or [])
	data.extend(expense or [])
	if net_profit_loss:
		data.append(net_profit_loss)

	columns = get_columns(filters.periodicity, period_list, filters.accumulated_values, filters.company)

	columns = get_difference_columns(columns, filters)
	
	chart = get_chart_data(filters, columns, income, expense, net_profit_loss)

	currency = filters.presentation_currency or frappe.get_cached_value(
		"Company", filters.company, "default_currency"
	)
	report_summary, primitive_summary = get_report_summary(
		period_list, filters.periodicity, income, expense, net_profit_loss, currency, filters
	)

	data = get_difference_data(columns, data)
	return columns, data, None, chart, report_summary, primitive_summary

def get_difference_data(columns, data):
    diff_w_columns = []
    percent_diff_columns = []
    for row in columns:
        if "diff_with_" in row.get("fieldname"): 
            diff_w_columns.append(row.get("fieldname"))
        if "percent_diff_with_" in row.get("fieldname"):
            percent_diff_columns.append(row.get("fieldname"))

    for row in data:
        for col in diff_w_columns:
            months = col.split("diff_with_")[1].split("_and_")
            old_value = row.get(months[0], 0)  
            new_value = row.get(months[1], 0)  

            row[col] = new_value - old_value

        for col in percent_diff_columns:
            months = col.split("percent_diff_with_")[1].split("_and_")
            old_value = row.get(months[0], 0)  
            new_value = row.get(months[1], 0)  

            # Avoid division by zero by checking if old_value is not 0
            if old_value != 0:
                percentage_diff = ((new_value - old_value) / old_value) * 100
            else:
                percentage_diff = 0  
            row[col] = percentage_diff  

    return data


def get_difference_columns(columns, filters):
	flag = False
	old_value = {}
	columns_new = []

	for row in columns:
		columns_new.append(row) 
        
		if flag and row.get("fieldtype")  == "Currency":

			if filters.get("show_difference") in ["Monthly"]:
				columns_new.append({
					'fieldname': f'diff_with_{old_value.get("fieldname")}_and_{row.get("fieldname")}', 
					'label': f'Diff W/{old_value.get("label")}', 
					'fieldtype': 'Currency', 
					'options': 'currency', 
					'width': 150
				})
				columns_new.append({
						'fieldname': f'percent_diff_with_{old_value.get("fieldname")}_and_{row.get("fieldname")}',
						'label': f'Percent Diff W/{old_value.get("label")}', 
						'fieldtype': 'Percent', 
						'width': 150
				})	

			if filters.get("show_difference") in ["Yearly"]:
			
				month = row.get("fieldname").split("_")
				
				if len(month) < 2:
					continue 
		
				month = f"{month[0]}_{int(month[1])-1}"

				month_name = row.get("label").split(" ")
				month_name = f"{month_name[0]} {int(month_name[1])-1}"
				# Adjust the year to the previous year for yearly comparison
				# month_name = f"{month[0]}_{int(month[1]) - 12}"
				columns_new.append({
					'fieldname': f'diff_with_{month}_and_{row.get("fieldname")}', 
					'label': f'Diff W/{month_name}', 
					'fieldtype': 'Currency', 
					'options': 'currency', 
					'width': 150
				})


  # Add percentage difference
				columns_new.append({
						'fieldname': f'percent_diff_with_{month_name}_and_{row.get("fieldname")}',
						'label': f'Percent Diff W/{month_name}', 
						'fieldtype': 'Percent', 
						'width': 150
				})
		if row.get("fieldtype")  == "Currency":
			flag = True
		
		old_value = row

	columns = columns_new

	# frappe.msgprint(f"{columns}")

	return columns


def get_report_summary(
	period_list, periodicity, income, expense, net_profit_loss, currency, filters, consolidated=False
):
	net_income, net_expense, net_profit = 0.0, 0.0, 0.0

	if filters.get("accumulated_in_group_company"):
		period_list = get_filtered_list_for_consolidated_report(filters, period_list)

	if filters.accumulated_values:
		
		key = period_list[-1].key
		if income:
			net_income = income[-2].get(key)
		if expense:
			net_expense = expense[-2].get(key)
		if net_profit_loss:
			net_profit = net_profit_loss.get(key)
	else:
		for period in period_list:
			key = period if consolidated else period.key
			if income:
				net_income += income[-2].get(key)
			if expense:
				net_expense += expense[-2].get(key)
			if net_profit_loss:
				net_profit += net_profit_loss.get(key)

	if len(period_list) == 1 and periodicity == "Yearly":
		profit_label = _("Profit This Year")
		income_label = _("Total Income This Year")
		expense_label = _("Total Expense This Year")
	else:
		profit_label = _("Net Profit")
		income_label = _("Total Income")
		expense_label = _("Total Expense")

	return [
		{"value": net_income, "label": income_label, "datatype": "Currency", "currency": currency},
		{"type": "separator", "value": "-"},
		{"value": net_expense, "label": expense_label, "datatype": "Currency", "currency": currency},
		{"type": "separator", "value": "=", "color": "blue"},
		{
			"value": net_profit,
			"indicator": "Green" if net_profit > 0 else "Red",
			"label": profit_label,
			"datatype": "Currency",
			"currency": currency,
		},
	], net_profit


def get_net_profit_loss(income, expense, period_list, company, currency=None, consolidated=False):
	total = 0
	net_profit_loss = {
		"account_name": "'" + _("Profit for the year") + "'",
		"account": "'" + _("Profit for the year") + "'",
		"warn_if_negative": True,
		"currency": currency or frappe.get_cached_value("Company", company, "default_currency"),
	}

	has_value = False

	for period in period_list:
		key = period if consolidated else period.key
		total_income = flt(income[-2][key], 3) if income else 0
		total_expense = flt(expense[-2][key], 3) if expense else 0

		net_profit_loss[key] = total_income - total_expense

		if net_profit_loss[key]:
			has_value = True

		total += flt(net_profit_loss[key])
		net_profit_loss["total"] = total

	if has_value:
		return net_profit_loss


def get_chart_data(filters, columns, income, expense, net_profit_loss):
	labels = [d.get("label") for d in columns[2:]]

	income_data, expense_data, net_profit = [], [], []

	for p in columns[2:]:
		if income:
			income_data.append(income[-2].get(p.get("fieldname")))
		if expense:
			expense_data.append(expense[-2].get(p.get("fieldname")))
		if net_profit_loss:
			net_profit.append(net_profit_loss.get(p.get("fieldname")))

	datasets = []
	if income_data:
		datasets.append({"name": _("Income"), "values": income_data})
	if expense_data:
		datasets.append({"name": _("Expense"), "values": expense_data})
	if net_profit:
		datasets.append({"name": _("Net Profit/Loss"), "values": net_profit})

	chart = {"data": {"labels": labels, "datasets": datasets}}

	if not filters.accumulated_values:
		chart["type"] = "bar"
	else:
		chart["type"] = "line"

	chart["fieldtype"] = "Currency"

	return chart