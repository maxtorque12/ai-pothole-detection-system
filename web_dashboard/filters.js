/**
 * Client-Side Filtering, Metrics & Work-Order State Management
 * Coordinates filter state between Leaflet map markers and the sidebar work-order list.
 */

/**
 * Resolves media URLs safely across local and network clients without breaking on origins.
 */
function resolveMediaUrl(url) {
  if (!url) return "";
  if (url.startsWith("data:") || url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }
  const cleanPath = url.startsWith("/") ? url : `/${url}`;
  const base = typeof BACKEND_BASE_URL !== "undefined" ? BACKEND_BASE_URL : window.location.origin;
  return `${base}${cleanPath}`;
}

// Filter state
const filterState = {
  severity: "all",
  status: "all",
  search: "",
};

/**
 * Initializes filter pill buttons and search input.
 */
function initFilters() {
  // Severity filter pills
  const severityPills = document.querySelectorAll("[data-filter-severity]");
  severityPills.forEach((pill) => {
    pill.addEventListener("click", () => {
      severityPills.forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      filterState.severity = pill.getAttribute("data-filter-severity");
      applyFilters();
    });
  });

  // Status filter pills
  const statusPills = document.querySelectorAll("[data-filter-status]");
  statusPills.forEach((pill) => {
    pill.addEventListener("click", () => {
      statusPills.forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      filterState.status = pill.getAttribute("data-filter-status");
      applyFilters();
    });
  });

  // Search input
  const searchInput = document.getElementById("search-input");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      filterState.search = e.target.value.trim().toLowerCase();
      applyFilters();
    });
  }

  // Refresh data button
  const refreshBtn = document.getElementById("refresh-btn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      refreshBtn.classList.add("spinning");
      fetchPotholeData().finally(() => {
        setTimeout(() => refreshBtn.classList.remove("spinning"), 500);
      });
    });
  }

  // Flush all captured data button
  const flushBtn = document.getElementById("flush-btn");
  if (flushBtn) {
    flushBtn.addEventListener("click", async () => {
      if (!confirm("Flush all captured pothole records and snapshots?")) {
        return;
      }
      try {
        const resp = await fetch("/api/v1/potholes", { method: "DELETE" });
        if (resp.ok) {
          allPotholes = [];
          applyFilters();
          showToast("Captured potholes and images flushed successfully!", "info");
        } else {
          showToast("Failed to flush server data.", "error");
        }
      } catch (err) {
        showToast("Error communicating with server.", "error");
      }
    });
  }

  // Seed demo sample potholes button
  const seedBtn = document.getElementById("seed-btn");
  if (seedBtn) {
    seedBtn.addEventListener("click", async () => {
      try {
        const resp = await fetch("mock_data.json");
        if (resp.ok) {
          const sampleData = await resp.json();
          allPotholes = [...sampleData];
          renderPotholes();
          updateMetrics();
          applyFilters();
          // Pan map to first demo pothole
          if (map && allPotholes.length > 0) {
            map.flyTo([allPotholes[0].latitude, allPotholes[0].longitude], 15);
          }
          showToast("Loaded 5 realistic demo potholes with dual-image inspection!", "success");
        }
      } catch (err) {
        showToast("Failed loading demo data.", "error");
      }
    });
  }
}

/**
 * Applies current filterState to the allPotholes dataset, updates metrics,
 * filters Leaflet markers, and updates sidebar work-order cards.
 */
function applyFilters() {
  const filtered = allPotholes.filter((p) => {
    // Severity filter
    if (
      filterState.severity !== "all" &&
      p.severity.toLowerCase() !== filterState.severity.toLowerCase()
    ) {
      return false;
    }

    // Status filter
    if (
      filterState.status !== "all" &&
      p.status.toLowerCase() !== filterState.status.toLowerCase()
    ) {
      return false;
    }

    // Search query
    if (filterState.search) {
      const q = filterState.search;
      const idMatch = (p.id || "").toLowerCase().includes(q);
      const streetMatch = (p.street || "").toLowerCase().includes(q);
      const clusterMatch = (p.cluster_id || "").toLowerCase().includes(q);
      const sevMatch = (p.severity || "").toLowerCase().includes(q);
      if (!idMatch && !streetMatch && !clusterMatch && !sevMatch) {
        return false;
      }
    }

    return true;
  });

  // Update map markers
  if (typeof updateMapMarkers === "function") {
    updateMapMarkers(filtered);
  }

  // Update sidebar list
  renderWorkOrders(filtered);

  // Update summary counters
  updateMetrics();
}

/**
 * Computes and renders aggregate metric counts in the top navigation bar.
 */
