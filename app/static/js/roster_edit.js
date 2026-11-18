// Roster Edit, Swap, and Backup Finder Interactivity
let currentRosterId = null;
let currentEmployeeId = null;
let currentDate = null;

function openEditModal(rosterId, empId, empName, empCode, dateStr, currentType, currentBrandId, currentProcId, currentShiftId) {
  currentRosterId = rosterId;
  currentEmployeeId = empId;
  currentDate = dateStr;

  document.getElementById('modalEmpName').innerText = `${empName} (${empCode})`;
  document.getElementById('modalDate').innerText = dateStr;

  // Set form inputs
  document.getElementById('editAssignmentType').value = currentType || 'WORK';
  document.getElementById('editBrandId').value = currentBrandId || '';
  document.getElementById('editProcessId').value = currentProcId || '';
  document.getElementById('editShiftId').value = currentShiftId || '';

  toggleWorkFields();
  triggerValidation();

  const modal = new bootstrap.Modal(document.getElementById('editShiftModal'));
  modal.show();
}

function toggleWorkFields() {
  const type = document.getElementById('editAssignmentType').value;
  const workFields = document.getElementById('workFieldsContainer');
  if (type === 'WORK') {
    workFields.style.display = 'block';
  } else {
    workFields.style.display = 'none';
  }
}

async function triggerValidation() {
  const feedbackDiv = document.getElementById('validationFeedback');
  const saveBtn = document.getElementById('saveEditBtn');
  feedbackDiv.innerHTML = '<div class="spinner-border spinner-border-sm text-primary"></div> Validating constraints...';
  feedbackDiv.className = 'alert alert-info py-2 my-2';
  feedbackDiv.style.display = 'block';

  const type = document.getElementById('editAssignmentType').value;
  const brandId = document.getElementById('editBrandId').value ? parseInt(document.getElementById('editBrandId').value) : null;
  const procId = document.getElementById('editProcessId').value ? parseInt(document.getElementById('editProcessId').value) : null;
  const shiftId = document.getElementById('editShiftId').value ? parseInt(document.getElementById('editShiftId').value) : null;

  try {
    const res = await fetch(`/api/roster/${currentRosterId}/validate_edit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        employee_id: currentEmployeeId,
        date: currentDate,
        assignment_type: type,
        brand_id: brandId,
        process_id: procId,
        shift_type_id: shiftId
      })
    });

    const data = await res.json();
    if (!data.valid) {
      let errHtml = '<strong><i class="fas fa-exclamation-triangle"></i> Constraint Violations:</strong><ul class="mb-0 mt-1 ps-3">';
      data.errors.forEach(err => { errHtml += `<li>${err}</li>`; });
      errHtml += '</ul>';
      feedbackDiv.className = 'alert alert-danger py-2 my-2';
      feedbackDiv.innerHTML = errHtml;
      saveBtn.disabled = true;
    } else {
      let msg = '<i class="fas fa-check-circle text-success"></i> All constraints satisfied.';
      if (data.warnings && data.warnings.length > 0) {
        msg += '<ul class="mb-0 mt-1 ps-3 text-warning">';
        data.warnings.forEach(w => { msg += `<li>${w}</li>`; });
        msg += '</ul>';
        feedbackDiv.className = 'alert alert-warning py-2 my-2';
      } else {
        feedbackDiv.className = 'alert alert-success py-2 my-2';
      }
      feedbackDiv.innerHTML = msg;
      saveBtn.disabled = false;
    }
  } catch (e) {
    feedbackDiv.className = 'alert alert-secondary py-2 my-2';
    feedbackDiv.innerHTML = 'Unable to connect to validator service.';
  }
}

async function saveShiftEdit() {
  const saveBtn = document.getElementById('saveEditBtn');
  saveBtn.disabled = true;
  saveBtn.innerText = 'Saving...';

  const type = document.getElementById('editAssignmentType').value;
  const brandId = document.getElementById('editBrandId').value ? parseInt(document.getElementById('editBrandId').value) : null;
  const procId = document.getElementById('editProcessId').value ? parseInt(document.getElementById('editProcessId').value) : null;
  const shiftId = document.getElementById('editShiftId').value ? parseInt(document.getElementById('editShiftId').value) : null;

  try {
    const res = await fetch(`/api/roster/${currentRosterId}/edit_assignment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        employee_id: currentEmployeeId,
        date: currentDate,
        assignment_type: type,
        brand_id: brandId,
        process_id: procId,
        shift_type_id: shiftId
      })
    });

    const data = await res.json();
    if (data.success) {
      window.location.reload();
    } else {
      alert('Error saving change: ' + data.message);
      saveBtn.disabled = false;
      saveBtn.innerText = 'Save Changes';
    }
  } catch (e) {
    alert('Failed to save assignment change.');
    saveBtn.disabled = false;
    saveBtn.innerText = 'Save Changes';
  }
}

