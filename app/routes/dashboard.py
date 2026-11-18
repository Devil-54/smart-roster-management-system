from datetime import date
from flask import Blueprint, render_template
from app.models import (
    Employee, Pod, Brand, Process, LeaveRequest,
    RosterSchedule, RosterConflict, UnavailabilityIncident
)
from app.services.validator import calculate_roster_coverage

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
def index():
    # Load KPIs
    total_employees = Employee.query.filter_by(is_active=True).count()
    total_brands = Brand.query.filter_by(is_active=True).count()
    total_processes = Process.query.count()
    total_pods = Pod.query.count()

    # Active or latest Roster
    latest_roster = RosterSchedule.query.order_by(RosterSchedule.year.desc(), RosterSchedule.month.desc()).first()

    open_conflicts = 0
    recent_conflicts = []
    coverage_health = 100.0
    coverage_required = 0
    coverage_staffed = 0

    if latest_roster:
        open_conflicts = RosterConflict.query.filter_by(roster_id=latest_roster.id, resolved=False).count()
        recent_conflicts = RosterConflict.query.filter_by(roster_id=latest_roster.id).order_by(RosterConflict.date.desc()).limit(6).all()
        coverage = calculate_roster_coverage(latest_roster.id)
        coverage_health = coverage['percentage']
        coverage_required = coverage['required']
        coverage_staffed = coverage['staffed']

    # Approved Leaves for current month
    today = date.today()
    pending_leaves = LeaveRequest.query.filter(
        LeaveRequest.status == 'APPROVED',
        LeaveRequest.end_date >= today
    ).count()

    # Recent unavailability incidents
    recent_incidents = UnavailabilityIncident.query.order_by(UnavailabilityIncident.created_at.desc()).limit(5).all()

    # Brands breakdown
    brands = Brand.query.all()
    pods = Pod.query.all()

    return render_template(
        'dashboard.html',
        total_employees=total_employees,
        total_brands=total_brands,
        total_processes=total_processes,
        total_pods=total_pods,
        latest_roster=latest_roster,
        open_conflicts=open_conflicts,
        coverage_health=coverage_health,
        coverage_required=coverage_required,
        coverage_staffed=coverage_staffed,
        recent_conflicts=recent_conflicts,
        pending_leaves=pending_leaves,
        recent_incidents=recent_incidents,
        brands=brands,
        pods=pods,
        today=today
    )
