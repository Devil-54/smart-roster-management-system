import calendar
from collections import Counter
from datetime import date, timedelta
from app.extensions import db
from app.models import (
    Employee, Brand, Process, ShiftType, WorkingDayRule,
    EmployeeAssignment, Holiday, LeaveRequest,
    RosterSchedule, RosterAssignment, RosterConflict
)
from app.services.operating_calendar import rule_operates_on, shifts_overlap


def calculate_roster_coverage(roster_id: int):
    roster = RosterSchedule.query.get(roster_id)
    if not roster:
        return {'required': 0, 'staffed': 0, 'percentage': 0.0}

    month_days = calendar.monthrange(roster.year, roster.month)[1]
    dates = [
        date(roster.year, roster.month, day)
        for day in range(1, month_days + 1)
    ]
    holidays = {
        holiday.date
        for holiday in Holiday.query.filter(
            Holiday.date >= dates[0],
            Holiday.date <= dates[-1]
        ).all()
    }
    rules = WorkingDayRule.query.all()
    assignments = RosterAssignment.query.filter_by(
        roster_id=roster_id,
        assignment_type='WORK'
    ).all()
    staffing = Counter(
        (assignment.date, assignment.brand_id, assignment.process_id)
        for assignment in assignments
        if assignment.brand_id and assignment.process_id
    )

    required = 0
    staffed = 0
    for target_date in dates:
        for rule in rules:
            if not rule_operates_on(rule, target_date, holidays):
                continue
            required += rule.min_staff_required
            scheduled = staffing[
                (target_date, rule.brand_id, rule.process_id)
            ]
            staffed += min(scheduled, rule.min_staff_required)

    percentage = round(staffed / required * 100, 1) if required else 100.0
    return {'required': required, 'staffed': staffed, 'percentage': percentage}

