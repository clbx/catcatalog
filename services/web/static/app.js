const CATALOG = "/api";
const PAGE_SIZE = 20;

let cats = [];
let selectedCatId = null;
let currentView = "all"; // "all", "unassigned", or a cat id
let currentPage = 0;
let lastPageFull = false; // true if last fetch returned PAGE_SIZE results

async function api(path, opts = {}) {
    const res = await fetch(CATALOG + path, {
        headers: { "Content-Type": "application/json", ...opts.headers },
        ...opts,
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
}

function cropUrl(key) {
    return CATALOG + "/crops/" + key;
}

function formatDate(iso) {
    if (!iso) return "Unknown";
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
    });
}

function formatTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
    });
}

function videoUrl(key) {
    return CATALOG + "/videos/" + key;
}

function confColor(c) {
    if (c >= 0.7) return "#4caf50";
    if (c >= 0.4) return "#ff9800";
    return "#e94560";
}

// --- Load data ---

let totalSightings = 0;
let unassignedCount = 0;

async function loadStats() {
    try {
        const s = await api("/stats");
        totalSightings = s.total_sightings;
        unassignedCount = s.unassigned_sightings;
        document.getElementById("stats").textContent =
            `${s.total_cats} cats, ${s.total_sightings} sightings`;
        renderCats();
    } catch (e) {
        console.error("Stats error:", e);
    }
}

async function loadCats() {
    try {
        cats = await api("/cats?limit=200");
        renderCats();
    } catch (e) {
        console.error("Cats error:", e);
    }
}

function setDetailVisible(show) {
    document.getElementById("detailPanelWrapper").style.display = show
        ? ""
        : "none";
}

function paginationParams() {
    return `limit=${PAGE_SIZE}&offset=${currentPage * PAGE_SIZE}`;
}

async function loadAllSightings(resetPage = true) {
    closeSidebar();
    selectedCatId = null;
    currentView = "all";
    if (resetPage) currentPage = 0;
    renderCats();
    setDetailVisible(false);
    document.getElementById("sightingsTitle").textContent = "All Sightings";
    try {
        const sightings = await api(`/sightings?${paginationParams()}`);
        lastPageFull = sightings.length === PAGE_SIZE;
        renderSightings(sightings);
    } catch (e) {
        console.error("Sightings error:", e);
    }
}

async function loadUnassignedSightings(resetPage = true) {
    closeSidebar();
    selectedCatId = null;
    currentView = "unassigned";
    if (resetPage) currentPage = 0;
    renderCats();
    setDetailVisible(false);
    document.getElementById("sightingsTitle").textContent =
        "Unassigned Sightings";
    try {
        const sightings = await api(
            `/sightings?unassigned=true&${paginationParams()}`,
        );
        lastPageFull = sightings.length === PAGE_SIZE;
        renderSightings(sightings);
    } catch (e) {
        console.error("Sightings error:", e);
    }
}

async function loadCatSightings(catId, resetPage = true) {
    const cat = cats.find((c) => c.id === catId);
    if (resetPage) currentPage = 0;
    document.getElementById("sightingsTitle").textContent = cat
        ? `${cat.name || "Unnamed"}'s Sightings`
        : "Sightings";
    try {
        const sightings = await api(
            `/cats/${catId}/sightings?${paginationParams()}`,
        );
        lastPageFull = sightings.length === PAGE_SIZE;
        renderSightings(sightings);
    } catch (e) {
        console.error("Cat sightings error:", e);
    }
}

function prevPage() {
    if (currentPage <= 0) return;
    currentPage--;
    reloadCurrentView();
}

function nextPage() {
    if (!lastPageFull) return;
    currentPage++;
    reloadCurrentView();
}

function reloadCurrentView() {
    if (currentView === "all") loadAllSightings(false);
    else if (currentView === "unassigned") loadUnassignedSightings(false);
    else loadCatSightings(currentView, false);
}

async function loadCatDetail(catId) {
    closeSidebar();
    selectedCatId = catId;
    currentView = catId;
    renderCats();
    setDetailVisible(true);
    loadCatSightings(catId);
    try {
        const cat = await api(`/cats/${catId}`);
        renderDetail(cat);
    } catch (e) {
        console.error("Detail error:", e);
    }
}

// --- Render ---

