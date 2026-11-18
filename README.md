# Smart Roster Management System

> **DataStraw Internship Technical Assessment**  
> Local assessment implementation of deterministic workforce scheduling and roster management, built with Python Flask, SQLite, SQLAlchemy, and Bootstrap 5.

---

## 🌟 Executive Summary

The **Smart Roster Management System** demonstrates multi-brand, multi-process scheduling with a deterministic constraint-based scheduler. It records staffing gaps and rule violations for review; a generated roster is not guaranteed to meet every requirement when eligible staff are unavailable.

---

## 🚀 Quick Start Guide (VS Code / Local Execution)

The application can be run locally from this directory. A fresh checkout creates a local SQLite database on first startup; the database and real roster data are not included in the public source.

### 1. Prerequisites
- **Python 3.10+** (Tested on Python 3.12)
- **Git** (optional)
- **VS Code** (recommended)

### 2. Set Up a Clean Environment
Open your terminal inside this folder:

```powershell
# Step 1: Create Python Virtual Environment
python -m venv venv

# Step 2: Activate Virtual Environment
# On Windows PowerShell:
.\venv\Scripts\activate
# (On macOS/Linux: source venv/bin/activate)

# Step 3: Install Required Dependencies
python -m pip install -r requirements.txt

# Step 4: Create a private local secret and run the development server
$env:SECRET_KEY = & .\venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
python app.py
```

Open your browser and navigate to:
👉 **`http://127.0.0.1:5000`**

On first startup, SQLite schema and synthetic sample data are created: 36 employees, 10 brands, 3 processes (CS, ACC, NDR), 4 pods with designated leads, employee certifications, weekly-off rules, 9 holidays, approved leave examples, and three operating-calendar types. A November 2026 baseline roster is generated only when no roster exists. Existing assignments are not regenerated on startup; the latest roster is revalidated and its current findings are refreshed while prior conflict rows are retained.

The secret above is generated only for the current shell session. To use a `.env` file, copy `.env.example` to `.env`, replace its `SECRET_KEY` placeholder with a private random value, and never commit `.env`. The checked-in example contains no real secret.

Before making a major change to a populated local database, make a copy. Create the local backup folder if it does not exist:

```powershell
New-Item -ItemType Directory -Force .\backups
Copy-Item .\roster.db .\backups\roster_backup_before_work.db
```

---

## 🛠️ VS Code Debugging Setup

This project includes a VS Code debugger launch configuration in `.vscode/launch.json`:
1. Open this folder in VS Code: `File -> Open Folder... -> smart-roster-system`
2. Press `Ctrl+Shift+P` -> `Python: Select Interpreter` -> Select `.\venv\Scripts\python.exe`
3. Press `F5` or click **Run & Debug** in the sidebar to launch the server directly with hot reload and Jinja template debugging enabled.

---

## 📋 Comprehensive Assessment Requirements Matrix