// ==================== EMERGENCY UNAVAILABILITY & BACKUP ====================
function openBackupFinder() {
  // Hide edit modal and show backup modal
  bootstrap.Modal.getInstance(document.getElementById('editShiftModal')).hide();

  document.getElementById('backupEmpName').innerText = document.getElementById('modalEmpName').innerText;
  document.getElementById('backupDate').innerText = currentDate;

  const modal = new bootstrap.Modal(document.getElementById('backupModal'));
  modal.show();
  loadBackupCandidates();
}

async function loadBackupCandidates() {
  const container = document.getElementById('backupCandidatesList');
  container.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div><p class="mt-2 text-muted">Scanning certified resources and calculating scores...</p></div>';

  try {
    const res = await fetch(`/api/roster/${currentRosterId}/unavailability/candidates?employee_id=${currentEmployeeId}&date=${currentDate}`);
    const data = await res.json();

    if (!data.success || !data.candidates || data.candidates.length === 0) {
      container.innerHTML = '<div class="alert alert-warning">No eligible backup candidates found without violating constraints.</div>';
      return;
    }

    let html = '<div class="list-group">';
    data.candidates.forEach((cand, idx) => {
      const isTop = idx === 0;
      html += `
        <div class="list-group-item list-group-item-action p-3 mb-2 border rounded ${isTop ? 'border-primary' : ''}">
          <div class="d-flex w-100 justify-content-between align-items-center">
            <div>
              <h6 class="mb-1 fw-bold text-dark">
                ${cand.name} <span class="badge bg-secondary">${cand.emp_code}</span>
                ${isTop ? '<span class="badge bg-success ms-1"><i class="fas fa-star"></i> Top Recommendation</span>' : ''}
              </h6>
              <p class="mb-1 text-muted small">
                <i class="fas fa-layer-group"></i> ${cand.pod_name} | <strong>${cand.role}</strong> | Status today: <span class="badge bg-light text-dark border">${cand.status_on_day}</span>
              </p>
            </div>
            <div class="text-end">
              <span class="badge bg-primary fs-6 px-3 py-2">Score: ${cand.score}</span>
              <div class="mt-2">
                <button class="btn btn-sm btn-outline-primary fw-bold" onclick="executeBackupSubstitution(${cand.employee_id}, '${cand.name.replace(/'/g, "\\'")}')">
                  <i class="fas fa-user-check"></i> Assign as Backup
                </button>
              </div>
            </div>
          </div>
          <div class="mt-2 pt-2 border-top">
            <small class="text-secondary fw-semibold">Why this candidate?</small>
            <div class="d-flex flex-wrap gap-1 mt-1">
              ${cand.reasons.map(r => `<span class="badge bg-light text-secondary border">${r}</span>`).join('')}
            </div>
          </div>
        </div>
      `;
    });
    html += '</div>';
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = '<div class="alert alert-danger">Error fetching backup candidate recommendations.</div>';
  }
}

async function executeBackupSubstitution(backupEmpId, backupName) {
  const reason = prompt(`Enter reason for substituting ${backupName} for this shift:`, 'Emergency medical absence');
  if (!reason) return;

  try {
    const res = await fetch(`/api/roster/${currentRosterId}/unavailability/substitute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        absent_employee_id: currentEmployeeId,
        backup_employee_id: backupEmpId,
        date: currentDate,
        reason: reason
      })
    });

    const data = await res.json();
    if (data.success) {
      alert(data.message);
      window.location.reload();
    } else {
      alert('Substitution failed: ' + data.message);
    }
  } catch (e) {
    alert('Error executing backup substitution.');
  }
}
