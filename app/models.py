from datetime import datetime, date
from app.extensions import db

class Employee(db.Model):
    __tablename__ = 'employees'

    id = db.Column(db.Integer, primary_key=True)
    emp_code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    role = db.Column(db.String(50), nullable=False, default='Associate')  # Pod Lead, Senior Associate, Associate, Trainee
    pod_id = db.Column(db.Integer, db.ForeignKey('pods.id', name='fk_employee_pod', use_alter=True), nullable=True)
    hire_date = db.Column(db.Date, default=date.today)
    is_active = db.Column(db.Boolean, default=True)
    max_consecutive_days = db.Column(db.Integer, default=6)

    # Relationships
    pod = db.relationship('Pod', foreign_keys=[pod_id], back_populates='members')
    assignments = db.relationship('EmployeeAssignment', back_populates='employee', cascade='all, delete-orphan')
    leave_requests = db.relationship('LeaveRequest', back_populates='employee', cascade='all, delete-orphan')
    roster_assignments = db.relationship('RosterAssignment', back_populates='employee', cascade='all, delete-orphan')
    weekly_off_rule = db.relationship('WeeklyOffRule', back_populates='employee', uselist=False, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'emp_code': self.emp_code,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'role': self.role,
            'pod_id': self.pod_id,
            'pod_name': self.pod.name if self.pod else 'Unassigned',
            'is_active': self.is_active,
            'max_consecutive_days': self.max_consecutive_days,
            'skills': [
                {
                    'brand_id': a.brand_id,
                    'brand_name': a.brand.name if a.brand else None,
                    'brand_code': a.brand.code if a.brand else None,
                    'process_id': a.process_id,
                    'process_name': a.process.name if a.process else None,
                    'process_code': a.process.code if a.process else None,
                    'is_primary': a.is_primary,
                    'skill_level': a.skill_level,
                    'assignment_nature': getattr(a, 'assignment_nature', 'DEDICATED')
                }
                for a in self.assignments
            ]
        }


class Pod(db.Model):
    __tablename__ = 'pods'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    lead_id = db.Column(db.Integer, db.ForeignKey('employees.id', name='fk_pod_lead', use_alter=True), nullable=True)
    description = db.Column(db.String(255), nullable=True)

    # Relationships
    lead = db.relationship('Employee', foreign_keys=[lead_id], post_update=True)
    members = db.relationship('Employee', foreign_keys=[Employee.pod_id], back_populates='pod')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'lead_id': self.lead_id,
            'lead_name': self.lead.name if self.lead else 'Vacant',
            'lead_code': self.lead.emp_code if self.lead else None,
            'description': self.description,
            'member_count': len(self.members)
        }


class Brand(db.Model):
    __tablename__ = 'brands'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    brand_type = db.Column(db.String(30), default='SINGLE_RESOURCE')  # 'SINGLE_RESOURCE' vs 'MULTI_RESOURCE'
    calendar_type = db.Column(db.String(40), default='365_DAYS')  # '365_DAYS', 'DAILY_EXCEPT_HOLIDAYS', 'SUNDAYS_HOLIDAYS_OFF'

    working_rules = db.relationship('WorkingDayRule', back_populates='brand', cascade='all, delete-orphan')
    assignments = db.relationship('EmployeeAssignment', back_populates='brand', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'is_active': self.is_active,
            'brand_type': self.brand_type,
            'calendar_type': self.calendar_type
        }


class Process(db.Model):
    __tablename__ = 'processes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)  # CS, ACC, NDR
    description = db.Column(db.String(255), nullable=True)
    color_code = db.Column(db.String(20), default='#0d6efd')

    working_rules = db.relationship('WorkingDayRule', back_populates='process', cascade='all, delete-orphan')
    assignments = db.relationship('EmployeeAssignment', back_populates='process', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'color_code': self.color_code
        }


class EmployeeAssignment(db.Model):
    __tablename__ = 'employee_assignments'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    process_id = db.Column(db.Integer, db.ForeignKey('processes.id'), nullable=False)
    is_primary = db.Column(db.Boolean, default=True)
    skill_level = db.Column(db.Integer, default=3)  # 1 (Beginner) to 5 (Expert)
    assignment_nature = db.Column(db.String(30), default='DEDICATED')  # 'DEDICATED' (separate) vs 'SHARED' (shared)

    employee = db.relationship('Employee', back_populates='assignments')
    brand = db.relationship('Brand', back_populates='assignments')
    process = db.relationship('Process', back_populates='assignments')