| # | Requirement | Implementation Details | Status |
|---|---|---|:---:|
| **1** | **Employee Management** | 36 synthetic sample employees with roles (Pod Lead, Senior Associate, Associate, Trainee), codes (`DST001`-`DST036`), reserved `.invalid` email addresses, active status, and custom fatigue limits (`max_consecutive_days`). Filterable directory with search and add/edit forms. | ✅ Complete |
| **2** | **Brand Management** | 10 seeded brands: 2 multi-resource brands (**Apex Retail (`APX`)**, **Zest Logistics (`ZST`)**) and 8 single-resource brands (`LMN`, `SWF`, `URB`, `PGL`, `CRD`, `BIO`, `BYT`, `NOV`). Configurable operating rules per brand and process. | ✅ Complete |
| **3** | **Process Management** | 3 distinct operational processes: **Customer Support (`CS`)**, **Accounts (`ACC`)**, and **Non-Delivery Reports (`NDR`)**. Custom color badges and shift support. | ✅ Complete |
| **4** | **Pod & Pod Lead Management** | 4 operational pods (Apex Retail, boutique brands east, Zest Logistics, and boutique brands west/surge) with 9 employees and a designated lead per pod. | ✅ Complete |
| **5** | **Employee-Brand-Process Assignments** | Relational many-to-many certifications mapping employees to brand and process pairs with primary/secondary designations and skill levels (1-5). | ✅ Complete |
| **6** | **Weekly Offs, Leaves & Comp-Offs** | Staggered weekly rest patterns (Group A-F), public holidays (New Year, Republic Day, Diwali, etc.), planned leaves (PL), sick leaves (SL), and compensatory offs (CO). | ✅ Complete |
| **7** | **Brand & Process Working-Day Rules** | 98 day-of-week rules define whether each brand-process pair operates, its calendar type, shift, and minimum headcount. APX CS requires 2 staff daily; APX ACC is weekday-only; ZST CS/NDR require 2 staff daily. | ✅ Complete |
| **8** | **Monthly Automatic Roster Generation** | Deterministic scheduling balances workload, weekly rest, qualifications, pod affinity, and operating calendars. Any unsatisfied minimum staffing is recorded as a conflict. | ✅ Complete |
| **9** | **Minimum Staffing & Coverage Validation** | Calculates required vs. staffed headcount slots across every operating day; dashboard coverage is based on those slots, not the conflict count. | ✅ Complete |
| **10** | **Conflict Detection & Explanations** | Flags fatigue exceedance, approved leave, double-booking, overlapping shift times, uncertified assignments, closed operating days, and understaffing. Revalidation retains prior conflict rows and marks no-longer-current findings resolved. | ✅ Complete |
| **11** | **5 Multi-Dimensional Roster Views** | **1. Company-wide Matrix** (All employees vs Days 1..31)<br>**2. Pod-wise View** (Grouped by Pod with Pod Lead highlighted)<br>**3. Brand-wise View** (Daily fulfillment per Brand)<br>**4. Process-wise View** (CS vs ACC vs NDR breakdown)<br>**5. Employee-wise View** (Individual monthly calendar card). | ✅ Complete |
| **12** | **Manual Roster Editing with Revalidation** | Interactive shift badge modal with real-time AJAX constraint validation before saving, shift swapping between employees, and full roster revalidation. | ✅ Complete |
| **13** | **Emergency Unavailability & Backup Engine** | Post-generation call-out wizard that finds, scores, and ranks qualified backup candidates based on pod affinity, certification, rest day availability, and low monthly workload. Includes 1-click substitution. | ✅ Complete |
| **14** | **Export Roster to CSV & Excel** | CSV and four-sheet Excel workbook include brand-process-shift assignment labels, required vs. scheduled coverage (including shortfalls), conflict status/explanations, and unavailability/substitution history. | ✅ Complete |
| **15** | **Admin Dashboard** | Bootstrap 5 dashboard displays workforce KPIs, actual required-slot coverage, unresolved conflicts, operational pods, and roster actions. | ✅ Complete |

---

## 🧠 Scheduling Algorithm & Architectural Design

### Deterministic vs. Random Allocation
The scheduling engine (`app/services/scheduler.py`) uses a **greedy deterministic constraint-satisfaction algorithm**:
1. **Calendar Initialization**: Expands dates $1 \dots N$ for the given month and year.
2. **Fixed Anchor Placement**: Allocates approved leaves (`PL`, `SL`, `CO`) and official company holidays.
3. **Rest Day Guarantee**: Distributes staggered weekly offs based on employee preference groups ensuring that no employee works more than their assigned `max_consecutive_days` (default 6 days).
4. **Demand Matching**: For each operating day, sorts required Brand-Process requirements and queries eligible employees.
5. **Deterministic Multi-Factor Scoring**: Primary/dedicated certifications, skill rating, pod affinity, workload fairness, weekend balance, and lead supervision determine candidate order; ties are broken by employee code.
6. **Conflict Capture**: If staffing is mathematically unsolvable because qualified staff are unavailable, the validator logs the exact required and scheduled headcount instead of implying full coverage.

The dashboard's **Coverage Health** is `staffed required slots / total required slots`, capped at 100% so overstaffing cannot compensate for an uncovered requirement. **Logged Conflicts** counts unresolved validator findings separately. Revalidation marks findings that are no longer present as resolved rather than deleting their records.

---

## 📂 Project Structure

