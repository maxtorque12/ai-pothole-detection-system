/**
 * Leaflet.js Map Initialization & Geospatial Defect Visualization
 * Centered on Mayur Vihar Phase 2, East Delhi [28.6186, 77.3013]
 */

const DEFAULT_CENTER = [28.6186, 77.3013];
const DEFAULT_ZOOM = 14;

// Global backend URL configuration (supports standalone or reverse-proxied hosting)
const BACKEND_BASE_URL = (window.location.protocol.startsWith("http"))
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
  high: { fill: "#EF4444", border: "#7F1D1D", pulse: true },
  medium: { fill: "#F97316", border: "#9A3412", pulse: false },
  low: { fill: "#0EA5E9", border: "#0369A1", pulse: false }, // High-contrast Vivid Sky Blue for clear OSM visibility
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
 * Safely resolves defect media URLs across local and remote devices.
 */
function resolveMediaUrl(url) {
  if (!url) return "";
  if (url.startsWith("data:") || url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }
  const cleanPath = url.startsWith("/") ? url : `/${url}`;
  return `${BACKEND_BASE_URL}${cleanPath}`;
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
  const snapshotSrc = resolveMediaUrl(pothole.image_url);
  const cropSrc = resolveMediaUrl(pothole.crop_url);

  let imagesHtml = "";
  const shortCode = (pothole.id || "").slice(-6).toUpperCase();
  if (snapshotSrc && cropSrc) {
    imagesHtml = `
      <div style="display:flex; gap:8px; margin: 8px 0;">
        <div style="flex:1;">
          <div style="font-size:10px; color:var(--text-muted); margin-bottom:3px; font-weight:600; text-transform:uppercase;">Scene Context</div>
          <div class="popup-image-wrap" style="height:90px;">
            <img src="${snapshotSrc}" alt="Road context" class="popup-image" onclick="openImageModal('${snapshotSrc}', 'Scene Context - #${shortCode}')" title="Click to view full scene" />
          </div>
        </div>
        <div style="flex:1;">
          <div style="font-size:10px; color:var(--text-muted); margin-bottom:3px; font-weight:600; text-transform:uppercase;">Defect Patch</div>
          <div class="popup-image-wrap" style="height:90px;">
            <img src="${cropSrc}" alt="Pothole crop" class="popup-image" onclick="openImageModal('${cropSrc}', 'Zoomed Defect Patch - #${shortCode}')" title="Click to view zoomed defect" />
          </div>
        </div>
      </div>
    `;
  } else if (snapshotSrc || cropSrc) {
    const src = snapshotSrc || cropSrc;
    imagesHtml = `
      <div class="popup-image-wrap">
        <img src="${src}" alt="Road defect snapshot" class="popup-image" onclick="openImageModal('${src}', 'Pothole #${shortCode}')"/>
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

  const coordCounts = new Map();
  const validLatLngs = [];

  items.forEach((pothole) => {
    const sevKey = pothole.severity.toLowerCase();
    const config = SEVERITY_COLORS[sevKey] || SEVERITY_COLORS.low;

    // Radius proportional to severity (clear visibility for all tiers)
    const radius = sevKey === "high" ? 16 : (sevKey === "medium" ? 14 : 12);

    // Coordinate collision dispersal: offset overlapping markers so every pothole is individually clickable
    const coordKey = `${pothole.latitude.toFixed(5)},${pothole.longitude.toFixed(5)}`;
    const count = coordCounts.get(coordKey) || 0;
    coordCounts.set(coordKey, count + 1);

    let displayLat = pothole.latitude;
    let displayLon = pothole.longitude;
    if (count > 0) {
      // Disperse in a rosette ring around the central point (~15m per ring)
      const angle = (count * 2 * Math.PI) / 6;
      const dist = 0.00014 * Math.ceil(count / 6);
      displayLat += dist * Math.cos(angle);
      displayLon += dist * Math.sin(angle) * 1.15;
    }
    validLatLngs.push([displayLat, displayLon]);

    // Circle Marker
    const marker = L.circleMarker([displayLat, displayLon], {
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

  // Automatically adjust map viewport to frame all reported potholes
  if (validLatLngs.length > 0 && map) {
    const bounds = L.latLngBounds(validLatLngs);
    if (bounds.isValid()) {
      map.fitBounds(bounds, { maxZoom: 16, padding: [40, 40] });
    }
  }
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

let currentModalZoom = 1.0;

/**
 * Modal image viewer for inspecting defect snapshots with interactive zoom controls.
 */
function openImageModal(src, title = "Defect Inspection Snapshot") {
  const modal = document.getElementById("image-modal");
  const modalImg = document.getElementById("modal-img");
  const titleEl = document.getElementById("modal-title");
  const zoomText = document.getElementById("modal-zoom-level");

  if (modal && modalImg) {
    modalImg.src = src;
    currentModalZoom = 1.0;
    modalImg.style.transform = "scale(1.0)";
    if (zoomText) zoomText.textContent = "100%";
    if (titleEl) titleEl.textContent = title;
    modal.classList.add("open");
  }
}

function adjustModalZoom(delta) {
  const modalImg = document.getElementById("modal-img");
  const zoomText = document.getElementById("modal-zoom-level");
  if (!modalImg) return;
  currentModalZoom = Math.min(Math.max(0.5, currentModalZoom + delta), 4.0);
  modalImg.style.transform = `scale(${currentModalZoom})`;
  if (zoomText) zoomText.textContent = `${Math.round(currentModalZoom * 100)}%`;
}

function toggleModalZoom() {
  adjustModalZoom(currentModalZoom >= 1.5 ? -1.0 : 1.0);
}

function resetModalZoom() {
  const modalImg = document.getElementById("modal-img");
  const zoomText = document.getElementById("modal-zoom-level");
  if (!modalImg) return;
  currentModalZoom = 1.0;
  modalImg.style.transform = "scale(1.0)";
  if (zoomText) zoomText.textContent = "100%";
}

function closeImageModal() {
  const modal = document.getElementById("image-modal");
  if (modal) {
    modal.classList.remove("open");
  }
}

// Global hotkeys (Escape to close, +/- to zoom)
window.addEventListener("keydown", (e) => {
  const modal = document.getElementById("image-modal");
  if (modal && modal.classList.contains("open")) {
    if (e.key === "Escape") {
      closeImageModal();
    } else if (e.key === "+" || e.key === "=") {
      adjustModalZoom(0.25);
    } else if (e.key === "-" || e.key === "_") {
      adjustModalZoom(-0.25);
    }
  }
});

let gpsWatchId = null;

/**
 * Broadcasts live satellite/Wi-Fi GPS coordinates from mobile browser to backend.
 */
function togglePhoneGpsSync() {
  const btn = document.getElementById("phone-gps-btn");
  const text = document.getElementById("phone-gps-text");

  if (gpsWatchId !== null) {
    navigator.geolocation.clearWatch(gpsWatchId);
    gpsWatchId = null;
    if (btn) {
      btn.style.background = "rgba(14, 165, 233, 0.15)";
      btn.style.color = "#38bdf8";
      btn.style.borderColor = "rgba(14, 165, 233, 0.4)";
    }
    if (text) text.textContent = "Sync Phone GPS";
    showToast("Phone GPS broadcast stopped.", "info");
    return;
  }

  if (!("geolocation" in navigator)) {
    showToast("Geolocation is not supported by your browser.", "error");
    return;
  }

  gpsWatchId = navigator.geolocation.watchPosition(
    (pos) => {
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      const accuracy = pos.coords.accuracy;

      fetch("/api/v1/telemetry/gps", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          latitude: lat,
          longitude: lon,
          accuracy: accuracy,
          timestamp: new Date().toISOString(),
        }),
      }).catch((err) => console.debug("GPS POST error:", err));

      if (btn) {
        btn.style.background = "rgba(16, 185, 129, 0.25)";
        btn.style.color = "#34d399";
        btn.style.borderColor = "#10b981";
      }
      if (text) text.textContent = `GPS: ${lat.toFixed(4)}, ${lon.toFixed(4)}`;
    },
    (err) => {
      console.warn("Geolocation watch error:", err);
      showToast(`GPS Error: ${err.message}`, "error");
    },
    { enableHighAccuracy: true, maximumAge: 1000 }
  );

  showToast("Broadcasting live phone satellite GPS to detector!", "success");
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