class ShiftType(db.Model):
    __tablename__ = 'shift_types'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # Morning, Afternoon, Night, General
    code = db.Column(db.String(10), unique=True, nullable=False)  # M, A, N, G
    start_time = db.Column(db.String(10), nullable=False)  # e.g., '07:00'
    end_time = db.Column(db.String(10), nullable=False)    # e.g., '16:00'
    color_code = db.Column(db.String(20), default='#198754')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'color_code': self.color_code
        }


class WorkingDayRule(db.Model):
    __tablename__ = 'working_day_rules'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    process_id = db.Column(db.Integer, db.ForeignKey('processes.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 6=Sunday
    is_operating = db.Column(db.Boolean, default=True)
    min_staff_required = db.Column(db.Integer, default=1)
    shift_type_id = db.Column(db.Integer, db.ForeignKey('shift_types.id'), nullable=True)
    operating_calendar = db.Column(db.String(40), default='365_DAYS')  # '365_DAYS', 'DAILY_EXCEPT_HOLIDAYS', 'SUNDAYS_HOLIDAYS_OFF'

    brand = db.relationship('Brand', back_populates='working_rules')
    process = db.relationship('Process', back_populates='working_rules')
    shift_type = db.relationship('ShiftType')


class Holiday(db.Model):
    __tablename__ = 'holidays'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, unique=True, nullable=False)
    is_mandatory = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'date': self.date.strftime('%Y-%m-%d'),
            'is_mandatory': self.is_mandatory
        }


class LeaveRequest(db.Model):
    __tablename__ = 'leave_requests'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    leave_type = db.Column(db.String(20), nullable=False)  # PL (Planned), SL (Sick), CO (Comp Off), EM (Emergency)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='APPROVED')  # APPROVED, PENDING, REJECTED
    reason = db.Column(db.String(255), nullable=True)

    employee = db.relationship('Employee', back_populates='leave_requests')

    def to_dict(self):
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'employee_name': self.employee.name if self.employee else None,
            'employee_code': self.employee.emp_code if self.employee else None,
            'leave_type': self.leave_type,
            'start_date': self.start_date.strftime('%Y-%m-%d'),
            'end_date': self.end_date.strftime('%Y-%m-%d'),
            'status': self.status,
            'reason': self.reason
        }


class WeeklyOffRule(db.Model):
    __tablename__ = 'weekly_off_rules'

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=True)
    preferred_day_1 = db.Column(db.Integer, default=6)  # 0=Mon, ..., 6=Sun
    preferred_day_2 = db.Column(db.Integer, nullable=True)
    pattern_type = db.Column(db.String(30), default='STAGGERED')  # FIXED, ROTATIONAL, STAGGERED

    employee = db.relationship('Employee', back_populates='weekly_off_rule')


class RosterSchedule(db.Model):
    __tablename__ = 'roster_schedules'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), default='DRAFT')  # DRAFT, PUBLISHED, ARCHIVED
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    total_shifts_scheduled = db.Column(db.Integer, default=0)
    conflicts_count = db.Column(db.Integer, default=0)

    assignments = db.relationship('RosterAssignment', back_populates='roster', cascade='all, delete-orphan')
    conflicts = db.relationship('RosterConflict', back_populates='roster', cascade='all, delete-orphan')
    unavailability_incidents = db.relationship('UnavailabilityIncident', back_populates='roster', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'month': self.month,
            'year': self.year,
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
            'total_shifts_scheduled': self.total_shifts_scheduled,
            'conflicts_count': self.conflicts_count
        }


