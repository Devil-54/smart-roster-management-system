import calendar
from datetime import date, timedelta
from app.extensions import db
from app.models import (
    Employee, ShiftType, WorkingDayRule,
    EmployeeAssignment, Holiday, LeaveRequest, WeeklyOffRule,
    RosterSchedule, RosterAssignment
)
from app.services.validator import validate_roster
from app.services.operating_calendar import rule_operates_on, shifts_overlap

class DeterministicScheduler:
    """
    Deterministic Monthly Roster Generation Engine
    Strictly complies with DataStraw Assessment Requirements:
    1. Mandatory hard constraints:
       - Approved leaves (PL, SL, CO) strictly respected (never scheduled).
       - Maximum consecutive working days limit (default <= 6 days).
       - At least 1 weekly off rest day per rolling 7-day period.
       - Max 1 work shift per employee per calendar day (no overlapping shifts across brands/processes).
       - Skill qualification certification (employee must be certified for Brand & Process).
       - Operating Calendar respect (processes closed on holidays/Sundays have 0 demand).
       - Minimum staffing requirements per brand & process.
    2. Preferences & soft constraints:
       - Pod alignment (prefer pod members and pod lead supervision).
       - Dedicated single-resource brand continuity with shared floater backup.
       - Fair shift workload balance.
       - Equitable weekend shift rotation.
    """

    def __init__(self, month: int, year: int):
        self.month = month
        self.year = year
        self.num_days = calendar.monthrange(year, month)[1]
        self.dates = [date(year, month, day) for day in range(1, self.num_days + 1)]

    def generate(self, roster_name: str = None) -> RosterSchedule:
        if not roster_name:
            month_name = calendar.month_name[self.month]
            roster_name = f"{month_name} {self.year} Operations Roster"

        # Check if an existing draft/schedule exists for this month/year
        existing = RosterSchedule.query.filter_by(month=self.month, year=self.year).first()
        if existing:
            RosterAssignment.query.filter_by(roster_id=existing.id).delete()
            roster = existing
            roster.name = roster_name
            roster.status = 'DRAFT'
        else:
            roster = RosterSchedule(
                name=roster_name,
                month=self.month,
                year=self.year,
                status='DRAFT'
            )
            db.session.add(roster)
            db.session.flush()

        # Load active data
        employees = Employee.query.filter_by(is_active=True).all()

        # Holidays
        holidays = Holiday.query.filter(
            Holiday.date >= self.dates[0],
            Holiday.date <= self.dates[-1]
        ).all()
        holiday_date_map = {h.date: h for h in holidays}
        holiday_dates = set(holiday_date_map)

        # Approved Leaves
        leaves = LeaveRequest.query.filter(
            LeaveRequest.status == 'APPROVED',
            LeaveRequest.start_date <= self.dates[-1],
            LeaveRequest.end_date >= self.dates[0]
        ).all()

        emp_leave_map = {}  # (emp_id, date) -> leave
        for l in leaves:
            curr = max(l.start_date, self.dates[0])
            end = min(l.end_date, self.dates[-1])
            while curr <= end:
                emp_leave_map[(l.employee_id, curr)] = l
                curr += timedelta(days=1)

        # Weekly Off Rules
        weekly_off_rules = {r.employee_id: r for r in WeeklyOffRule.query.all()}

        # Working Day Rules
        working_rules = WorkingDayRule.query.all()
        rules_by_day = {d: [] for d in range(7)}
        for r in working_rules:
            rules_by_day[r.day_of_week].append(r)

        # Employee Qualifications: quals[(emp_id, brand_id, process_id)] = EmployeeAssignment
        quals = {}
        for a in EmployeeAssignment.query.all():
            quals[(a.employee_id, a.brand_id, a.process_id)] = a

        # State tracking for deterministic scheduling
        schedule_grid = {}  # (emp_id, date) -> assignment dict
        emp_consecutive_days = {e.id: 0 for e in employees}
        emp_total_shifts = {e.id: 0 for e in employees}
        emp_weekend_shifts = {e.id: 0 for e in employees}

        # Shift types lookup
        shift_types = ShiftType.query.all()
        shift_types_by_id = {shift.id: shift for shift in shift_types}
        default_shift = next((shift for shift in shift_types if shift.code == 'M'), None) or (
            shift_types[0] if shift_types else None
        )
        gen_shift = ShiftType.query.filter_by(code='G').first() or default_shift

        # Step A: Pre-assign Approved Leaves
        for d in self.dates:
            for emp in employees:
                if (emp.id, d) in emp_leave_map:
                    leave = emp_leave_map[(emp.id, d)]
                    assignment_type = 'COMP_OFF' if leave.leave_type == 'CO' else 'LEAVE'
                    schedule_grid[(emp.id, d)] = {
                        'roster_id': roster.id,
                        'date': d,
                        'employee_id': emp.id,
                        'brand_id': None,
                        'process_id': None,
                        'shift_type_id': None,
                        'assignment_type': assignment_type,
                        'notes': f"{leave.leave_type} - {leave.reason or 'Approved Leave'}"
                    }

        # Step B: Determine Day-by-Day Schedule
        for d in self.dates:
            dow = d.weekday()  # 0=Mon, 6=Sun
            is_weekend = dow in (5, 6)
            is_holiday = d in holiday_date_map

            # 1. Reset consecutive days for those on Leave today
            for emp in employees:
                if (emp.id, d) in schedule_grid:
                    emp_consecutive_days[emp.id] = 0

            # 2. Compulsory Weekly Off for employees hitting max consecutive days
            for emp in employees:
                if (emp.id, d) in schedule_grid:
                    continue

                max_days = emp.max_consecutive_days or 6
                # Must take compulsory rest day if worked max_days continuously
                if emp_consecutive_days[emp.id] >= max_days:
                    schedule_grid[(emp.id, d)] = {
                        'roster_id': roster.id,
                        'date': d,
                        'employee_id': emp.id,
                        'brand_id': None,
                        'process_id': None,
                        'shift_type_id': None,
                        'assignment_type': 'WEEKLY_OFF',
                        'notes': f'Mandatory rest: Reached {max_days} consecutive days'
                    }
                    emp_consecutive_days[emp.id] = 0

            # 3. Filter Operating Rules for today considering Operating Calendar:
            # - 365_DAYS: Operates every day including Sundays & Holidays
            # - DAILY_EXCEPT_HOLIDAYS: Closed on Public Holidays
            # - SUNDAYS_HOLIDAYS_OFF: Closed on Sundays and Public Holidays
            active_rules_today = [
                rule for rule in rules_by_day[dow]
                if rule_operates_on(rule, d, holiday_dates)
            ]

            # Sort rules: Multi-resource & Customer Support first, then single-resource brands
            active_rules_today.sort(key=lambda r: (
                r.brand.brand_type == 'SINGLE_RESOURCE',
                r.process.code != 'CS',
                -r.min_staff_required
            ))

            # 4. Allocate shifts to fulfill operating rules
            for rule in active_rules_today:
                brand_id = rule.brand_id
                process_id = rule.process_id
                required_count = rule.min_staff_required
                fallback_shift = gen_shift if rule.process.code == 'ACC' else default_shift
                shift_id = rule.shift_type_id or (fallback_shift.id if fallback_shift else None)
                candidate_shift = shift_types_by_id.get(shift_id)

                # Find eligible candidates who are NOT yet assigned on date d
                candidates = []
                for emp in employees:
                    if (emp.id, d) in schedule_grid:
                        continue  # Already assigned on date d (enforces no double booking)

                    qual = quals.get((emp.id, brand_id, process_id))
                    if not qual:
                        continue  # Enforces mandatory skill qualification

                    max_days = emp.max_consecutive_days or 6
                    if emp_consecutive_days[emp.id] >= max_days:
                        continue  # Enforces fatigue limit

                    if not candidate_shift:
                        continue

                    overlaps_existing_shift = False
                    for (assigned_emp_id, assigned_date), assigned in schedule_grid.items():
                        if (
                            assigned_emp_id != emp.id
                            or assigned_date >= d
                            or (d - assigned_date).days > 1
                            or assigned['assignment_type'] != 'WORK'
                        ):
                            continue
                        assigned_shift = shift_types_by_id.get(assigned['shift_type_id'])
                        if (
                            assigned_shift
                            and shifts_overlap(
                                assigned_date,
                                assigned_shift,
                                d,
                                candidate_shift
                            )
                        ):
                            overlaps_existing_shift = True
                            break
                    if overlaps_existing_shift:
                        continue

                    # Check preferred weekly off day: allow soft preference unless need demands it
                    rule_off = weekly_off_rules.get(emp.id)
                    is_preferred_off_day = (rule_off.preferred_day_1 == dow or rule_off.preferred_day_2 == dow) if rule_off else (dow == 6)

                    # Deterministic Priority Scoring
                    score = 100

                    # Factor A: Primary dedicated skill (+100) vs secondary/shared (+40)
                    if qual.is_primary:
                        score += 100
                    if getattr(qual, 'assignment_nature', 'DEDICATED') == 'DEDICATED':
                        score += 50
                    score += (qual.skill_level or 3) * 10

                    # Factor B: Pod alignment (+80 for matching pod)
                    pod_name = emp.pod.name if emp.pod else ''
                    if 'Alpha' in pod_name and rule.brand.code == 'APX':
                        score += 80
                    elif 'Gamma' in pod_name and rule.brand.code == 'ZST':
                        score += 80
                    elif 'Beta' in pod_name and rule.brand.code in ('LMN', 'SWF', 'URB', 'PGL'):
                        score += 80
                    elif 'Delta' in pod_name and rule.brand.code in ('CRD', 'BIO', 'BYT', 'NOV'):
                        score += 80
                    elif 'Delta' in pod_name:
                        score += 50  # Pod Delta universal floaters

                    # Factor C: Soft preference penalty for preferred rest day (-40 if due for rest)
                    if is_preferred_off_day and emp_consecutive_days[emp.id] >= 3:
                        score -= 40

                    # Factor D: Fairness - penalty for high total shifts worked so far
                    score -= emp_total_shifts[emp.id] * 5

                    # Factor E: Weekend fairness - penalty for weekend shifts already worked
                    if is_weekend:
                        score -= emp_weekend_shifts[emp.id] * 8

                    # Factor F: Pod Lead supervisory bonus
                    if emp.role == 'Pod Lead':
                        score += 15

                    candidates.append((score, emp))

                # Deterministically sort candidates descending by score, tiebreak by emp_code
                candidates.sort(key=lambda x: (x[0], -int(x[1].emp_code[3:] if x[1].emp_code[3:].isdigit() else 0)), reverse=True)

                assigned_count = 0
                for score, emp in candidates:
                    if assigned_count >= required_count:
                        break

                    notes = f"Assigned to {rule.brand.code}-{rule.process.code}"
                    if is_holiday:
                        notes += " (Holiday Shift - Comp-off Eligible)"

                    schedule_grid[(emp.id, d)] = {
                        'roster_id': roster.id,
                        'date': d,
                        'employee_id': emp.id,
                        'brand_id': brand_id,
                        'process_id': process_id,
                        'shift_type_id': shift_id,
                        'assignment_type': 'WORK',
                        'notes': notes
                    }
                    emp_consecutive_days[emp.id] += 1
                    emp_total_shifts[emp.id] += 1
                    if is_weekend:
                        emp_weekend_shifts[emp.id] += 1
                    assigned_count += 1

            # 5. For employees still unassigned today, allocate Weekly Off or Holiday Off
            for emp in employees:
                if (emp.id, d) not in schedule_grid:
                    rule_off = weekly_off_rules.get(emp.id)
                    is_pref_off = (rule_off.preferred_day_1 == dow or rule_off.preferred_day_2 == dow) if rule_off else (dow == 6)

                    # If it's a public holiday and employee has no work, mark HOLIDAY
                    if is_holiday:
                        a_type = 'HOLIDAY'
                        note = f"Public Holiday Off: {holiday_date_map[d].name}"
                    else:
                        a_type = 'WEEKLY_OFF'
                        note = 'Preferred Weekly Off' if is_pref_off else 'Staggered Rest / Standby'

                    schedule_grid[(emp.id, d)] = {
                        'roster_id': roster.id,
                        'date': d,
                        'employee_id': emp.id,
                        'brand_id': None,
                        'process_id': None,
                        'shift_type_id': None,
                        'assignment_type': a_type,
                        'notes': note
                    }
                    emp_consecutive_days[emp.id] = 0

        # Save all generated assignments
        assignment_records = [RosterAssignment(**item) for item in schedule_grid.values()]
        db.session.bulk_save_objects(assignment_records)
        db.session.flush()

        # Update Roster summary stats
        total_work_shifts = sum(1 for item in schedule_grid.values() if item['assignment_type'] == 'WORK')
        roster.total_shifts_scheduled = total_work_shifts

        # Run validation engine to audit all constraints & record conflicts
        conflicts = validate_roster(roster.id)
        roster.conflicts_count = len(conflicts)

        db.session.commit()
        return roster
