from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.extensions import db
from app.models import Brand, Process, Pod, Employee, WorkingDayRule, ShiftType

operations_bp = Blueprint('operations', __name__)

# ==================== BRANDS ====================
@operations_bp.route('/brands')
def brands_list():
    brands = Brand.query.all()
    processes = Process.query.all()
    return render_template('operations/brands.html', brands=brands, processes=processes)

@operations_bp.route('/brands/add', methods=['POST'])
def add_brand():
    name = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip().upper()
    description = request.form.get('description', '').strip()

    if not name or not code:
        flash('Brand Name and Code are required.', 'danger')
        return redirect(url_for('operations.brands_list'))

    if Brand.query.filter((Brand.name == name) | (Brand.code == code)).first():
        flash('Brand with this Name or Code already exists.', 'danger')
        return redirect(url_for('operations.brands_list'))

    brand_type = request.form.get('brand_type', 'SINGLE_RESOURCE')
    calendar_type = request.form.get('calendar_type', '365_DAYS')

    brand = Brand(name=name, code=code, description=description, is_active=True, brand_type=brand_type, calendar_type=calendar_type)
    db.session.add(brand)
    db.session.flush()

    # Create default working day rules for all existing processes
    processes = Process.query.all()
    default_shift = ShiftType.query.first()
    for proc in processes:
        for day in range(7):
            if calendar_type == 'SUNDAYS_HOLIDAYS_OFF':
                is_op = (day < 6)
            elif calendar_type == 'DAILY_EXCEPT_HOLIDAYS':
                is_op = True
            else:
                is_op = True

            min_staff = 1 if is_op else 0
            if brand_type == 'MULTI_RESOURCE' and proc.code == 'CS' and is_op:
                min_staff = 2

            db.session.add(WorkingDayRule(
                brand_id=brand.id,
                process_id=proc.id,
                day_of_week=day,
                is_operating=is_op,
                min_staff_required=min_staff,
                shift_type_id=default_shift.id if default_shift else None,
                operating_calendar=calendar_type
            ))

    db.session.commit()
    flash(f'Brand {brand.name} added with default operational rules!', 'success')
    return redirect(url_for('operations.brands_list'))

# ==================== PROCESSES ====================
@operations_bp.route('/processes')
def processes_list():
    processes = Process.query.all()
    shifts = ShiftType.query.all()
    brands = Brand.query.all()
    return render_template('operations/processes.html', processes=processes, shifts=shifts, brands=brands)

@operations_bp.route('/processes/add', methods=['POST'])
def add_process():
    name = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip().upper()
    description = request.form.get('description', '').strip()
    color_code = request.form.get('color_code', '#0d6efd')

    if not name or not code:
        flash('Process Name and Code are required.', 'danger')
        return redirect(url_for('operations.processes_list'))

    if Process.query.filter((Process.name == name) | (Process.code == code)).first():
        flash('Process with this Name or Code already exists.', 'danger')
        return redirect(url_for('operations.processes_list'))

    proc = Process(name=name, code=code, description=description, color_code=color_code)
    db.session.add(proc)
    db.session.flush()

    # Initialize working rules for all brands
    brands = Brand.query.all()
    default_shift = ShiftType.query.first()
    for b in brands:
        for day in range(7):
            is_op = (day < 5)
            db.session.add(WorkingDayRule(
                brand_id=b.id,
                process_id=proc.id,
                day_of_week=day,
                is_operating=is_op,
                min_staff_required=1 if is_op else 0,
                shift_type_id=default_shift.id if default_shift else None
            ))

    db.session.commit()
    flash(f'Process {proc.name} added successfully!', 'success')
    return redirect(url_for('operations.processes_list'))

# ==================== PODS & LEADS ====================
@operations_bp.route('/pods')
def pods_list():
    pods = Pod.query.all()
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    return render_template('operations/pods.html', pods=pods, employees=employees)

@operations_bp.route('/pods/add', methods=['POST'])
def add_pod():
    name = request.form.get('name', '').strip()
    lead_id = request.form.get('lead_id', type=int)
    description = request.form.get('description', '').strip()

    if not name:
        flash('Pod name is required.', 'danger')
        return redirect(url_for('operations.pods_list'))

    pod = Pod(name=name, lead_id=lead_id if lead_id else None, description=description)
    db.session.add(pod)
    db.session.commit()
    flash(f'Pod {pod.name} created successfully!', 'success')
    return redirect(url_for('operations.pods_list'))

@operations_bp.route('/pods/<int:pod_id>/assign_lead', methods=['POST'])
def assign_pod_lead(pod_id):
    pod = Pod.query.get_or_404(pod_id)
    lead_id = request.form.get('lead_id', type=int)

    if lead_id:
        emp = Employee.query.get(lead_id)
        if emp:
            emp.role = 'Pod Lead'
            emp.pod_id = pod.id
            pod.lead_id = emp.id
            flash(f"{emp.name} is now the Pod Lead for {pod.name}.", 'success')
    else:
        pod.lead_id = None
        flash(f"Pod Lead removed for {pod.name}.", 'info')

    db.session.commit()
    return redirect(url_for('operations.pods_list'))

# ==================== WORKING DAY RULES ====================
@operations_bp.route('/rules/update', methods=['POST'])
def update_working_rules():
    rule_ids = request.form.getlist('rule_id')
    for r_id in rule_ids:
        rule = WorkingDayRule.query.get(int(r_id))
        if rule:
            is_op = request.form.get(f'is_operating_{r_id}') == '1'
            min_staff = request.form.get(f'min_staff_{r_id}', type=int, default=1)
            shift_id = request.form.get(f'shift_id_{r_id}', type=int)

            rule.is_operating = is_op
            rule.min_staff_required = min_staff if is_op else 0
            if shift_id:
                rule.shift_type_id = shift_id

    db.session.commit()
    flash('Operational working day rules updated successfully!', 'success')
    return redirect(request.referrer or url_for('operations.brands_list'))