def validate_roster(roster_id: int):
    """
    Comprehensive constraint validation engine.
    Audits all assignments in a roster against mandatory and soft operational constraints:
    1. Double Booking: max 1 shift per employee per date.
    2. Leave Compliance: no work assignments on approved leave days (PL, SL, CO).
    3. Fatigue Limit: no employee exceeding max consecutive working days (default 6).
    4. Skill Certification: employee must have active certification for Brand + Process.
    5. Operating Calendar Compliance: no work shifts when brand/process is closed on holidays or Sundays.
    6. Minimum Staffing Headcount: required headcount must be met on all operating days.
    """
    roster = RosterSchedule.query.get(roster_id)
    if not roster:
        return []

    assignments = RosterAssignment.query.filter_by(roster_id=roster_id).all()

    # Preload reference data
    employees = {e.id: e for e in Employee.query.all()}
    brands = {b.id: b for b in Brand.query.all()}
    processes = {p.id: p for p in Process.query.all()}
    working_rules = WorkingDayRule.query.all()
    month_days = calendar.monthrange(roster.year, roster.month)[1]
    first_date = date(roster.year, roster.month, 1)
    last_date = date(roster.year, roster.month, month_days)
    roster_dates = [
        date(roster.year, roster.month, day)
        for day in range(1, month_days + 1)
    ]
    rules_by_slot = {
        (rule.brand_id, rule.process_id, rule.day_of_week): rule
        for rule in working_rules
    }

    # Preload approved leaves
    leaves = LeaveRequest.query.filter(
        LeaveRequest.status == 'APPROVED',
        LeaveRequest.start_date <= last_date,
        LeaveRequest.end_date >= first_date
    ).all()
    emp_leaves = {}
    for l in leaves:
        curr = max(l.start_date, first_date)
        end = min(l.end_date, last_date)
        while curr <= end:
            emp_leaves[(l.employee_id, curr)] = l
            curr += timedelta(days=1)

    # Preload holidays
    holidays = Holiday.query.filter(
        Holiday.date >= first_date,
        Holiday.date <= last_date
    ).all()
    holiday_map = {h.date: h for h in holidays}
    holiday_dates = set(holiday_map)

    # Preload employee certifications: (emp_id, brand_id, process_id)
    cert_set = set(
        (a.employee_id, a.brand_id, a.process_id)
        for a in EmployeeAssignment.query.all()
    )

    conflicts = []

    # 1. Employee-level checks
    emp_assignments = {}
    for a in assignments:
        emp_assignments.setdefault(a.employee_id, []).append(a)

    for emp_id, a_list in emp_assignments.items():
        emp = employees.get(emp_id)
        if not emp:
            continue

        consecutive_work_days = 0
        assignments_by_date = {}
        for assignment in a_list:
            assignments_by_date.setdefault(assignment.date, []).append(assignment)

        work_assignments = [
            assignment
            for assignment in a_list
            if assignment.assignment_type == 'WORK'
        ]
        for index, first in enumerate(work_assignments):
            if not first.shift_type:
                continue
            for second in work_assignments[index + 1:]:
                if second.date == first.date or not second.shift_type:
                    continue
                if shifts_overlap(
                    first.date,
                    first.shift_type,
                    second.date,
                    second.shift_type
                ):
                    conflicts.append(RosterConflict(
                        roster_id=roster_id,
                        date=max(first.date, second.date),
                        employee_id=emp_id,
                        conflict_type='SHIFT_OVERLAP',
                        severity='CRITICAL',
                        message=(
                            f"Overlapping shifts: {emp.name} ({emp.emp_code}) is "
                            f"scheduled on {first.date:%Y-%m-%d} "
                            f"({first.shift_type.name}) and {second.date:%Y-%m-%d} "
                            f"({second.shift_type.name}) during overlapping hours."
                        )
                    ))

        for target_date in roster_dates:
            day_assignments = assignments_by_date.get(target_date, [])
            work_today = [
                assignment
                for assignment in day_assignments
                if assignment.assignment_type == 'WORK'
            ]
            if len(work_today) > 1:
                conflicts.append(RosterConflict(
                    roster_id=roster_id,
                    date=target_date,
                    employee_id=emp_id,
                    conflict_type='DOUBLE_BOOKING',
                    severity='CRITICAL',
                    message=f"Duplicate assignment: {emp.name} ({emp.emp_code}) is scheduled more than once on {target_date:%Y-%m-%d}."
                ))
            if work_today:
                consecutive_work_days += 1
            else:
                consecutive_work_days = 0

            for a in work_today:
                # Check B: Scheduled on Approved Leave
                if (emp_id, a.date) in emp_leaves:
                    leave = emp_leaves[(emp_id, a.date)]
                    conflicts.append(RosterConflict(
                        roster_id=roster_id,
                        date=a.date,
                        employee_id=emp_id,
                        conflict_type='SCHEDULED_ON_LEAVE',
                        severity='CRITICAL',
                        message=f"{emp.name} ({emp.emp_code}) is scheduled to work on {a.date.strftime('%Y-%m-%d')} while on approved {leave.leave_type} ({leave.reason or 'Leave'})."
                    ))

                # Check C: Max Consecutive Working Days (Fatigue limit)
                max_days = emp.max_consecutive_days or 6
                if consecutive_work_days > max_days:
                    conflicts.append(RosterConflict(
                        roster_id=roster_id,
                        date=a.date,
                        employee_id=emp_id,
                        conflict_type='CONSECUTIVE_DAYS_EXCEEDED',
                        severity='CRITICAL',
                        message=f"Fatigue rule violation: {emp.name} worked {consecutive_work_days} consecutive days as of {a.date.strftime('%Y-%m-%d')} (Max allowed is {max_days})."
                    ))

                # Check D: Skill & Process qualification certification
                if (
                    not a.brand_id
                    or not a.process_id
                    or (emp_id, a.brand_id, a.process_id) not in cert_set
                ):
                    b_name = brands.get(a.brand_id).name if a.brand_id in brands else 'Unknown Brand'
                    p_name = processes.get(a.process_id).name if a.process_id in processes else 'Unknown Process'
                    conflicts.append(RosterConflict(
                        roster_id=roster_id,
                        date=a.date,
                        employee_id=emp_id,
                        conflict_type='UNQUALIFIED_ASSIGNMENT',
                        severity='CRITICAL',
                        message=f"Uncertified assignment: {emp.name} is not certified for {b_name} - {p_name}."
                    ))

                # Check E: Operating Calendar Compliance
                brand_obj = brands.get(a.brand_id)
                process_obj = processes.get(a.process_id)
                operating_rule = rules_by_slot.get((
                    a.brand_id,
                    a.process_id,
                    a.date.weekday()
                ))
                if not operating_rule or not rule_operates_on(
                    operating_rule,
                    a.date,
                    holiday_dates
                ):
                    if a.date in holiday_map:
                        reason = f"public holiday ({holiday_map[a.date].name})"
                    elif a.date.weekday() == 6:
                        reason = 'Sunday'
                    else:
                        reason = 'a non-operating day'
                    brand_name = brand_obj.name if brand_obj else 'Unknown Brand'
                    process_code = process_obj.code if process_obj else 'Unknown Process'
                    conflicts.append(RosterConflict(
                        roster_id=roster_id,
                        date=a.date,
                        employee_id=emp_id,
                        conflict_type='CALENDAR_VIOLATION',
                        severity='WARNING',
                        message=(
                            f"Calendar violation: {brand_name} [{process_code}] "
                            f"does not operate on {reason}, but {emp.name} is "
                            f"scheduled to work."
                        )
                    ))

            max_days = emp.max_consecutive_days or 6
            if consecutive_work_days > max_days:
                conflicts.append(RosterConflict(
                    roster_id=roster_id,
                    date=target_date,
                    employee_id=emp_id,
                    conflict_type='CONSECUTIVE_DAYS_EXCEEDED',
                    severity='CRITICAL',
                    message=f"Fatigue rule violation: {emp.name} worked {consecutive_work_days} consecutive days as of {target_date:%Y-%m-%d} (Max allowed is {max_days})."
                ))

    # 2. Coverage & Minimum Staffing Check by Brand & Process
    staffing = Counter(
        (assignment.date, assignment.brand_id, assignment.process_id)
        for assignment in assignments
        if assignment.assignment_type == 'WORK'
        and assignment.brand_id
        and assignment.process_id
    )
    for target_date in roster_dates:
        for rule in working_rules:
            if not rule_operates_on(rule, target_date, holiday_dates):
                continue
            scheduled = staffing[(target_date, rule.brand_id, rule.process_id)]
            if scheduled < rule.min_staff_required:
                b_name = brands.get(rule.brand_id).name if rule.brand_id in brands else f"Brand #{rule.brand_id}"
                p_code = processes.get(rule.process_id).code if rule.process_id in processes else f"Proc #{rule.process_id}"
                conflicts.append(RosterConflict(
                    roster_id=roster_id,
                    date=target_date,
                    employee_id=None,
                    conflict_type='UNDER_STAFFED',
                    severity='CRITICAL',
                    message=f"Understaffed: {b_name} [{p_code}] on {target_date.strftime('%a %d %b %Y')} requires {rule.min_staff_required} staff, but only {scheduled} are scheduled."
                ))

    existing_by_signature = {}
    existing_conflicts = RosterConflict.query.filter_by(roster_id=roster_id).all()
    for existing in existing_conflicts:
        signature = (
            existing.date,
            existing.employee_id,
            existing.conflict_type,
            existing.message
        )
        existing_by_signature.setdefault(signature, []).append(existing)

    current_conflicts = []
    for conflict in conflicts:
        signature = (
            conflict.date,
            conflict.employee_id,
            conflict.conflict_type,
            conflict.message
        )
        previous = existing_by_signature.get(signature)
        if previous:
            persisted = previous.pop()
            persisted.severity = conflict.severity
            persisted.resolved = False
        else:
            persisted = conflict
            db.session.add(persisted)
        current_conflicts.append(persisted)

    for previous_conflicts in existing_by_signature.values():
        for previous in previous_conflicts:
            previous.resolved = True

    db.session.flush()

    return current_conflicts