function renderCats() {
    const el = document.getElementById("catList");
    el.innerHTML =
        `<div class="cat-item${currentView === "all" ? " active" : ""}" onclick="loadAllSightings(); renderDetail(null);">
      <span class="name">All Sightings</span>
      <span class="count">${totalSightings}</span>
    </div>
    <div class="cat-item${currentView === "unassigned" ? " active" : ""}" onclick="loadUnassignedSightings(); renderDetail(null);">
      <span class="name">Unassigned</span>
      <span class="count">${unassignedCount}</span>
    </div>` +
        (cats.length === 0
            ? ""
            : '<div class="sidebar-divider"></div>' +
              cats
                  .map(
                      (c) => `
    <div class="cat-item${c.id === selectedCatId ? " active" : ""}" onclick="loadCatDetail(${c.id})">
      <span class="name">${esc(c.name || "Unnamed #" + c.id)}</span>
      <span class="count">${c.total_sightings}</span>
    </div>
  `,
                  )
                  .join(""));
}

function renderSightingCard(s) {
    const hasVideo = s.source_key && /\.(mp4|avi|mov|mkv)$/i.test(s.source_key);
    const assignedCat = s.cat_id ? cats.find((c) => c.id === s.cat_id) : null;
    const showDismiss = !assignedCat;
    return `
    <div class="sighting-card">
      <img src="${s.crop_key ? cropUrl(s.crop_key) : ""}" alt="crop" onerror="this.style.display='none'">
      <div class="sighting-info">
        ${
            assignedCat
                ? `<span class="assigned-cat">${esc(assignedCat.name || "Unnamed #" + assignedCat.id)}</span>`
                : `
        <div class="sighting-actions">
          <select onchange="assignSighting(${s.id}, this.value)">
            <option value="">Assign to cat...</option>
            ${cats.map((c) => `<option value="${c.id}">${esc(c.name || "Unnamed #" + c.id)}</option>`).join("")}
          </select>
        </div>`
        }
        <span class="timestamp-time">${formatTime(s.timestamp)}</span>
        <span class="confidence-subtle">${(s.confidence * 100).toFixed(0)}%</span>
        <div class="sighting-buttons">
          ${hasVideo ? `<button class="btn-video" onclick="playVideo('${esc(s.source_key)}')">View Video</button>` : ""}
          ${showDismiss ? `<button class="btn-dismiss" onclick="dismissSighting(${s.id})">Not a cat!</button>` : ""}
        </div>
      </div>
    </div>`;
}

function renderSightings(sightings) {
    const el = document.getElementById("sightingsList");
    if (sightings.length === 0) {
        el.innerHTML = '<div class="empty-state">No sightings</div>';
        return;
    }
    // Group by date
    const groups = {};
    for (const s of sightings) {
        const day = formatDate(s.timestamp);
        if (!groups[day]) groups[day] = [];
        groups[day].push(s);
    }
    el.innerHTML =
        Object.entries(groups)
            .map(([day, items]) => {
                const cards = items.map(renderSightingCard).join("");
                return `<div class="day-group"><div class="day-header">${day}</div>${cards}</div>`;
            })
            .join("") +
        `<div class="pagination">
      <button onclick="prevPage()" ${currentPage === 0 ? "disabled" : ""}>Previous</button>
      <span class="page-info">Page ${currentPage + 1}</span>
      <button onclick="nextPage()" ${!lastPageFull ? "disabled" : ""}>Next</button>
    </div>`;
}

function renderDetail(cat) {
    const el = document.getElementById("detailPanel");
    if (!cat) {
        el.innerHTML =
            '<div class="detail-empty">Select a cat to view details</div>';
        return;
    }
    el.innerHTML = `
    <div class="detail-header">
      <div class="cat-name" id="detailName">${esc(cat.name || "Unnamed #" + cat.id)}</div>
      <div class="cat-notes" id="detailNotes">${esc(cat.notes || "No notes")}</div>
      <div class="cat-meta">
        First seen: ${formatDate(cat.first_seen)}<br>
        Last seen: ${formatDate(cat.last_seen)}<br>
        Total sightings: ${cat.total_sightings}
      </div>
      <div class="btn-group">
        <button onclick="editCat(${cat.id})">Edit</button>
        <button class="secondary" onclick="deleteCat(${cat.id})">Delete</button>
      </div>
    </div>
  `;
}

// --- Actions ---

function toggleAddCat() {
    document.getElementById("addCatForm").classList.toggle("hidden");
}