```
smart-roster-system/
│
├── app.py                      # Local Flask development-server entry point
├── wsgi.py                     # WSGI application and database initialization
├── config.py                   # App configurations (DevelopmentConfig, ProductionConfig, TestingConfig)
├── requirements.txt            # Runtime dependencies, including the Waitress WSGI server
├── .env.example                # Sample environment variables
├── README.md                   # Complete documentation and setup manual
│
├── .vscode/
│   └── launch.json             # VS Code debugger configuration
│
├── app/
│   ├── __init__.py             # Application factory (create_app) & blueprint registrations
│   ├── extensions.py           # SQLAlchemy database instance
│   ├── models.py               # ORM database models (Employee, Brand, Process, Pod, Shift, Roster)
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── seeder.py           # Populates synthetic employees, pods, brands, rules, and leave examples
│   │   ├── scheduler.py        # Core deterministic monthly roster scheduling algorithm
│   │   ├── operating_calendar.py # Shared operating-day/calendar rules
│   │   ├── validator.py        # Constraint evaluation & natural-language conflict explanations
│   │   ├── backup_engine.py    # Unavailability incident handler & ranked backup recommendation engine
│   │   └── exporter.py         # Multi-tab styled Excel (.xlsx) and CSV generators
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── dashboard.py        # KPI metrics, health gauges, and quick action cards
│   │   ├── employees.py        # Employee directory, CRUD, and skill certification manager
│   │   ├── operations.py       # Brands, Processes (CS, ACC, NDR), Pods, and working-day rules
│   │   ├── leaves.py           # Leaves, holidays, comp-offs, and weekly off rules
│   │   ├── roster.py           # Generation triggers, 5 dedicated views, exports, revalidation
│   │   └── api.py              # REST API endpoints for live modal validation, swaps, and backup assignment
│   │
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css       # Clean layout styling, responsive badges, sticky matrix columns
│   │   └── js/
│   │       ├── main.js         # Alerts and tooltips
│   │       └── roster_edit.js  # Live constraint validation, shift swap, and backup modal logic
│   │
│   └── templates/
│       ├── base.html           # Master layout with responsive sidebar navigation
│       ├── dashboard.html      # Operations KPI dashboard
│       ├── employees/
│       │   ├── list.html       # Searchable employee directory
│       │   └── form.html       # Add/Edit employee & domain certification manager
│       ├── operations/
│       │   ├── brands.html     # Brand management & working-day rules
│       │   ├── processes.html  # Process management (CS, ACC, NDR) & shift timings
│       │   └── pods.html       # Operational pods & pod lead assignments
│       ├── leaves/
│       │   ├── leaves_list.html # Planned leaves, sick leaves, comp-offs & holidays
│       │   └── rules.html      # Staggered weekly off preferences
│       └── roster/
│           ├── index.html      # Roster schedules hub
│           ├── company_view.html # View 1: Company-wide master matrix
│           ├── pod_view.html   # View 2: Pod-wise grouped view
│           ├── brand_view.html # View 3: Brand fulfillment view
│           ├── process_view.html # View 4: Process-wise coverage view
│           ├── employee_view.html # View 5: Individual employee calendar view
│           └── edit_modal.html # Modal partials for live shift editing & backup candidate ranking
│
└── tests/
    ├── __init__.py
    ├── test_config.py        # Production secret-key validation
    ├── test_scheduler.py       # Deterministic scheduler tests (constraints, rest days, leaves)
    ├── test_validator.py       # Intentional violation injection and detection tests
    ├── test_backup_engine.py   # Emergency unavailability and backup substitution tests
    └── test_routes.py          # HTTP routes, all 5 views, CSV, and Excel export tests
```

---

## 🧪 Automated Testing Suite

The automated suite contains 23 tests and uses an in-memory database so tests do not alter `roster.db`:

```powershell
# Run the complete test suite
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

To verify a clean dependency install in a separate environment, create and activate a new virtual environment, install only `requirements.txt`, and run the same test command. On PowerShell, for example:

```powershell
python -m venv .venv-clean
.\.venv-clean\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-clean\Scripts\python.exe -m unittest discover -s tests -v
```

### Verified Test Cases:
1. `test_database_seeder_workforce_count`: Verifies database is seeded with $\ge 30$ active employees.
2. `test_deterministic_scheduler_generation`: Verifies monthly schedule generation and persistence.
3. `test_hard_constraint_no_double_booking`: Proves no employee has $>1$ shift on any day.
4. `test_hard_constraint_max_consecutive_days`: Proves no employee exceeds their consecutive days limit without rest.
5. `test_hard_constraint_approved_leave_respected`: Proves employees on leave are never scheduled to work.
6. `test_hard_constraint_certification_mapping`: Proves employees are only scheduled for certified brands & processes.
7. `test_conflict_detection_scheduled_on_leave`: Verifies conflict engine detects intentional leave violations.
8. `test_single_assignment_instant_revalidation`: Verifies prevalidation catches uncertified assignments.
9. Calendar override validation: checks process-specific operating-day rules.
10. Overnight shift overlap validation: rejects overlapping shifts across dates.
11. Scheduler overlap prevention: avoids assigning an overnight shift that conflicts with the next day's shift.
12. Conflict-history validation: keeps prior findings as resolved history.
13. `test_backup_recommendation_and_substitution`: Exercises ranked backup candidates and a persisted substitution.
14. `test_dashboard_route`: Verifies the dashboard renders its KPIs.
15. Dashboard coverage test: compares staffed slots with required staffing.
16. `test_employees_list_route`: Verifies workforce directory loads.
17. `test_operations_routes`: Verifies Brands, Processes, and Pods routes.
18. `test_leaves_route`: Verifies Leaves and Holidays management.
19. `test_five_roster_views`: Verifies Company, Pod, Brand, Process, and Employee views.
20. Export tests: verify CSV and Excel content, coverage, conflict, and substitution worksheets.
21. Manual edit and revalidation: verifies API edits persist and conflict records remain.
22. Production config rejects a missing, placeholder, or short secret key.
23. Production config accepts a private strong secret and keeps debug mode disabled.

The synthetic November 2026 schedule requires **464 staffing slots**. The pre-existing local assessment database has 464/464 required slots filled but also contains 12 out-of-calendar work assignments, recorded as open warnings. Those findings are preserved and detailed below; the database is intentionally excluded from this public source. A clean checkout has a newly seeded database and will not reproduce that local roster state.

### Persisted Local Assessment Warnings (November 2026)

The local database used during the assessment contains **12 open `CALENDAR_VIOLATION` findings**: three work assignments on the Diwali holiday (**November 8**) and nine on Guru Nanak Jayanti (**November 24**). The affected brand/process pairs are:

| Date | Open holiday assignments |
|---|---|
| November 8 | LMN / CS, URB / CS, BIO / CS |
| November 24 | LMN / CS, BIO / CS, APX / NDR, APX / ACC, SWF / CS, PGL / CS, URB / CS, ZST / ACC, BYT / CS |

That saved roster has **476 work assignments**, of which 12 are on those closed holiday calendars; it covers all **464/464 required staffing slots**. Full required-slot coverage therefore does not mean every assignment is calendar-compliant. The 12 findings remain open, and 12 corresponding resolved history rows are retained from earlier revalidation. No assignments or database rows were changed for this GitHub-preparation work. The local database and its backups are excluded from upload; the counts above describe that existing local assessment data, not a clean installation.

---

## 🔒 Public Repository and Local Data

- Seed employee names are generic, emails use the reserved `.invalid` domain, and phone numbers are blank. Use only synthetic data in any public demonstration.
- `.gitignore` excludes local environment files, SQLite databases, backups, generated exports, caches, and local editor settings. Do not force-add them; they may contain personal employee information and roster records.
- `.env.example` is a template, not a production secret. Keep `.env` private and provide a strong secret through a secure deployment secret store.

## 💡 Operational Limitations & Deployment Readiness

- **Minimum Turnaround**: Shift-time overlap is rejected, but a longer minimum rest window between otherwise non-overlapping shifts is not currently enforced.
- **Approval Workflow**: Shift swaps and backup substitutions are applied with automated validation; there is no multi-party approval workflow.
- **Authentication and Authorization**: There is no login system or role-based access control. Do not expose this application to an untrusted network.
- **CSRF Protection**: Forms and state-changing routes do not have comprehensive CSRF protection.
- **Production Configuration**: `FLASK_ENV=production` requires an explicitly set, private `SECRET_KEY` and disables Flask debug mode. Waitress is included as a production WSGI server. For a local-only production-mode smoke run:

  ```powershell
  $env:FLASK_ENV = "production"
  $env:SECRET_KEY = & .\venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
  .\venv\Scripts\waitress-serve.exe --listen=127.0.0.1:5000 wsgi:app
  ```

- **Deployment Readiness**: This repository is prepared for source review, not production deployment. Authentication/authorization, CSRF defenses, security review of all state-changing routes, operational monitoring, backup/restore procedures, and a production data-retention policy remain necessary before deployment. Use a protected secret manager and terminate TLS at an appropriately configured reverse proxy for any real deployment.

---

## 👨‍💻 Submission Attribution
Developed for the **DataStraw Technologies Internship Assessment**.
Tested and verified on Windows with Python 3.12, Flask 3.0.3, SQLite 3, and Bootstrap 5.
