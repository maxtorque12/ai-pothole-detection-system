/**
 * Leaflet.js Map Initialization & Geospatial Defect Visualization
 * Centered on Connaught Place / Central Delhi [28.6139, 77.2090]
 */

const DEFAULT_CENTER = [28.6139, 77.2090];
const DEFAULT_ZOOM = 14;

// Global backend URL configuration (supports standalone or reverse-proxied hosting)
const BACKEND_BASE_URL = window.location.port === "5000" 
  ? window.location.origin 
  : "http://127.0.0.1:5000";

let map = null;
let markerLayerGroup = null;
let allPotholes = [];
const markerMap = new Map(); // id -> L.circleMarker

/**
 * Color scheme matching severity classification:
 * - High: Red (#EF4444)
 * - Medium: Orange (#F97316)
 * - Low: Yellow (#EAB308)
 */
const SEVERITY_COLORS = {
  high: { fill: "#EF4444", border: "#B91C1C", pulse: true },
  medium: { fill: "#F97316", border: "#C2410C", pulse: false },
  low: { fill: "#EAB308", border: "#A16207", pulse: false },
};

/**
 * Initializes the Leaflet map and tile layers.
 */
function initMap() {
  map = L.map("map", {
    center: DEFAULT_CENTER,
    zoom: DEFAULT_ZOOM,
    zoomControl: false,
  });

  // Re-position zoom controls to bottom-right
  L.control.zoom({ position: "bottomright" }).addTo(map);

  // OpenStreetMap standard tiles (100% free, public, no API key required)
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map);

  markerLayerGroup = L.layerGroup().addTo(map);
}

/**
 * Generates custom HTML for defect popups.
 */