async function createCat() {
    const name = document.getElementById("newCatName").value.trim();
    const notes = document.getElementById("newCatNotes").value.trim();
    if (!name) return;
    try {
        await api("/cats", {
            method: "POST",
            body: JSON.stringify({ name, notes: notes || null }),
        });
        document.getElementById("newCatName").value = "";
        document.getElementById("newCatNotes").value = "";
        toggleAddCat();
        loadCats();
        loadStats();
    } catch (e) {
        console.error("Create cat error:", e);
    }
}

async function assignSighting(sightingId, catId) {
    if (!catId) return;
    try {
        await api(`/sightings/${sightingId}`, {
            method: "PATCH",
            body: JSON.stringify({ cat_id: parseInt(catId) }),
        });
        if (currentView === "all") loadAllSightings();
        else if (currentView === "unassigned") loadUnassignedSightings();
        loadCats();
        loadStats();
    } catch (e) {
        console.error("Assign error:", e);
    }
}

async function dismissSighting(sightingId) {
    try {
        await api(`/sightings/${sightingId}`, { method: "DELETE" });
        reloadCurrentView();
        loadStats();
    } catch (e) {
        console.error("Dismiss error:", e);
    }
}

async function editCat(catId) {
    const cat = cats.find((c) => c.id === catId);
    if (!cat) return;
    const el = document.getElementById("detailPanel");
    el.innerHTML = `
    <div class="detail-header">
      <div class="form-group">
        <label>Name</label>
        <input id="editName" value="${esc(cat.name || "")}">
      </div>
      <div class="form-group">
        <label>Notes</label>
        <textarea id="editNotes">${esc(cat.notes || "")}</textarea>
      </div>
      <div class="btn-group">
        <button onclick="saveCat(${catId})">Save</button>
        <button class="secondary" onclick="loadCatDetail(${catId})">Cancel</button>
      </div>
    </div>
  `;
}

async function saveCat(catId) {
    const name = document.getElementById("editName").value.trim();
    const notes = document.getElementById("editNotes").value.trim();
    try {
        await api(`/cats/${catId}`, {
            method: "PATCH",
            body: JSON.stringify({ name, notes }),
        });
        loadCats();
        loadCatDetail(catId);
    } catch (e) {
        console.error("Save cat error:", e);
    }
}

async function deleteCat(catId) {
    if (!confirm("Delete this cat? It can be restored later.")) return;
    try {
        await api(`/cats/${catId}`, { method: "DELETE" });
        selectedCatId = null;
        loadCats();
        loadAllSightings();
        loadStats();
        document.getElementById("detailPanel").innerHTML =
            '<div class="detail-empty">Select a cat to view details</div>';
    } catch (e) {
        console.error("Delete error:", e);
    }
}

function playVideo(sourceKey, startTime = 0) {
    let modal = document.getElementById("videoModal");
    if (!modal) {
        modal = document.createElement("div");
        modal.id = "videoModal";
        modal.className = "video-modal";
        modal.innerHTML = `
      <div class="video-modal-backdrop" onclick="closeVideo()"></div>
      <div class="video-modal-content">
        <button class="video-modal-close" onclick="closeVideo()">&times;</button>
        <video id="videoPlayer" controls autoplay></video>
      </div>
    `;
        document.body.appendChild(modal);
    }
    const player = document.getElementById("videoPlayer");
    player.src = videoUrl(sourceKey);
    player.currentTime = startTime || 0;
    modal.classList.add("visible");
}

function closeVideo() {
    const modal = document.getElementById("videoModal");
    if (modal) {
        const player = document.getElementById("videoPlayer");
        player.pause();
        player.src = "";
        modal.classList.remove("visible");
    }
}

// --- Sidebar toggle ---

function toggleSidebar() {
    const panel = document.querySelector(".panel-cats");
    const overlay = document.querySelector(".sidebar-overlay");
    panel.classList.toggle("open");
    overlay.classList.toggle("visible");
}

function closeSidebar() {
    const panel = document.querySelector(".panel-cats");
    const overlay = document.querySelector(".sidebar-overlay");
    if (panel.classList.contains("open")) {
        panel.classList.remove("open");
        overlay.classList.remove("visible");
    }
}

function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
}

// --- Init ---
function updateHeaderHeight() {
    const h = document.querySelector("header").offsetHeight;
    document.documentElement.style.setProperty("--header-height", h + "px");
}
updateHeaderHeight();
window.addEventListener("resize", updateHeaderHeight);

loadStats();
loadCats().then(() => loadAllSightings());