function updateMetrics() {
  const total = allPotholes.length;
  const highSev = allPotholes.filter((p) => p.severity.toLowerCase() === "high").length;
  const inProgress = allPotholes.filter((p) => p.status.toLowerCase() === "in-progress").length;
  const repaired = allPotholes.filter((p) => p.status.toLowerCase() === "repaired").length;

  const countTotalEl = document.getElementById("count-total");
  const countHighEl = document.getElementById("count-high");
  const countProgressEl = document.getElementById("count-progress");
  const countRepairedEl = document.getElementById("count-repaired");

  if (countTotalEl) countTotalEl.textContent = total;
  if (countHighEl) countHighEl.textContent = highSev;
  if (countProgressEl) countProgressEl.textContent = inProgress;
  if (countRepairedEl) countRepairedEl.textContent = repaired;
}

/**
 * Sends a PATCH request to update the repair status of a pothole defect.
 *
 * @param {string} id - The ID of the pothole to update.
 * @param {string} newStatus - 'reported', 'in-progress', or 'repaired'.
 */
async function updatePotholeStatus(id, newStatus) {
  const pothole = allPotholes.find((p) => p.id === id);
  if (!pothole) return;

  const previousStatus = pothole.status;
  pothole.status = newStatus; // Optimistic update
  applyFilters();

  try {
    const patchUrl = `${BACKEND_BASE_URL}/api/v1/potholes/${encodeURIComponent(id)}`;
    const response = await fetch(patchUrl, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });

    if (response.ok) {
      const result = await response.json();
      showToast(`Work order #${id.slice(-6)} status updated to "${newStatus}".`, "success");
      // Update with server confirmed data if available
      if (result.data) {
        Object.assign(pothole, result.data);
        applyFilters();
      }
    } else {
      // Revert on server error
      pothole.status = previousStatus;
      applyFilters();
      showToast(`Status update failed (HTTP ${response.status}).`, "error");
    }
  } catch (err) {
    // If backend is offline, retain local state and inform user
    console.warn("Backend PATCH failed, retaining client state for offline demo:", err);
    showToast(`Status updated locally to "${newStatus}" (Offline Mode).`, "info");
  }
}

/**
 * Renders the work-order card list in the collapsible municipal sidebar.
 *
 * @param {Array} items - List of filtered defect objects.
 */
function renderWorkOrders(items) {
  const container = document.getElementById("work-order-list");
  if (!container) return;

  if (items.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="8" y1="12" x2="16" y2="12"></line>
        </svg>
        <p>No pothole defects match the active filters.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = items
    .map((item) => {
      const sevClass = `badge-sev-${item.severity.toLowerCase()}`;
      const statusClass = `badge-status-${item.status.replace("-", "")}`;
      const shortId = (item.id || "unknown").slice(-6).toUpperCase();
      const timeStr = item.timestamp
        ? new Date(item.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        : "Just now";
      const confidencePct = Math.round((item.confidence || 0.8) * 100);
      const ratioPct = item.bbox_ratio ? (item.bbox_ratio * 100).toFixed(1) + "%" : "N/A";
      const streetName = item.street || `Lat: ${item.latitude.toFixed(4)}, Lon: ${item.longitude.toFixed(4)}`;
      const thumb = item.crop_url || item.image_url;
      const thumbSrc = resolveMediaUrl(thumb);

      return `
        <div class="work-order-card" id="card-${item.id}" onclick="focusPothole('${item.id}')">
          <div class="card-header">
            <span class="card-id">#${shortId}${item.track_id ? ` <small style="color:var(--text-muted);font-weight:normal;">(ID #${item.track_id})</small>` : ""}</span>
            <div class="card-tags">
              <span class="badge ${sevClass}">${item.severity.toUpperCase()}</span>
              <span class="badge ${statusClass}">${item.status.toUpperCase()}</span>
            </div>
          </div>
          
          <div class="card-body" style="display:flex; justify-content:space-between; align-items:center; gap:10px;">
            <div style="flex:1;">
              <div class="card-street">${streetName}</div>
              <div class="card-meta">
                <span><b>Area:</b> ${ratioPct}</span>
                <span><b>Conf:</b> ${confidencePct}%</span>
                <span><b>Time:</b> ${timeStr}</span>
              </div>
            </div>
            ${thumbSrc ? `<img src="${thumbSrc}" alt="Pothole" style="width:48px; height:48px; object-fit:cover; border-radius:6px; border:1px solid var(--border-color); cursor:pointer; flex-shrink:0;" onclick="event.stopPropagation(); openImageModal('${thumbSrc}', 'Pothole #${shortId} Defect Snapshot')" title="Click to inspect in zoom viewer" />` : ""}
          </div>

          <div class="card-footer" onclick="event.stopPropagation()">
            <label class="status-label">Work Status:</label>
            <select class="status-select" onchange="updatePotholeStatus('${item.id}', this.value)">
              <option value="reported" ${item.status === "reported" ? "selected" : ""}>Reported</option>
              <option value="in-progress" ${item.status === "in-progress" ? "selected" : ""}>In Progress</option>
              <option value="repaired" ${item.status === "repaired" ? "selected" : ""}>Repaired</option>
            </select>
          </div>
        </div>
      `;
    })
    .join("");
}

/**
 * Toast notifications for status changes and system alerts.
 */
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("show");
  }, 10);

  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
