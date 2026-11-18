import calendar
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, send_file
from app.extensions import db
from app.models import (
    RosterSchedule, RosterAssignment, RosterConflict, UnavailabilityIncident,
    Employee, Pod, Brand, Process, ShiftType
)
from app.services.scheduler import DeterministicScheduler
from app.services.validator import validate_roster
from app.services.exporter import export_roster_csv, export_roster_excel

roster_bp = Blueprint('roster', __name__)

@roster_bp.route('/')
def index():
    schedules = RosterSchedule.query.order_by(RosterSchedule.year.desc(), RosterSchedule.month.desc()).all()
    today = date.today()
    return render_template('roster/index.html', schedules=schedules, current_month=today.month, current_year=today.year)

@roster_bp.route('/generate', methods=['POST'])
def generate():
    month = request.form.get('month', type=int)
    year = request.form.get('year', type=int)
    name = request.form.get('name', '').strip()

    if not month or not year:
        flash('Month and Year are required.', 'danger')
        return redirect(url_for('roster.index'))

    try:
        scheduler = DeterministicScheduler(month=month, year=year)
        roster = scheduler.generate(roster_name=name if name else None)
        flash(f'Successfully generated roster "{roster.name}" with {roster.total_shifts_scheduled} work shifts!', 'success')
        if roster.conflicts_count > 0:
            flash(f'Notice: {roster.conflicts_count} operational constraint warnings/conflicts detected and logged for review.', 'warning')
        return redirect(url_for('roster.company_view', roster_id=roster.id))
    except Exception as e:
        flash(f'Error during roster generation: {str(e)}', 'danger')
        return redirect(url_for('roster.index'))

@roster_bp.route('/<int:roster_id>/revalidate', methods=['POST'])
def revalidate(roster_id):
    roster = RosterSchedule.query.get_or_404(roster_id)
    conflicts = validate_roster(roster_id)
    roster.conflicts_count = len(conflicts)
    db.session.commit()
    if conflicts:
        flash(f'Revalidation complete: {len(conflicts)} conflict(s) detected.', 'warning')
    else:
        flash('Revalidation complete: Roster is 100% compliant with all hard constraints!', 'success')
    return redirect(request.referrer or url_for('roster.company_view', roster_id=roster_id))

# ==================== 1. COMPANY-WISE VIEW ====================
@roster_bp.route('/<int:roster_id>/company')
def company_view(roster_id):
    roster = RosterSchedule.query.get_or_404(roster_id)
    num_days = calendar.monthrange(roster.year, roster.month)[1]
    dates = [date(roster.year, roster.month, d) for d in range(1, num_days + 1)]

    # Filters
    pod_id = request.args.get('pod_id', type=int)
    brand_id = request.args.get('brand_id', type=int)

    emp_query = Employee.query.filter_by(is_active=True)
    if pod_id:
        emp_query = emp_query.filter_by(pod_id=pod_id)

    employees = emp_query.order_by(Employee.pod_id, Employee.role, Employee.name).all()

    # Preload assignments into matrix: grid[emp_id][date] = assignment
    assignments = RosterAssignment.query.filter_by(roster_id=roster_id).all()
    grid = {}
    for a in assignments:
        grid.setdefault(a.employee_id, {})[a.date] = a

    # Summary counts per employee
    emp_stats = {}
    for emp in employees:
        emp_assignments = grid.get(emp.id, {})
        work_cnt = sum(1 for a in emp_assignments.values() if a.assignment_type == 'WORK')
        off_cnt = sum(1 for a in emp_assignments.values() if a.assignment_type in ('WEEKLY_OFF', 'LEAVE', 'COMP_OFF', 'HOLIDAY'))
        emp_stats[emp.id] = {'work': work_cnt, 'off': off_cnt}

    # Conflicts
    conflicts = RosterConflict.query.filter_by(roster_id=roster_id).order_by(RosterConflict.date).all()
    pods = Pod.query.all()
    brands = Brand.query.all()
    processes = Process.query.all()
    shift_types = ShiftType.query.all()

    return render_template(
        'roster/company_view.html',
        roster=roster,
        dates=dates,
        employees=employees,
        grid=grid,
        emp_stats=emp_stats,
        conflicts=conflicts,
        pods=pods,
        brands=brands,
        processes=processes,
        shift_types=shift_types,
        selected_pod=pod_id,
        selected_brand=brand_id
    )

# ==================== 2. POD-WISE VIEW ====================
@roster_bp.route('/<int:roster_id>/pods')
def pod_view(roster_id):
    roster = RosterSchedule.query.get_or_404(roster_id)
    num_days = calendar.monthrange(roster.year, roster.month)[1]
    dates = [date(roster.year, roster.month, d) for d in range(1, num_days + 1)]

    pods = Pod.query.all()
    assignments = RosterAssignment.query.filter_by(roster_id=roster_id).all()
    grid = {}
    for a in assignments:
        grid.setdefault(a.employee_id, {})[a.date] = a

    # Group employees by pod
    pod_data = []
    for p in pods:
        members = Employee.query.filter_by(pod_id=p.id, is_active=True).order_by(Employee.role == 'Pod Lead', Employee.name).all()
        pod_data.append({
            'pod': p,
            'lead': p.lead,
            'members': members
        })

    shift_types = ShiftType.query.all()
    brands = Brand.query.all()
    processes = Process.query.all()

    return render_template(
        'roster/pod_view.html',
        roster=roster,
        dates=dates,
        pod_data=pod_data,
        grid=grid,
        shift_types=shift_types,
        brands=brands,
        processes=processes
    )

