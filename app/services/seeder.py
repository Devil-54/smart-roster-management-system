from datetime import date, timedelta
from app.extensions import db
from app.models import (
    Employee, Pod, Brand, Process, ShiftType, WorkingDayRule,
    EmployeeAssignment, Holiday, LeaveRequest, WeeklyOffRule,
    RosterSchedule, RosterAssignment, RosterConflict, UnavailabilityIncident
)

def seed_database(force_refresh=False):
    """
    Populates database with synthetic sample data complying with:
    1. Minimum 30 employees (seeds 36).
    2. Exactly 80% single-resource brands and 20% multi-employee brands (8 single-resource, 2 multi-resource).
    3. Separate and shared process assignments.
    4. 3 Operating calendar configurations:
       - 365 days including Sundays and holidays
       - Daily except public holidays
       - Sundays and public holidays off
    5. Different minimum staffing requirements (1 for single-resource, 2+ for multi-resource).
    6. Staggered weekly off patterns.
    """
    # If already seeded with 10 brands and force_refresh is False, return
    if not force_refresh and Brand.query.count() >= 10 and Employee.query.count() >= 30:
        print("[Seeder] Database already populated with 10 brands and 36 employees. Skipping seeder.")
        return

    print("[Seeder] Seeding/Updating database with comprehensive operational data...")

    # Clear existing operational configuration if refreshing
    if force_refresh or Brand.query.count() < 10:
        RosterConflict.query.delete()
        UnavailabilityIncident.query.delete()
        RosterAssignment.query.delete()
        RosterSchedule.query.delete()
        EmployeeAssignment.query.delete()
        WorkingDayRule.query.delete()
        WeeklyOffRule.query.delete()
        LeaveRequest.query.delete()
        Holiday.query.delete()
        Employee.query.delete()
        Pod.query.delete()
        Brand.query.delete()
        Process.query.delete()
        ShiftType.query.delete()
        db.session.commit()

    # 1. Create Shift Types
    shifts = [
        ShiftType(name='Morning', code='M', start_time='07:00', end_time='15:30', color_code='#0dcaf0'),
        ShiftType(name='Afternoon', code='A', start_time='15:00', end_time='23:30', color_code='#fd7e14'),
        ShiftType(name='Night', code='N', start_time='23:00', end_time='07:30', color_code='#6f42c1'),
        ShiftType(name='General', code='G', start_time='09:30', end_time='18:30', color_code='#198754')
    ]
    db.session.add_all(shifts)
    db.session.flush()
    shift_map = {s.code: s for s in shifts}

    # 2. Create Processes
    processes = [
        Process(name='Customer Support', code='CS', description='Tier 1 & 2 Omnichannel Support', color_code='#0d6efd'),
        Process(name='Accounts', code='ACC', description='Billing, Ledger & Merchant Reconciliation', color_code='#198754'),
        Process(name='Non-Delivery Reports', code='NDR', description='Order Logistics & Courier Escalations', color_code='#dc3545')
    ]
    db.session.add_all(processes)
    db.session.flush()
    process_map = {p.code: p for p in processes}

    # 3. Create Brands (80% Single-Resource Brands, 20% Multi-Employee Brands)
    # Total = 10 Brands -> 8 Single-Resource (80%), 2 Multi-Employee (20%)
    brands = [
        # --- Multi-Employee Brands (20%) ---
        Brand(
            name='Apex Retail',
            code='APX',
            description='Enterprise high-volume eCommerce retail platform',
            brand_type='MULTI_RESOURCE',
            calendar_type='365_DAYS'
        ),
        Brand(
            name='Zest Logistics',
            code='ZST',
            description='Nationwide cold-chain freight & express courier network',
            brand_type='MULTI_RESOURCE',
            calendar_type='365_DAYS'
        ),

        # --- Single-Resource Brands (80%) ---
        Brand(
            name='Lumina Cosmetics',
            code='LMN',
            description='Boutique organic skincare & beauty direct-to-consumer brand',
            brand_type='SINGLE_RESOURCE',
            calendar_type='DAILY_EXCEPT_HOLIDAYS'
        ),
        Brand(
            name='SwiftCart Electronics',
            code='SWF',
            description='Specialty gaming hardware and consumer electronics retailer',
            brand_type='SINGLE_RESOURCE',
            calendar_type='SUNDAYS_HOLIDAYS_OFF'
        ),
        Brand(
            name='UrbanKicks Footwear',
            code='URB',
            description='Premium designer footwear and streetwear apparel brand',
            brand_type='SINGLE_RESOURCE',
            calendar_type='DAILY_EXCEPT_HOLIDAYS'
        ),
        Brand(
            name='PureGlow Wellness',
            code='PGL',
            description='Nutraceutical supplements and holistic health products',
            brand_type='SINGLE_RESOURCE',
            calendar_type='SUNDAYS_HOLIDAYS_OFF'
        ),
        Brand(
            name='CraftDen Home Decor',
            code='CRD',
            description='Handcrafted furniture and artisan interior decor marketplace',
            brand_type='SINGLE_RESOURCE',
            calendar_type='365_DAYS'
        ),
        Brand(
            name='BioHealth Nutrition',
            code='BIO',
            description='Clinical sports supplements and fitness nutrition store',
            brand_type='SINGLE_RESOURCE',
            calendar_type='DAILY_EXCEPT_HOLIDAYS'
        ),
        Brand(
            name='ByteGadgets Tech',
            code='BYT',
            description='Smart home IoT sensors and wireless mobile accessories',
            brand_type='SINGLE_RESOURCE',
            calendar_type='SUNDAYS_HOLIDAYS_OFF'
        ),
        Brand(
            name='NovaDecor Living',
            code='NOV',
            description='Modern lifestyle furnishings and minimalist decor',
            brand_type='SINGLE_RESOURCE',
            calendar_type='365_DAYS'
        )
    ]
    db.session.add_all(brands)
    db.session.flush()
    brand_map = {b.code: b for b in brands}

    # 4. Create Working Day Rules for each Brand & Process
    # Incorporates the 3 operating calendars:
    # 1. 365_DAYS (Mon-Sun, open on holidays)
    # 2. DAILY_EXCEPT_HOLIDAYS (Mon-Sun, closed on holidays)
    # 3. SUNDAYS_HOLIDAYS_OFF (Mon-Sat, closed on Sundays and holidays)
    rules = []

    # APX (Multi-Resource): CS (365 days, min staff 2), ACC (Mon-Fri, Sundays/Holidays Off, min staff 1), NDR (Mon-Sat, min staff 1)
    for day in range(7):
        rules.append(WorkingDayRule(
            brand_id=brand_map['APX'].id, process_id=process_map['CS'].id,
            day_of_week=day, is_operating=True, min_staff_required=2,
            shift_type_id=shift_map['M'].id, operating_calendar='365_DAYS'
        ))
        is_acc = day < 5
        rules.append(WorkingDayRule(
            brand_id=brand_map['APX'].id, process_id=process_map['ACC'].id,
            day_of_week=day, is_operating=is_acc, min_staff_required=1 if is_acc else 0,
            shift_type_id=shift_map['G'].id, operating_calendar='SUNDAYS_HOLIDAYS_OFF'
        ))
        is_ndr = day < 6
        rules.append(WorkingDayRule(
            brand_id=brand_map['APX'].id, process_id=process_map['NDR'].id,
            day_of_week=day, is_operating=is_ndr, min_staff_required=1 if is_ndr else 0,
            shift_type_id=shift_map['M'].id, operating_calendar='DAILY_EXCEPT_HOLIDAYS'
        ))

    # ZST (Multi-Resource): CS (365 days, min staff 2), NDR (365 days, min staff 2), ACC (Mon-Sat, min staff 1)
    for day in range(7):
        rules.append(WorkingDayRule(
            brand_id=brand_map['ZST'].id, process_id=process_map['CS'].id,
            day_of_week=day, is_operating=True, min_staff_required=2,
            shift_type_id=shift_map['M'].id, operating_calendar='365_DAYS'
        ))
        rules.append(WorkingDayRule(
            brand_id=brand_map['ZST'].id, process_id=process_map['NDR'].id,
            day_of_week=day, is_operating=True, min_staff_required=2,
            shift_type_id=shift_map['M'].id, operating_calendar='365_DAYS'
        ))
        is_acc = day < 6
        rules.append(WorkingDayRule(
            brand_id=brand_map['ZST'].id, process_id=process_map['ACC'].id,
            day_of_week=day, is_operating=is_acc, min_staff_required=1 if is_acc else 0,
            shift_type_id=shift_map['G'].id, operating_calendar='SUNDAYS_HOLIDAYS_OFF'
        ))

    # Single-Resource Brands (80%): Require min staff = 1 for Customer Support
    single_brands_config = [
        ('LMN', 'DAILY_EXCEPT_HOLIDAYS', 7), # Mon-Sun except holidays
        ('SWF', 'SUNDAYS_HOLIDAYS_OFF', 6),  # Mon-Sat (Sunday off)
        ('URB', 'DAILY_EXCEPT_HOLIDAYS', 7), # Mon-Sun except holidays
        ('PGL', 'SUNDAYS_HOLIDAYS_OFF', 6),  # Mon-Sat (Sunday off)
        ('CRD', '365_DAYS', 7),              # 365 days
        ('BIO', 'DAILY_EXCEPT_HOLIDAYS', 7), # Mon-Sun except holidays
        ('BYT', 'SUNDAYS_HOLIDAYS_OFF', 6),  # Mon-Sat (Sunday off)
        ('NOV', '365_DAYS', 7)               # 365 days
    ]

    for b_code, cal_type, operating_days_count in single_brands_config:
        b_id = brand_map[b_code].id
        for day in range(7):
            is_op = (day < operating_days_count)
            rules.append(WorkingDayRule(
                brand_id=b_id,
                process_id=process_map['CS'].id,
                day_of_week=day,
                is_operating=is_op,
                min_staff_required=1 if is_op else 0,
                shift_type_id=shift_map['G'].id,
                operating_calendar=cal_type
            ))

    db.session.add_all(rules)
    db.session.flush()

    # 5. Create Pods
    pods = [
        Pod(name='Pod Alpha (Apex Retail Enterprise)', description='Dedicated team for Apex Retail operations and escalations'),
        Pod(name='Pod Beta (Boutique Brands East)', description='Single-resource dedicated specialists for Lumina, SwiftCart, UrbanKicks & PureGlow'),
        Pod(name='Pod Gamma (Zest Logistics Express)', description='Dedicated team for Zest Logistics courier tracking & NDR dispatch'),
        Pod(name='Pod Delta (Boutique Brands West & Surge)', description='Dedicated specialists for CraftDen, BioHealth, ByteGadgets, NovaDecor & cross-functional floaters')
    ]
    db.session.add_all(pods)
    db.session.flush()
    pod_map = {
        'Alpha': pods[0],
        'Beta': pods[1],
        'Gamma': pods[2],
        'Delta': pods[3]
    }

    # 6. Create 36 Sample Employees
    raw_employees = [
        # Pod Alpha (Apex Retail) - 9 employees
        ('DST001', 'Pod Lead', 'Alpha', 6),
        ('DST002', 'Senior Associate', 'Alpha', 6),
        ('DST003', 'Senior Associate', 'Alpha', 6),
        ('DST004', 'Associate', 'Alpha', 6),
        ('DST005', 'Associate', 'Alpha', 6),
        ('DST006', 'Associate', 'Alpha', 6),
        ('DST007', 'Associate', 'Alpha', 6),
        ('DST008', 'Trainee', 'Alpha', 5),
        ('DST009', 'Trainee', 'Alpha', 5),

        # Pod Beta (Boutique Brands East) - 9 employees
        ('DST010', 'Pod Lead', 'Beta', 6),
        ('DST011', 'Senior Associate', 'Beta', 6),
        ('DST012', 'Senior Associate', 'Beta', 6),
        ('DST013', 'Associate', 'Beta', 6),
        ('DST014', 'Associate', 'Beta', 6),
        ('DST015', 'Associate', 'Beta', 6),
        ('DST016', 'Associate', 'Beta', 6),
        ('DST017', 'Trainee', 'Beta', 5),
        ('DST018', 'Trainee', 'Beta', 5),

        # Pod Gamma (Zest Logistics) - 9 employees
        ('DST019', 'Pod Lead', 'Gamma', 6),
        ('DST020', 'Senior Associate', 'Gamma', 6),
        ('DST021', 'Senior Associate', 'Gamma', 6),
        ('DST022', 'Associate', 'Gamma', 6),
        ('DST023', 'Associate', 'Gamma', 6),
        ('DST024', 'Associate', 'Gamma', 6),
        ('DST025', 'Associate', 'Gamma', 6),
        ('DST026', 'Trainee', 'Gamma', 5),
        ('DST027', 'Trainee', 'Gamma', 5),

        # Pod Delta (Boutique Brands West & Surge Floaters) - 9 employees
        ('DST028', 'Pod Lead', 'Delta', 6),
        ('DST029', 'Senior Associate', 'Delta', 6),
        ('DST030', 'Senior Associate', 'Delta', 6),
        ('DST031', 'Associate', 'Delta', 6),
        ('DST032', 'Associate', 'Delta', 6),
        ('DST033', 'Associate', 'Delta', 6),
        ('DST034', 'Associate', 'Delta', 6),
        ('DST035', 'Trainee', 'Delta', 5),
        ('DST036', 'Trainee', 'Delta', 5)
    ]

    emp_objects = []
    for code, role, pod_key, max_days in raw_employees:
        employee_number = int(code[3:])
        emp = Employee(
            emp_code=code,
            name=f'Employee {employee_number:03d}',
            email=f'employee{employee_number:03d}@example.invalid',
            phone=None,
            role=role,
            pod_id=pod_map[pod_key].id,
            hire_date=date(2025, 1, 15),
            is_active=True,
            max_consecutive_days=max_days
        )
        emp_objects.append(emp)
        db.session.add(emp)

    db.session.flush()

    # Assign Pod Leads
    pod_map['Alpha'].lead_id = emp_objects[0].id
    pod_map['Beta'].lead_id = emp_objects[9].id
    pod_map['Gamma'].lead_id = emp_objects[18].id
    pod_map['Delta'].lead_id = emp_objects[27].id
    db.session.flush()

    # 7. Employee Brand-Process Certifications (Separate & Shared)
    assignments = []

    # Pod Alpha -> Apex Retail (Multi-Employee)
    # - Separate (Dedicated) assignments for CS
    # - Shared assignments for cross-trained ACC/NDR
    for i in range(0, 9):
        emp = emp_objects[i]
        # Primary dedicated: Apex Retail CS
        assignments.append(EmployeeAssignment(
            employee_id=emp.id, brand_id=brand_map['APX'].id, process_id=process_map['CS'].id,
            is_primary=True, skill_level=4 if 'Senior' in emp.role or 'Lead' in emp.role else 3,
            assignment_nature='DEDICATED'
        ))
        # Shared secondary skills: Apex Retail NDR or ACC
        if i % 2 == 0:
            assignments.append(EmployeeAssignment(
                employee_id=emp.id, brand_id=brand_map['APX'].id, process_id=process_map['NDR'].id,
                is_primary=False, skill_level=3, assignment_nature='SHARED'
            ))
        else:
            assignments.append(EmployeeAssignment(
                employee_id=emp.id, brand_id=brand_map['APX'].id, process_id=process_map['ACC'].id,
                is_primary=False, skill_level=3, assignment_nature='SHARED'
            ))

    # Pod Beta -> Boutique Single-Resource Brands (Lumina, SwiftCart, UrbanKicks, PureGlow)
    # Each brand has 1 primary dedicated associate + cross-trained backup associates
    # Dedicated assignments:
    assignments.append(EmployeeAssignment(employee_id=emp_objects[9].id, brand_id=brand_map['LMN'].id, process_id=process_map['CS'].id, is_primary=True, skill_level=4, assignment_nature='DEDICATED'))
    assignments.append(EmployeeAssignment(employee_id=emp_objects[10].id, brand_id=brand_map['SWF'].id, process_id=process_map['CS'].id, is_primary=True, skill_level=4, assignment_nature='DEDICATED'))
    assignments.append(EmployeeAssignment(employee_id=emp_objects[11].id, brand_id=brand_map['URB'].id, process_id=process_map['CS'].id, is_primary=True, skill_level=4, assignment_nature='DEDICATED'))
    assignments.append(EmployeeAssignment(employee_id=emp_objects[12].id, brand_id=brand_map['PGL'].id, process_id=process_map['CS'].id, is_primary=True, skill_level=4, assignment_nature='DEDICATED'))

    # Shared backup assignments for remaining Pod Beta associates across Pod Beta brands:
    for i in range(13, 18):
        emp = emp_objects[i]
        assignments.append(EmployeeAssignment(employee_id=emp.id, brand_id=brand_map['LMN'].id, process_id=process_map['CS'].id, is_primary=(i == 13), skill_level=3, assignment_nature='SHARED'))
        assignments.append(EmployeeAssignment(employee_id=emp.id, brand_id=brand_map['SWF'].id, process_id=process_map['CS'].id, is_primary=(i == 14), skill_level=3, assignment_nature='SHARED'))
        assignments.append(EmployeeAssignment(employee_id=emp.id, brand_id=brand_map['URB'].id, process_id=process_map['CS'].id, is_primary=(i == 15), skill_level=3, assignment_nature='SHARED'))
        assignments.append(EmployeeAssignment(employee_id=emp.id, brand_id=brand_map['PGL'].id, process_id=process_map['CS'].id, is_primary=(i == 16), skill_level=3, assignment_nature='SHARED'))

    # Pod Gamma -> Zest Logistics (Multi-Employee)
    # - Separate dedicated for NDR & CS, shared for ACC
    for i in range(18, 27):
        emp = emp_objects[i]
        assignments.append(EmployeeAssignment(
            employee_id=emp.id, brand_id=brand_map['ZST'].id, process_id=process_map['NDR'].id,
            is_primary=True, skill_level=4 if 'Senior' in emp.role or 'Lead' in emp.role else 3,
            assignment_nature='DEDICATED'
        ))
        assignments.append(EmployeeAssignment(
            employee_id=emp.id, brand_id=brand_map['ZST'].id, process_id=process_map['CS'].id,
            is_primary=False, skill_level=3, assignment_nature='SHARED'
        ))
        if i % 2 == 0:
            assignments.append(EmployeeAssignment(
                employee_id=emp.id, brand_id=brand_map['ZST'].id, process_id=process_map['ACC'].id,
                is_primary=False, skill_level=3, assignment_nature='SHARED'
            ))

    # Pod Delta -> Boutique Single-Resource Brands (CraftDen, BioHealth, ByteGadgets, NovaDecor) + Floaters
    # Dedicated assignments:
    assignments.append(EmployeeAssignment(employee_id=emp_objects[27].id, brand_id=brand_map['CRD'].id, process_id=process_map['CS'].id, is_primary=True, skill_level=4, assignment_nature='DEDICATED'))
    assignments.append(EmployeeAssignment(employee_id=emp_objects[28].id, brand_id=brand_map['BIO'].id, process_id=process_map['CS'].id, is_primary=True, skill_level=4, assignment_nature='DEDICATED'))
    assignments.append(EmployeeAssignment(employee_id=emp_objects[29].id, brand_id=brand_map['BYT'].id, process_id=process_map['CS'].id, is_primary=True, skill_level=4, assignment_nature='DEDICATED'))
    assignments.append(EmployeeAssignment(employee_id=emp_objects[30].id, brand_id=brand_map['NOV'].id, process_id=process_map['CS'].id, is_primary=True, skill_level=4, assignment_nature='DEDICATED'))

    # Shared backup assignments for remaining Pod Delta associates (cross-trained floaters):
    for i in range(31, 36):
        emp = emp_objects[i]
        assignments.append(EmployeeAssignment(employee_id=emp.id, brand_id=brand_map['CRD'].id, process_id=process_map['CS'].id, is_primary=False, skill_level=3, assignment_nature='SHARED'))
        assignments.append(EmployeeAssignment(employee_id=emp.id, brand_id=brand_map['BIO'].id, process_id=process_map['CS'].id, is_primary=False, skill_level=3, assignment_nature='SHARED'))
        assignments.append(EmployeeAssignment(employee_id=emp.id, brand_id=brand_map['BYT'].id, process_id=process_map['CS'].id, is_primary=False, skill_level=3, assignment_nature='SHARED'))
        assignments.append(EmployeeAssignment(employee_id=emp.id, brand_id=brand_map['NOV'].id, process_id=process_map['CS'].id, is_primary=False, skill_level=3, assignment_nature='SHARED'))
        # Universal emergency floaters can also support Apex Retail & Zest Logistics CS
        assignments.append(EmployeeAssignment(employee_id=emp.id, brand_id=brand_map['APX'].id, process_id=process_map['CS'].id, is_primary=False, skill_level=3, assignment_nature='SHARED'))
        assignments.append(EmployeeAssignment(employee_id=emp.id, brand_id=brand_map['ZST'].id, process_id=process_map['CS'].id, is_primary=False, skill_level=3, assignment_nature='SHARED'))

    db.session.add_all(assignments)

    # 8. Weekly Off Staggering Patterns
    stagger_patterns = [
        (6, None),  # Sun
        (5, None),  # Sat
        (0, None),  # Mon
        (2, None),  # Wed
        (3, None),  # Thu
        (1, None),  # Tue
        (5, 6),     # Sat + Sun (2-day off pattern for Accounts/support specialists)
    ]

    for idx, emp in enumerate(emp_objects):
        day1, day2 = stagger_patterns[idx % len(stagger_patterns)]
        pattern = 'FIXED' if day2 is not None else 'STAGGERED'
        db.session.add(WeeklyOffRule(
            employee_id=emp.id,
            preferred_day_1=day1,
            preferred_day_2=day2,
            pattern_type=pattern
        ))

    # 9. Realistic Public Holidays (Target year 2026)
    holidays = [
        Holiday(name='New Year Day', date=date(2026, 1, 1), is_mandatory=True),
        Holiday(name='Republic Day', date=date(2026, 1, 26), is_mandatory=True),
        Holiday(name='Holi Festival', date=date(2026, 3, 4), is_mandatory=True),
        Holiday(name='May Day / Labour Day', date=date(2026, 5, 1), is_mandatory=True),
        Holiday(name='Independence Day', date=date(2026, 8, 15), is_mandatory=True),
        Holiday(name='Gandhi Jayanti', date=date(2026, 10, 2), is_mandatory=True),
        Holiday(name='Diwali Festival', date=date(2026, 11, 8), is_mandatory=True),
        Holiday(name='Guru Nanak Jayanti', date=date(2026, 11, 24), is_mandatory=True),
        Holiday(name='Christmas Day', date=date(2026, 12, 25), is_mandatory=True)
    ]
    db.session.add_all(holidays)

    # 10. Sample Pre-Planned Leaves & Comp-Offs
    leaves = [
        LeaveRequest(employee_id=emp_objects[1].id, leave_type='PL', start_date=date(2026, 11, 10), end_date=date(2026, 11, 12), status='APPROVED', reason='Approved planned leave'),
        LeaveRequest(employee_id=emp_objects[13].id, leave_type='SL', start_date=date(2026, 11, 15), end_date=date(2026, 11, 16), status='APPROVED', reason='Approved sick leave'),
        LeaveRequest(employee_id=emp_objects[19].id, leave_type='CO', start_date=date(2026, 11, 20), end_date=date(2026, 11, 20), status='APPROVED', reason='Approved compensatory leave'),
        LeaveRequest(employee_id=emp_objects[27].id, leave_type='PL', start_date=date(2026, 11, 5), end_date=date(2026, 11, 6), status='APPROVED', reason='Approved planned leave')
    ]
    db.session.add_all(leaves)

    db.session.commit()
    print("[Seeder] Successfully seeded 36 employees, 4 pods, 10 brands (80% single-resource, 20% multi-resource), 3 operating calendars, separate & shared skills, weekly-offs, holidays, and leaves!")