def validate_single_assignment(roster_id: int, employee_id: int, target_date: date,
                               brand_id: int = None, process_id: int = None,
                               shift_type_id: int = None, assignment_type: str = 'WORK'):
    """
    Performs instant validation for prospective manual edits or shift swaps.
    Returns:
        {
            "valid": bool,
            "errors": [str, ...],
            "warnings": [str, ...]
        }
    """
    errors = []
    warnings = []

    emp = Employee.query.get(employee_id)
    if not emp:
        return {'valid': False, 'errors': ['Employee not found.'], 'warnings': []}

    valid_assignment_types = ('WORK', 'WEEKLY_OFF', 'LEAVE', 'COMP_OFF', 'HOLIDAY')
    if assignment_type not in valid_assignment_types:
        return {
            'valid': False,
            'errors': [f'Unsupported assignment type: {assignment_type}.'],
            'warnings': []
        }

    if assignment_type != 'WORK':
        return {'valid': True, 'errors': [], 'warnings': []}

    if not brand_id or not process_id or not shift_type_id:
        return {
            'valid': False,
            'errors': ['Brand, process, and shift type are required for work assignments.'],
            'warnings': []
        }

    # 1. Approved Leave check
    leave = LeaveRequest.query.filter(
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.status == 'APPROVED',
        LeaveRequest.start_date <= target_date,
        LeaveRequest.end_date >= target_date
    ).first()
    if leave:
        errors.append(f"{emp.name} is on approved {leave.leave_type} ({leave.reason or 'Leave'}) on {target_date}.")

    # 2. Skill Qualification Certification check
    has_cert = EmployeeAssignment.query.filter_by(
        employee_id=employee_id,
        brand_id=brand_id,
        process_id=process_id
    ).first()
    brand = Brand.query.get(brand_id)
    process = Process.query.get(process_id)
    if not has_cert:
        errors.append(
            f"{emp.name} is not certified for "
            f"{brand.name if brand else 'Brand'} - "
            f"{process.name if process else 'Process'}."
        )

    shift_type = ShiftType.query.get(shift_type_id)
    if not shift_type:
        errors.append('Selected shift type was not found.')

    # 3. Operating day and calendar check
    operating_rule = WorkingDayRule.query.filter_by(
        brand_id=brand_id,
        process_id=process_id,
        day_of_week=target_date.weekday()
    ).first()
    holiday = Holiday.query.filter_by(date=target_date).first()
    if not operating_rule:
        errors.append(
            f"No operating rule exists for "
            f"{brand.name if brand else 'Brand'} - "
            f"{process.name if process else 'Process'} on "
            f"{target_date.strftime('%A')}."
        )
    elif not rule_operates_on(
        operating_rule,
        target_date,
        {holiday.date} if holiday else set()
    ):
        if holiday:
            closed_reason = f"public holiday ({holiday.name})"
        elif target_date.weekday() == 6:
            closed_reason = 'Sunday'
        else:
            closed_reason = 'a non-operating day'
        errors.append(
            f"{brand.name if brand else 'Brand'} - "
            f"{process.name if process else 'Process'} does not operate on "
            f"{closed_reason}."
        )

    # 4. Prevent overlapping shifts, including overnight shifts across dates.
    if shift_type:
        surrounding_shifts = RosterAssignment.query.filter(
            RosterAssignment.roster_id == roster_id,
            RosterAssignment.employee_id == employee_id,
            RosterAssignment.date >= target_date - timedelta(days=1),
            RosterAssignment.date <= target_date + timedelta(days=1),
            RosterAssignment.assignment_type == 'WORK',
            RosterAssignment.date != target_date
        ).all()
        for existing in surrounding_shifts:
            if (
                existing.shift_type
                and shifts_overlap(
                    target_date,
                    shift_type,
                    existing.date,
                    existing.shift_type
                )
            ):
                errors.append(
                    f"Shift overlaps with {emp.name}'s existing "
                    f"{existing.shift_type.name} shift on "
                    f"{existing.date.strftime('%Y-%m-%d')}."
                )

    # 5. Consecutive Working Days limit check around target_date
    start_window = target_date - timedelta(days=7)
    end_window = target_date + timedelta(days=7)
    surrounding = RosterAssignment.query.filter(
        RosterAssignment.roster_id == roster_id,
        RosterAssignment.employee_id == employee_id,
        RosterAssignment.date >= start_window,
        RosterAssignment.date <= end_window
    ).order_by(RosterAssignment.date).all()

    day_work = {a.date: (a.assignment_type == 'WORK') for a in surrounding}
    day_work[target_date] = True

    streak = 0
    curr = target_date
    while day_work.get(curr, False):
        streak += 1
        curr -= timedelta(days=1)

    curr = target_date + timedelta(days=1)
    while day_work.get(curr, False):
        streak += 1
        curr += timedelta(days=1)

    max_days = emp.max_consecutive_days or 6
    if streak > max_days:
        errors.append(f"Fatigue breach: Assigning this shift results in {streak} consecutive working days for {emp.name} (Maximum allowed is {max_days}).")
    elif streak == max_days:
        warnings.append(f"{emp.name} will reach their limit of {max_days} consecutive working days.")

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings
    }