# ==================== 3. BRAND-WISE VIEW ====================
@roster_bp.route('/<int:roster_id>/brands')
def brand_view(roster_id):
    roster = RosterSchedule.query.get_or_404(roster_id)
    num_days = calendar.monthrange(roster.year, roster.month)[1]
    dates = [date(roster.year, roster.month, d) for d in range(1, num_days + 1)]

    selected_brand_id = request.args.get('brand_id', type=int)
    brands = Brand.query.all()
    current_brand = Brand.query.get(selected_brand_id) if selected_brand_id else (brands[0] if brands else None)

    processes = Process.query.all()
    assignments = RosterAssignment.query.filter_by(roster_id=roster_id).all()

    # Precalculate coverage count for current brand: coverage[process_id][date] = [assigned_assignments]
    brand_coverage = {}
    if current_brand:
        for p in processes:
            brand_coverage[p.id] = {}
            for d in dates:
                brand_coverage[p.id][d] = [
                    a for a in assignments
                    if a.date == d and a.brand_id == current_brand.id and a.process_id == p.id and a.assignment_type == 'WORK'
                ]

    shift_types = ShiftType.query.all()

    return render_template(
        'roster/brand_view.html',
        roster=roster,
        dates=dates,
        brands=brands,
        current_brand=current_brand,
        processes=processes,
        brand_coverage=brand_coverage,
        shift_types=shift_types
    )

# ==================== 4. PROCESS-WISE VIEW ====================
@roster_bp.route('/<int:roster_id>/processes')
def process_view(roster_id):
    roster = RosterSchedule.query.get_or_404(roster_id)
    num_days = calendar.monthrange(roster.year, roster.month)[1]
    dates = [date(roster.year, roster.month, d) for d in range(1, num_days + 1)]

    processes = Process.query.all()
    brands = Brand.query.all()
    assignments = RosterAssignment.query.filter_by(roster_id=roster_id, assignment_type='WORK').all()

    # Matrix: data[process_id][brand_id][date] = count
    proc_matrix = {}
    for p in processes:
        proc_matrix[p.id] = {}
        for b in brands:
            proc_matrix[p.id][b.id] = {}
            for d in dates:
                proc_matrix[p.id][b.id][d] = sum(
                    1 for a in assignments
                    if a.process_id == p.id and a.brand_id == b.id and a.date == d
                )

    return render_template(
        'roster/process_view.html',
        roster=roster,
        dates=dates,
        processes=processes,
        brands=brands,
        proc_matrix=proc_matrix
    )

# ==================== 5. EMPLOYEE-WISE VIEW ====================
@roster_bp.route('/<int:roster_id>/employee')
@roster_bp.route('/<int:roster_id>/employee/<int:emp_id>')
def employee_view(roster_id, emp_id=None):
    roster = RosterSchedule.query.get_or_404(roster_id)
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()

    current_emp = Employee.query.get(emp_id) if emp_id else (employees[0] if employees else None)

    assignments = []
    stats = {'work': 0, 'weekly_off': 0, 'leave': 0, 'comp_off': 0, 'holiday': 0}

    if current_emp:
        assignments = RosterAssignment.query.filter_by(
            roster_id=roster_id,
            employee_id=current_emp.id
        ).order_by(RosterAssignment.date).all()

        for a in assignments:
            if a.assignment_type == 'WORK':
                stats['work'] += 1
            elif a.assignment_type == 'WEEKLY_OFF':
                stats['weekly_off'] += 1
            elif a.assignment_type == 'LEAVE':
                stats['leave'] += 1
            elif a.assignment_type == 'COMP_OFF':
                stats['comp_off'] += 1
            elif a.assignment_type == 'HOLIDAY':
                stats['holiday'] += 1

    return render_template(
        'roster/employee_view.html',
        roster=roster,
        employees=employees,
        current_emp=current_emp,
        assignments=assignments,
        stats=stats
    )

# ==================== EXPORT ROUTES ====================
@roster_bp.route('/<int:roster_id>/export/csv')
def export_csv(roster_id):
    roster = RosterSchedule.query.get_or_404(roster_id)
    csv_file = export_roster_csv(roster_id)
    if not csv_file:
        flash('Could not generate CSV export.', 'danger')
        return redirect(url_for('roster.company_view', roster_id=roster_id))

    filename = f"roster_{roster.year}_{roster.month:02d}_{roster.name.replace(' ', '_')}.csv"
    return Response(
        csv_file.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )

@roster_bp.route('/<int:roster_id>/export/excel')
def export_excel(roster_id):
    roster = RosterSchedule.query.get_or_404(roster_id)
    excel_io = export_roster_excel(roster_id)
    if not excel_io:
        flash('Could not generate Excel export.', 'danger')
        return redirect(url_for('roster.company_view', roster_id=roster_id))

    filename = f"roster_{roster.year}_{roster.month:02d}_{roster.name.replace(' ', '_')}.xlsx"
    return send_file(
        excel_io,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
