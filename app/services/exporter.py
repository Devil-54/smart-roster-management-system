import io
import csv
import calendar
from datetime import date
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.models import (
    RosterSchedule, RosterAssignment, RosterConflict, UnavailabilityIncident,
    Employee, WorkingDayRule, Holiday
)
from app.services.operating_calendar import rule_operates_on

def export_roster_csv(roster_id: int) -> io.StringIO:
    """Exports roster matrix to CSV format."""
    roster = RosterSchedule.query.get(roster_id)
    if not roster:
        return None

    assignments = RosterAssignment.query.filter_by(roster_id=roster_id).all()
    num_days = calendar.monthrange(roster.year, roster.month)[1]
    dates = [date(roster.year, roster.month, d) for d in range(1, num_days + 1)]

    # Group assignments by employee_id and date
    grid = {}
    for a in assignments:
        grid[(a.employee_id, a.date)] = a

    employees = Employee.query.order_by(Employee.pod_id, Employee.role, Employee.name).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    header = ['Emp Code', 'Employee Name', 'Role', 'Pod']
    for d in dates:
        header.append(d.strftime('%d-%b (%a)'))
    header.extend(['Total Work Shifts', 'Total Off Days'])
    writer.writerow(header)

    # Rows
    for emp in employees:
        row = [
            emp.emp_code,
            emp.name,
            emp.role,
            emp.pod.name if emp.pod else 'Unassigned'
        ]
        work_count = 0
        off_count = 0

        for d in dates:
            a = grid.get((emp.id, d))
            if not a:
                row.append('-')
            elif a.assignment_type == 'WORK':
                shift_code = a.shift_type.code if a.shift_type else 'W'
                brand_code = a.brand.code if a.brand else ''
                process_code = a.process.code if a.process else ''
                row.append(
                    f"{brand_code}-{process_code}-{shift_code}"
                    if brand_code and process_code
                    else shift_code
                )
                work_count += 1
            elif a.assignment_type == 'WEEKLY_OFF':
                row.append('OFF')
                off_count += 1
            elif a.assignment_type == 'LEAVE':
                row.append('LEAVE')
                off_count += 1
            elif a.assignment_type == 'COMP_OFF':
                row.append('CO')
                off_count += 1
            elif a.assignment_type == 'HOLIDAY':
                row.append('HOL')
                off_count += 1
            else:
                row.append(a.assignment_type)

        row.extend([work_count, off_count])
        writer.writerow(row)

    output.seek(0)
    return output