function createPopupContent(pothole) {
  const sevKey = pothole.severity.toLowerCase();
  const colors = SEVERITY_COLORS[sevKey] || SEVERITY_COLORS.low;
  const timeStr = pothole.timestamp
    ? new Date(pothole.timestamp).toLocaleString()
    : "Unknown time";
  const confidencePct = Math.round((pothole.confidence || 0.8) * 100);
  const ratioPct = pothole.bbox_ratio ? (pothole.bbox_ratio * 100).toFixed(1) + "%" : "N/A";
  const streetName = pothole.street || `Coordinates: ${pothole.latitude.toFixed(5)}, ${pothole.longitude.toFixed(5)}`;
  const snapshotSrc = pothole.image_url 
    ? (pothole.image_url.startsWith("http") || pothole.image_url.startsWith("data:") 
        ? pothole.image_url 
        : `${BACKEND_BASE_URL}${pothole.image_url}`)
    : "";
  const cropSrc = pothole.crop_url
    ? (pothole.crop_url.startsWith("http") || pothole.crop_url.startsWith("data:")
        ? pothole.crop_url
        : `${BACKEND_BASE_URL}${pothole.crop_url}`)
    : "";

  let imagesHtml = "";
  if (snapshotSrc && cropSrc) {
    imagesHtml = `
      <div style="display:flex; gap:8px; margin: 8px 0;">
        <div style="flex:1;">
          <div style="font-size:10px; color:var(--text-muted); margin-bottom:3px; font-weight:600; text-transform:uppercase;">Scene Context</div>
          <div class="popup-image-wrap" style="height:90px;">
            <img src="${snapshotSrc}" alt="Road context" class="popup-image" onclick="openImageModal('${snapshotSrc}')" title="Click to view full scene" />
          </div>
        </div>
        <div style="flex:1;">
          <div style="font-size:10px; color:var(--text-muted); margin-bottom:3px; font-weight:600; text-transform:uppercase;">Defect Patch</div>
          <div class="popup-image-wrap" style="height:90px;">
            <img src="${cropSrc}" alt="Pothole crop" class="popup-image" onclick="openImageModal('${cropSrc}')" title="Click to view zoomed defect" />
          </div>
        </div>
      </div>
    `;
  } else if (snapshotSrc || cropSrc) {
    const src = snapshotSrc || cropSrc;
    imagesHtml = `
      <div class="popup-image-wrap">
        <img src="${src}" alt="Road defect snapshot" class="popup-image" onclick="openImageModal('${src}')"/>
      </div>
    `;
  }

  return `
    <div class="popup-container">
      <div class="popup-header" style="border-left: 4px solid ${colors.fill};">
        <div class="popup-title">Pothole #${(pothole.id || "").slice(-6).toUpperCase()}${pothole.track_id ? ` (Track #${pothole.track_id})` : ""}</div>
        <div class="popup-badges">
          <span class="badge badge-sev-${sevKey}">${pothole.severity.toUpperCase()}</span>
          <span class="badge badge-status-${pothole.status.replace("-", "")}">${pothole.status.toUpperCase()}</span>
        </div>
      </div>

      ${imagesHtml}

      <div class="popup-details">
        <div><b>Location:</b> ${streetName}</div>
        <div><b>Lat / Lon:</b> ${pothole.latitude.toFixed(5)}, ${pothole.longitude.toFixed(5)}</div>
        <div><b>Area Ratio:</b> ${ratioPct} (Severity: ${pothole.severity})</div>
        <div><b>Model Confidence:</b> ${confidencePct}%</div>
        <div><b>Detected:</b> ${timeStr}</div>
      </div>

      <div class="popup-actions">
        <label for="popup-status-${pothole.id}">Update Status:</label>
        <select id="popup-status-${pothole.id}" class="status-select" onchange="updatePotholeStatus('${pothole.id}', this.value)">
          <option value="reported" ${pothole.status === "reported" ? "selected" : ""}>Reported</option>
          <option value="in-progress" ${pothole.status === "in-progress" ? "selected" : ""}>In Progress</option>
          <option value="repaired" ${pothole.status === "repaired" ? "selected" : ""}>Repaired</option>
        </select>
      </div>
    </div>
  `;
}

/**
 * Updates rendered Leaflet circle markers based on current filtered items.
 *
 * @param {Array} items - List of pothole records to render.
 */
function updateMapMarkers(items) {
  if (!markerLayerGroup) return;
  markerLayerGroup.clearLayers();
  markerMap.clear();

  items.forEach((pothole) => {
    const sevKey = pothole.severity.toLowerCase();
    const config = SEVERITY_COLORS[sevKey] || SEVERITY_COLORS.low;

    // Radius proportional to severity
    const radius = sevKey === "high" ? 14 : (sevKey === "medium" ? 11 : 8);

    // Circle Marker
    const marker = L.circleMarker([pothole.latitude, pothole.longitude], {
      radius: radius,
      fillColor: config.fill,
      color: config.border,
      weight: 2.5,
      opacity: 0.95,
      fillOpacity: 0.75,
      className: config.pulse ? "marker-pulse" : "",
    });

    // Detailed popup
    marker.bindPopup(() => createPopupContent(pothole), {
      maxWidth: 320,
      minWidth: 260,
      className: "custom-leaflet-popup",
    });

    // Interaction on click
    marker.on("click", () => {
      highlightSidebarCard(pothole.id);
    });

    marker.addTo(markerLayerGroup);
    markerMap.set(pothole.id, marker);
  });
}

/**
 * Smoothly centers and zooms to a selected pothole and triggers its popup.
 *
 * @param {string} id - The ID of the defect to focus.
 */
function focusPothole(id) {
  const pothole = allPotholes.find((p) => p.id === id);
  if (!pothole || !map) return;

  map.flyTo([pothole.latitude, pothole.longitude], 16, {
    animate: true,
    duration: 1.0,
  });

  const marker = markerMap.get(id);
  if (marker) {
    setTimeout(() => {
      marker.openPopup();
    }, 1050);
  }

  highlightSidebarCard(id);
}

/**
 * Highlights and scrolls to the corresponding card in the sidebar.
 */
function highlightSidebarCard(id) {
  document.querySelectorAll(".work-order-card").forEach((card) => {
    card.classList.remove("selected");
  });
  const targetCard = document.getElementById(`card-${id}`);
  if (targetCard) {
    targetCard.classList.add("selected");
    targetCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

/**
 * Fetches defect records from GET /api/v1/potholes with automated fallback to mock_data.json.
 */
async function fetchPotholeData() {
  const statusIndicator = document.getElementById("connection-status");
  const apiUrl = `${BACKEND_BASE_URL}/api/v1/potholes`;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2500);

    const response = await fetch(apiUrl, { signal: controller.signal });
    clearTimeout(timeoutId);

    if (response.ok) {
      const json = await response.json();
      allPotholes = json.data || [];
      if (statusIndicator) {
        statusIndicator.className = "status-badge status-live";
        statusIndicator.textContent = "API LIVE";
      }
      applyFilters();
      return;
    }
  } catch (err) {
    console.warn("Backend API unreachable, activating mock_data.json fallback:", err.message);
  }

  // Automated Fallback to mock_data.json
  try {
    const mockResponse = await fetch("mock_data.json");
    if (mockResponse.ok) {
      allPotholes = await mockResponse.json();
      if (statusIndicator) {
        statusIndicator.className = "status-badge status-mock";
        statusIndicator.textContent = "OFFLINE (MOCK DATA)";
      }
      applyFilters();
      showToast("Loaded 5 sample pothole entries from mock_data.json.", "info");
    }
  } catch (mockErr) {
    console.error("Failed loading mock_data.json:", mockErr);
  }
}

/**
 * Modal image viewer for inspecting defect snapshots in high resolution.
 */
function openImageModal(src) {
  const modal = document.getElementById("image-modal");
  const modalImg = document.getElementById("modal-img");
  if (modal && modalImg) {
    modalImg.src = src;
    modal.classList.add("open");
  }
}

function closeImageModal() {
  const modal = document.getElementById("image-modal");
  if (modal) {
    modal.classList.remove("open");
  }
}

// Global bootstrap on window load
window.addEventListener("DOMContentLoaded", () => {
  initMap();
  initFilters();
  fetchPotholeData();

  // Sidebar toggle
  const toggleBtn = document.getElementById("sidebar-toggle");
  const dashboard = document.querySelector(".dashboard-layout");
  if (toggleBtn && dashboard) {
    toggleBtn.addEventListener("click", () => {
      dashboard.classList.toggle("sidebar-collapsed");
      setTimeout(() => map.invalidateSize(), 300);
    });
  }

  // Live Stream PiP toggle
  const liveToggleBtn = document.getElementById("live-stream-toggle");
  const livePip = document.getElementById("live-stream-pip");
  const pipClose = document.getElementById("pip-close");
  const pipVideoImg = document.getElementById("pip-video-img");

  if (liveToggleBtn && livePip) {
    liveToggleBtn.addEventListener("click", () => {
      livePip.classList.toggle("open");
      if (livePip.classList.contains("open") && pipVideoImg) {
        pipVideoImg.src = `${BACKEND_BASE_URL}/api/v1/live_stream?t=${Date.now()}`;
      }
    });
  }

  if (pipClose && livePip) {
    pipClose.addEventListener("click", () => {
      livePip.classList.remove("open");
    });
  }

  // Modal close handlers
  const modal = document.getElementById("image-modal");
  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal || e.target.classList.contains("modal-close")) {
        closeImageModal();
      }
    });
  }
});