class RosterAssignment(db.Model):
    __tablename__ = 'roster_assignments'

    id = db.Column(db.Integer, primary_key=True)
    roster_id = db.Column(db.Integer, db.ForeignKey('roster_schedules.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=True)
    process_id = db.Column(db.Integer, db.ForeignKey('processes.id'), nullable=True)
    shift_type_id = db.Column(db.Integer, db.ForeignKey('shift_types.id'), nullable=True)
    assignment_type = db.Column(db.String(30), nullable=False, default='WORK')  # WORK, WEEKLY_OFF, LEAVE, HOLIDAY, COMP_OFF
    is_manual_override = db.Column(db.Boolean, default=False)
    notes = db.Column(db.String(255), nullable=True)

    roster = db.relationship('RosterSchedule', back_populates='assignments')
    employee = db.relationship('Employee', back_populates='roster_assignments')
    brand = db.relationship('Brand')
    process = db.relationship('Process')
    shift_type = db.relationship('ShiftType')

    def to_dict(self):
        return {
            'id': self.id,
            'roster_id': self.roster_id,
            'date': self.date.strftime('%Y-%m-%d'),
            'employee_id': self.employee_id,
            'employee_name': self.employee.name if self.employee else None,
            'employee_code': self.employee.emp_code if self.employee else None,
            'brand_id': self.brand_id,
            'brand_name': self.brand.name if self.brand else None,
            'brand_code': self.brand.code if self.brand else None,
            'process_id': self.process_id,
            'process_name': self.process.name if self.process else None,
            'process_code': self.process.code if self.process else None,
            'shift_type_id': self.shift_type_id,
            'shift_name': self.shift_type.name if self.shift_type else None,
            'shift_code': self.shift_type.code if self.shift_type else None,
            'shift_color': self.shift_type.color_code if self.shift_type else '#6c757d',
            'assignment_type': self.assignment_type,
            'is_manual_override': self.is_manual_override,
            'notes': self.notes
        }


class RosterConflict(db.Model):
    __tablename__ = 'roster_conflicts'

    id = db.Column(db.Integer, primary_key=True)
    roster_id = db.Column(db.Integer, db.ForeignKey('roster_schedules.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=True)
    conflict_type = db.Column(db.String(60), nullable=False)
    severity = db.Column(db.String(20), default='CRITICAL')  # CRITICAL, WARNING
    message = db.Column(db.Text, nullable=False)
    resolved = db.Column(db.Boolean, default=False)

    roster = db.relationship('RosterSchedule', back_populates='conflicts')
    employee = db.relationship('Employee')

    def to_dict(self):
        return {
            'id': self.id,
            'roster_id': self.roster_id,
            'date': self.date.strftime('%Y-%m-%d'),
            'employee_id': self.employee_id,
            'employee_name': self.employee.name if self.employee else None,
            'employee_code': self.employee.emp_code if self.employee else None,
            'conflict_type': self.conflict_type,
            'severity': self.severity,
            'message': self.message,
            'resolved': self.resolved
        }


class UnavailabilityIncident(db.Model):
    __tablename__ = 'unavailability_incidents'

    id = db.Column(db.Integer, primary_key=True)
    roster_id = db.Column(db.Integer, db.ForeignKey('roster_schedules.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(30), default='PENDING')  # PENDING, SUBSTITUTED, UNRESOLVED
    substituted_by_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    roster = db.relationship('RosterSchedule', back_populates='unavailability_incidents')
    employee = db.relationship('Employee', foreign_keys=[employee_id])
    substituted_by = db.relationship('Employee', foreign_keys=[substituted_by_id])

    def to_dict(self):
        return {
            'id': self.id,
            'roster_id': self.roster_id,
            'employee_id': self.employee_id,
            'employee_name': self.employee.name if self.employee else None,
            'date': self.date.strftime('%Y-%m-%d'),
            'reason': self.reason,
            'status': self.status,
            'substituted_by_id': self.substituted_by_id,
            'substituted_by_name': self.substituted_by.name if self.substituted_by else None,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }


def apply_sqlite_migrations(engine):
    """Safely adds missing columns to SQLite database without dropping existing tables."""
    with engine.connect() as conn:
        def add_column_if_missing(table, column, col_type):
            res = conn.execute(db.text(f"PRAGMA table_info({table})"))
            existing = [row[1] for row in res.fetchall()]
            if column not in existing:
                conn.execute(db.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()

        try:
            add_column_if_missing('brands', 'brand_type', "VARCHAR(30) DEFAULT 'SINGLE_RESOURCE'")
            add_column_if_missing('brands', 'calendar_type', "VARCHAR(40) DEFAULT '365_DAYS'")
            add_column_if_missing('employee_assignments', 'assignment_nature', "VARCHAR(30) DEFAULT 'DEDICATED'")
            add_column_if_missing('working_day_rules', 'operating_calendar', "VARCHAR(40) DEFAULT '365_DAYS'")
        except Exception as e:
            print(f"[Migration] Column verification note: {e}")