def export_roster_excel(roster_id: int) -> io.BytesIO:
    """
    Generates a professional multi-sheet Excel (.xlsx) workbook:
    - Sheet 1: Master Schedule Matrix (formatted & colored)
    - Sheet 2: Staffing Coverage Analysis
    - Sheet 3: Conflicts & Explanations Log
    - Sheet 4: Emergency Unavailability & Substitutions
    """
    roster = RosterSchedule.query.get(roster_id)
    if not roster:
        return None

    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    num_days = calendar.monthrange(roster.year, roster.month)[1]
    dates = [date(roster.year, roster.month, d) for d in range(1, num_days + 1)]
    assignments = RosterAssignment.query.filter_by(roster_id=roster_id).all()
    grid = {(a.employee_id, a.date): a for a in assignments}
    employees = Employee.query.order_by(Employee.pod_id, Employee.role, Employee.name).all()

    # Styling helpers
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style='thin', color='D3D3D3'),
        right=Side(style='thin', color='D3D3D3'),
        top=Side(style='thin', color='D3D3D3'),
        bottom=Side(style='thin', color='D3D3D3')
    )
    center_align = Alignment(horizontal='center', vertical='center')

    # Color fills for shift badges
    fills = {
        'M': PatternFill(start_color="D1ECF1", end_color="D1ECF1", fill_type="solid"),
        'A': PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid"),
        'N': PatternFill(start_color="E2D9F3", end_color="E2D9F3", fill_type="solid"),
        'G': PatternFill(start_color="D4EDDA", end_color="D4EDDA", fill_type="solid"),
        'OFF': PatternFill(start_color="F8F9FA", end_color="F8F9FA", fill_type="solid"),
        'LEAVE': PatternFill(start_color="F8D7DA", end_color="F8D7DA", fill_type="solid"),
        'CO': PatternFill(start_color="CCE5FF", end_color="CCE5FF", fill_type="solid"),
        'HOL': PatternFill(start_color="E8DAEF", end_color="E8DAEF", fill_type="solid")
    }

    # ==================== SHEET 1: MASTER SCHEDULE ====================
    ws1 = wb.create_sheet(title="Master Roster Matrix")
    ws1.views.sheetView[0].showGridLines = True

    # Title block
    ws1.merge_cells("A1:G1")
    ws1["A1"] = f"DATASTRAW TECHNOLOGIES - SMART ROSTER MANAGEMENT SYSTEM"
    ws1["A1"].font = Font(name="Segoe UI", size=14, bold=True, color="1F4E78")

    ws1.merge_cells("A2:G2")
    ws1["A2"] = f"Schedule Period: {calendar.month_name[roster.month]} {roster.year} | Status: {roster.status}"
    ws1["A2"].font = Font(name="Segoe UI", size=11, italic=True, color="555555")

    # Table Header at row 4
    headers = ['Emp Code', 'Employee Name', 'Role', 'Pod']
    for d in dates:
        headers.append(f"{d.day} ({d.strftime('%a')[:2]})")
    headers.extend(['Work Shifts', 'Off Days'])

    ws1.append([])
    ws1.append(headers)
    header_row_idx = 4

    for col_idx, cell in enumerate(ws1[header_row_idx], start=1):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    # Freeze panes below header
    ws1.freeze_panes = "E5"

    # Fill Employee Rows
    for emp in employees:
        row_data = [emp.emp_code, emp.name, emp.role, emp.pod.name if emp.pod else 'Unassigned']
        work_cnt = 0
        off_cnt = 0

        for d in dates:
            a = grid.get((emp.id, d))
            if not a:
                row_data.append('-')
            elif a.assignment_type == 'WORK':
                shift_code = a.shift_type.code if a.shift_type else 'W'
                brand_code = a.brand.code if a.brand else ''
                process_code = a.process.code if a.process else ''
                code = (
                    f"{brand_code}-{process_code}-{shift_code}"
                    if brand_code and process_code
                    else shift_code
                )
                row_data.append(code)
                work_cnt += 1
            elif a.assignment_type == 'WEEKLY_OFF':
                row_data.append('OFF')
                off_cnt += 1
            elif a.assignment_type == 'LEAVE':
                row_data.append('LEAVE')
                off_cnt += 1
            elif a.assignment_type == 'COMP_OFF':
                row_data.append('CO')
                off_cnt += 1
            elif a.assignment_type == 'HOLIDAY':
                row_data.append('HOL')
                off_cnt += 1
            else:
                row_data.append(a.assignment_type[:4])

        row_data.extend([work_cnt, off_cnt])
        ws1.append(row_data)

        # Style current row
        curr_row = ws1.max_row
        for col_idx in range(1, len(row_data) + 1):
            c = ws1.cell(row=curr_row, column=col_idx)
            c.border = thin_border
            if col_idx > 4 and col_idx <= len(row_data) - 2:
                c.alignment = center_align
                assignment = grid.get((emp.id, dates[col_idx - 5]))
                val = (
                    assignment.shift_type.code
                    if assignment and assignment.shift_type
                    else str(c.value)
                )
                if val in fills:
                    c.fill = fills[val]
            elif col_idx > len(row_data) - 2:
                c.alignment = center_align
                c.font = Font(name="Segoe UI", bold=True)

    # Adjust column widths
    ws1.column_dimensions['A'].width = 12
    ws1.column_dimensions['B'].width = 22
    ws1.column_dimensions['C'].width = 18
    ws1.column_dimensions['D'].width = 28
    for col_idx in range(5, len(headers) + 1):
        col_letter = get_column_letter(col_idx)
        ws1.column_dimensions[col_letter].width = 8

    # ==================== SHEET 2: COVERAGE ANALYSIS ====================
    ws2 = wb.create_sheet(title="Coverage Analysis")
    ws2.views.sheetView[0].showGridLines = True

    ws2.merge_cells("A1:G1")
    ws2["A1"] = "Daily Staffing Headcount by Brand and Process"
    ws2["A1"].font = Font(name="Segoe UI", size=13, bold=True, color="1F4E78")

    cov_headers = [
        "Date",
        "Day",
        "Brand",
        "Process",
        "Required Staff",
        "Scheduled Staff",
        "Shortfall"
    ]
    ws2.append([])
    ws2.append(cov_headers)
    for cell in ws2[3]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    rules = WorkingDayRule.query.all()
    holiday_dates = {
        holiday.date
        for holiday in Holiday.query.filter(
            Holiday.date >= dates[0],
            Holiday.date <= dates[-1]
        ).all()
    }
    for d in dates:
        for rule in rules:
            if not rule_operates_on(rule, d, holiday_dates):
                continue
            cnt = sum(
                1 for a in assignments
                if a.date == d
                and a.brand_id == rule.brand_id
                and a.process_id == rule.process_id
                and a.assignment_type == 'WORK'
            )
            ws2.append([
                d.strftime('%Y-%m-%d'),
                d.strftime('%A'),
                rule.brand.name,
                rule.process.name,
                rule.min_staff_required,
                cnt,
                max(0, rule.min_staff_required - cnt)
            ])

    for row in ws2.iter_rows(min_row=4, max_col=7):
        for cell in row:
            cell.border = thin_border
            if cell.column in (1, 2, 5, 6, 7):
                cell.alignment = center_align
            if cell.column == 7 and cell.value:
                cell.fill = PatternFill(start_color="F8D7DA", end_color="F8D7DA", fill_type="solid")

    ws2.column_dimensions['A'].width = 14
    ws2.column_dimensions['B'].width = 14
    ws2.column_dimensions['C'].width = 20
    ws2.column_dimensions['D'].width = 24
    ws2.column_dimensions['E'].width = 16
    ws2.column_dimensions['F'].width = 18
    ws2.column_dimensions['G'].width = 12

    # ==================== SHEET 3: CONFLICTS LOG ====================
    ws3 = wb.create_sheet(title="Conflicts & Exceptions")
    ws3.views.sheetView[0].showGridLines = True

    ws3.merge_cells("A1:F1")
    ws3["A1"] = "Rule Conflict & Compliance Log"
    ws3["A1"].font = Font(name="Segoe UI", size=13, bold=True, color="1F4E78")

    conf_headers = [
        "Date",
        "Employee",
        "Conflict Type",
        "Severity",
        "Status",
        "Explanation Message"
    ]
    ws3.append([])
    ws3.append(conf_headers)
    for cell in ws3[3]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    conflicts = RosterConflict.query.filter_by(roster_id=roster_id).order_by(RosterConflict.date).all()
    if not conflicts:
        ws3.append([
                "-",
                "None",
                "CLEAN",
                "INFO",
                "CURRENT",
                "No operational conflicts detected. All constraints satisfied."
        ])
    else:
        for c in conflicts:
                emp_str = f"{c.employee.name} ({c.employee.emp_code})" if c.employee else "System/Coverage"
                status = 'RESOLVED' if c.resolved else 'OPEN'
                ws3.append([
                    c.date.strftime('%Y-%m-%d'),
                    emp_str,
                    c.conflict_type,
                    c.severity,
                    status,
                    c.message
                ])

    for row in ws3.iter_rows(min_row=4, max_col=6):
        for cell in row:
                cell.border = thin_border
                if cell.column in (1, 3, 4, 5):
                    cell.alignment = center_align
                if cell.column == 4 and cell.value == 'CRITICAL':
                    cell.fill = PatternFill(start_color="F8D7DA", end_color="F8D7DA", fill_type="solid")

    ws3.column_dimensions['A'].width = 14
    ws3.column_dimensions['B'].width = 25
    ws3.column_dimensions['C'].width = 26
    ws3.column_dimensions['D'].width = 14
    ws3.column_dimensions['E'].width = 14
    ws3.column_dimensions['F'].width = 60

    # ==================== SHEET 4: UNAVAILABILITY ====================
    ws4 = wb.create_sheet(title="Unavailability & Substitutions")
    ws4.views.sheetView[0].showGridLines = True
    ws4.merge_cells("A1:E1")
    ws4["A1"] = "Emergency Unavailability & Backup Substitutions"
    ws4["A1"].font = Font(name="Segoe UI", size=13, bold=True, color="1F4E78")
    incident_headers = ["Date", "Employee", "Reason", "Status", "Substituted By"]
    ws4.append([])
    ws4.append(incident_headers)
    for cell in ws4[3]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    incidents = UnavailabilityIncident.query.filter_by(
        roster_id=roster_id
    ).order_by(UnavailabilityIncident.date).all()
    if not incidents:
        ws4.append(["-", "None", "No incidents recorded.", "-", "-"])
    else:
        for incident in incidents:
                employee = incident.employee
                substitute = incident.substituted_by
                ws4.append([
                    incident.date.strftime('%Y-%m-%d'),
                    f"{employee.name} ({employee.emp_code})" if employee else "Unknown",
                    incident.reason,
                    incident.status,
                    f"{substitute.name} ({substitute.emp_code})" if substitute else "-"
                ])

    for row in ws4.iter_rows(min_row=4, max_col=5):
        for cell in row:
                cell.border = thin_border
                if cell.column in (1, 4):
                    cell.alignment = center_align
    ws4.column_dimensions['A'].width = 14
    ws4.column_dimensions['B'].width = 28
    ws4.column_dimensions['C'].width = 42
    ws4.column_dimensions['D'].width = 18
    ws4.column_dimensions['E'].width = 28

    # Save to BytesIO
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
