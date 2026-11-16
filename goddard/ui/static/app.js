/**
 * Goddard Mission Control Dashboard - Interactive 3D & Telemetry Client
 */

// ── Global Application State ────────────────────────────────────────────────
const state = {
  revisions: [],
  activeRevId: null,
  activeRevisionId: null,
  activeRevData: null,
  activeMeshData: null,
  three: {
    scene: null,
    camera: null,
    renderer: null,
    controls: null,
    meshGroup: null,       // Root model group (rotates with autoSpin)
    activeGroup: null,     // Subgroup holding active rocket airframe
    ghostGroup: null,      // Subgroup holding dual-layer revision ghost
    solidMesh: null,
    wireframeMesh: null,
    gridHelper: null,
    axesHelper: null,
    rocketHeight: 0,
    rocketRadius: 0,
    autoSpin: false,
  },
  view: {
    wireframeOverlay: true,
    shadingMode: "solid", // "solid", "wireframe", "both"
    autoRotate: false,
    backdropMode: "liquid-glass",
  },
  ghost: {
    enabled: true,
    priorRevId: null,
    solidMesh: null,
    wireframeMesh: null,
    cache: new Map(),      // rev_id -> meshData
  },
  charts: {
    altitude: null,
    structural: null,
    mass: null,
  },
  overlay: { mode: 'solid', meshData: null, ghostMesh: null, currentMesh: null },
  audio: { muted: false, ctx: null },
};

// ── Initialization ──────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initThreeJS();
  initClock();
  initAudio();
  fetchRevisions();
  initKeyboardShortcuts();
  window.addEventListener("resize", onWindowResize);
});

// ── Clock ───────────────────────────────────────────────────────────────────
function initClock() {
  const clockEl = document.getElementById("clock-display");
  setInterval(() => {
    const now = new Date();
    const utcStr = now.toISOString().substring(11, 19);
    clockEl.textContent = `UTC ${utcStr}`;
  }, 1000);
}

// ── Three.js 3D Viewport Setup ──────────────────────────────────────────────
function initThreeJS() {
  const container = document.getElementById("threejs-canvas");
  const width = Math.max(container.clientWidth, 1);
  const height = Math.max(container.clientHeight, 1);

  // Scene - Liquid Glass mode is default (scene.background = null, scene.fog = null)
  const scene = new THREE.Scene();
  scene.background = null;
  scene.fog = null;
  state.three.scene = scene;

  // Camera
  const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 3000);
  camera.position.set(45, 30, 60);
  state.three.camera = camera;

  // Renderer - alpha enabled, high-performance powerPreference, premultipliedAlpha, zero clear color
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    powerPreference: "high-performance",
    premultipliedAlpha: true,
  });
  renderer.setSize(width, height);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x000000, 0.0);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.2;
  renderer.shadowMap.enabled = true;
  container.appendChild(renderer.domElement);
  state.three.renderer = renderer;

  // Controls
  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.maxDistance = 1500;
  controls.minDistance = 1;
  state.three.controls = controls;

  // Lighting
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.65);
  scene.add(ambientLight);

  const dirLight1 = new THREE.DirectionalLight(0xffffff, 1.4);
  dirLight1.position.set(60, 100, 80);
  scene.add(dirLight1);

  const dirLight2 = new THREE.DirectionalLight(0x00e5ff, 0.6);
  dirLight2.position.set(-60, 30, -60);
  scene.add(dirLight2);

  const dirLight3 = new THREE.DirectionalLight(0x38bdf8, 0.4);
  dirLight3.position.set(0, -40, 40);
  scene.add(dirLight3);

  // Synchronized Mesh Groups: meshGroup rotates; activeGroup and ghostGroup stay in lockstep
  const meshGroup = new THREE.Group();
  scene.add(meshGroup);
  state.three.meshGroup = meshGroup;

  const activeGroup = new THREE.Group();
  meshGroup.add(activeGroup);
  state.three.activeGroup = activeGroup;

  const ghostGroup = new THREE.Group();
  meshGroup.add(ghostGroup);
  state.three.ghostGroup = ghostGroup;

  // Grid & Triad
  const grid = new THREE.GridHelper(120, 60, 0x00e5ff, 0x1e293b);
  grid.position.y = 0;
  scene.add(grid);
  state.three.gridHelper = grid;

  const axes = new THREE.AxesHelper(15);
  axes.position.set(0, 0.1, 0);
  scene.add(axes);
  state.three.axesHelper = axes;

  // Animation Loop
  function animate() {
    requestAnimationFrame(animate);
    if ((state.view.autoRotate || state.three.autoSpin) && state.three.meshGroup) {
      state.three.meshGroup.rotation.y += 0.005;
    }
    controls.update();
    renderer.render(scene, camera);
  }
  animate();

  // Initialize Liquid Glass default backdrop mode
  setBackdropMode("liquid-glass");
}

function onWindowResize() {
  const container = document.getElementById("threejs-canvas");
  if (!container || !state.three.camera || !state.three.renderer) return;
  const width = Math.max(container.clientWidth, 1);
  const height = Math.max(container.clientHeight, 1);
  state.three.camera.aspect = width / height;
  state.three.camera.updateProjectionMatrix();
  state.three.renderer.setSize(width, height);
}

// ── 3D Mesh Rendering ───────────────────────────────────────────────────────
async function loadRevisionMesh(revId) {
  const hudTri = document.getElementById("hud-tri");
  if (hudTri) hudTri.innerHTML = '<span class="spinner"></span> LOADING...';

  try {
    let meshData;
    if (state.ghost.cache.has(revId)) {
      meshData = state.ghost.cache.get(revId);
    } else {
      const res = await fetch(`/api/revisions/${revId}/mesh`);
      if (!res.ok) throw new Error(`Mesh fetch failed: ${res.status}`);
      meshData = await res.json();
      state.ghost.cache.set(revId, meshData);
    }
    state.activeMeshData = meshData;
    state.overlay.meshData = meshData;

    renderMeshGeometry(meshData);
  } catch (err) {
    console.error("Error loading mesh:", err);
    if (hudTri) hudTri.textContent = "MESH ERROR";
  }
}

function renderMeshGeometry(meshData) {
  const { activeGroup, camera, controls } = state.three;
  if (!activeGroup) return;

  // Clear previous meshes from activeGroup
  while (activeGroup.children.length > 0) {
    const obj = activeGroup.children[0];
    if (obj.geometry) obj.geometry.dispose();
    if (obj.material) {
      if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
      else obj.material.dispose();
    }
    activeGroup.remove(obj);
  }

  const vertices = new Float32Array(meshData.vertices);
  const normals = new Float32Array(meshData.normals);

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(vertices, 3));
  geometry.setAttribute("normal", new THREE.BufferAttribute(normals, 3));

  // In Onshape, Z is vertical along rocket axis.
  // Transform geometry so rocket stands vertically along Three.js +Y axis:
  // (x, y, z) -> (x, z, -y)
  geometry.rotateX(-Math.PI / 2);
  geometry.computeBoundingBox();

  const bbox = geometry.boundingBox;
  const center = new THREE.Vector3();
  bbox.getCenter(center);
  const size = new THREE.Vector3();
  bbox.getSize(size);

  // Center on ground plane (Y = 0 at rocket base)
  geometry.translate(-center.x, -bbox.min.y, -center.z);

  const rocketHeight = size.y;
  const rocketRadius = Math.max(size.x, size.z) / 2.0;
  state.three.rocketHeight = rocketHeight;
  state.three.rocketRadius = rocketRadius;

  // Update HUD
  const hudLen = document.getElementById("hud-len");
  const hudDiam = document.getElementById("hud-diam");
  const hudTri = document.getElementById("hud-tri");
  if (hudLen) hudLen.textContent = `${rocketHeight.toFixed(2)} m`;
  if (hudDiam) hudDiam.textContent = `${(rocketRadius * 2.0).toFixed(2)} m`;
  if (hudTri && meshData.triangle_count !== undefined) hudTri.textContent = meshData.triangle_count.toLocaleString();

  // Solid Mesh Material (Aerospace Metallic finish)
  const solidMat = getCadSolidMaterial();
  const solidMesh = new THREE.Mesh(geometry, solidMat);
  solidMesh.castShadow = true;
  solidMesh.receiveShadow = true;
  activeGroup.add(solidMesh);
  state.three.solidMesh = solidMesh;

  // Wireframe Mesh Overlay
  const wireMat = new THREE.MeshBasicMaterial({
    color: 0x00e5ff,
    wireframe: true,
    transparent: true,
    opacity: 0.20,
  });
  const wireMesh = new THREE.Mesh(geometry, wireMat);
  activeGroup.add(wireMesh);
  state.three.wireframeMesh = wireMesh;

  // Apply active overlay (or default solid shading)
  const currentMode = state.overlay.mode || "solid";
  applyOverlayToMesh(meshData, currentMode);

  // Frame camera to comfortably fit the rocket
  const maxDim = Math.max(size.x, size.y, size.z);
  const fov = camera.fov * (Math.PI / 180);
  let cameraDist = Math.abs(maxDim / Math.tan(fov / 2)) * 0.75;
  cameraDist = Math.max(cameraDist, 10);

  camera.position.set(cameraDist * 0.75, rocketHeight * 0.55, cameraDist * 0.95);
  controls.target.set(0, rocketHeight * 0.45, 0);
  camera.lookAt(0, rocketHeight * 0.45, 0);
  controls.update();

  // Scale ground grid
  if (state.three.gridHelper) {
    state.three.gridHelper.scale.set(maxDim / 20, 1, maxDim / 20);
  }
}

// ── Viewport Control Actions ────────────────────────────────────────────────
function toggleShadingMode() {
  const btn = document.getElementById("btn-shading-mode");
  if (state.view.shadingMode === "solid") {
    state.view.shadingMode = "both";
    btn.textContent = "SHADING: SOLID + WIRE";
  } else if (state.view.shadingMode === "both") {
    state.view.shadingMode = "wireframe";
    btn.textContent = "SHADING: WIRE ONLY";
  } else {
    state.view.shadingMode = "solid";
    btn.textContent = "SHADING: SOLID";
  }
  applyShadingMode();
}

function applyShadingMode() {
  const { solidMesh, wireframeMesh } = state.three;
  if (!solidMesh || !wireframeMesh) return;

  if (state.view.shadingMode === "solid") {
    solidMesh.visible = true;
    wireframeMesh.visible = false;
  } else if (state.view.shadingMode === "wireframe") {
    solidMesh.visible = false;
    wireframeMesh.visible = true;
    wireframeMesh.material.opacity = 0.85;
  } else if (state.view.shadingMode === "both") {
    solidMesh.visible = true;
    wireframeMesh.visible = true;
    wireframeMesh.material.opacity = 0.25;
  }
}

function toggleWireframe() {
  const btn = document.getElementById("btn-wireframe");
  const wf = state.three.wireframeMesh;
  if (!wf) return;

  wf.visible = !wf.visible;
  btn.classList.toggle("active", wf.visible);
}

function toggleAutoRotate() {
  state.view.autoRotate = !state.view.autoRotate;
  document.getElementById("btn-autorotate").classList.toggle("active", state.view.autoRotate);
}

function resetCamera() {
  const { camera, controls, rocketHeight } = state.three;
  if (!camera || !controls) return;
  const dist = Math.max(rocketHeight * 1.2, 20);
  camera.position.set(dist * 0.75, rocketHeight * 0.55, dist * 0.95);
  controls.target.set(0, rocketHeight * 0.45, 0);
  controls.update();
}

// ── Data Fetching & Dashboard Updating ───────────────────────────────────────
async function fetchRevisions() {
  try {
    const res = await fetch("/api/revisions");
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();
    state.revisions = data;

    renderLineageSidebar();
    renderTradeSpaceCharts();

    if (data.length > 0) {
      // Default to the latest revision
      const latest = data[data.length - 1];
      selectRevision(latest.revision_id);
    } else {
      document.getElementById("active-rev-badge").textContent = "NO REVISIONS LOGGED";
    }
  } catch (err) {
    console.error("Failed to load revisions:", err);
    document.getElementById("active-rev-badge").textContent = "ERROR CONNECTING";
  }
}

function selectRevision(revId) {
  state.activeRevId = revId;
  state.activeRevisionId = revId;
  const rev = state.revisions.find(r => r.revision_id === revId);
  if (!rev) return;
  state.activeRevData = rev;

  // Update Sidebar active state
  document.querySelectorAll(".rev-card").forEach(el => {
    el.classList.toggle("active", parseInt(el.dataset.revId) === revId);
  });

  // Update Header Badge
  const badgeEl = document.getElementById("active-rev-badge");
  const isPassed = rev.compliance?.passed ?? true;
  badgeEl.className = `status-badge ${isPassed ? "" : "violation"}`;
  badgeEl.innerHTML = `● REV ${revId.toString().padStart(3, "0")}: ${rev.classification.toUpperCase()} · ${isPassed ? "PASS" : "VIOLATION"}`;

  // Update Right Panel: Requirements & Telemetry
  renderComplianceMatrix(rev);
  renderTelemetryRollup(rev);
  renderDiffTable(rev);

  // 3D Revision Ghosting: Determine predecessor N - 1
  const priorRevId = revId - 1;
  if (priorRevId >= 1) {
    updateRevisionGhost(priorRevId);
  } else {
    clearRevisionGhost();
  }

  // Load 3D Mesh
  loadRevisionMesh(revId);
}

// ── Render Sidebar (Design Lineage) ─────────────────────────────────────────
function renderLineageSidebar() {
  const container = document.getElementById("rev-list-container");
  container.innerHTML = "";
  document.getElementById("rev-count-chip").textContent = `${state.revisions.length} REVS`;

  state.revisions.slice().reverse().forEach(rev => {
    const card = document.createElement("div");
    card.className = `rev-card ${rev.revision_id === state.activeRevId ? "active" : ""}`;
    card.dataset.revId = rev.revision_id;
    card.onclick = () => selectRevision(rev.revision_id);

    const isPassed = rev.compliance?.passed ?? true;
    const inp = rev.inputs || {};
    const fm = rev.flight_metrics || {};
    const cad = rev.cad_metrics || {};

    const engines = inp.engine_count_stage1 || 1;
    const prop = inp.propellant || "LOX/CH4";
    const mat = inp.structural_material || "AL6061-T6";
    const apogeeKm = ((fm.apogee_m || 0) / 1000.0).toFixed(1);

    card.innerHTML = `
      <div class="rev-card-header">
        <span class="rev-badge">REV ${rev.revision_id.toString().padStart(2, "0")}</span>
        <span class="status-badge ${isPassed ? "" : "violation"}" style="font-size: 10px; padding: 2px 8px;">
          ${isPassed ? "PASS" : "VIOLATION"}
        </span>
      </div>
      <div class="rev-class">${rev.classification}</div>
      <div class="rev-specs">
        <span class="rev-tag">${engines}x ${prop}</span>
        <span class="rev-tag">${mat}</span>
        <span class="rev-tag">r=${inp.body_radius_m}m</span>
      </div>
      <div style="font-size: 11px; color: var(--text-dim); display: flex; justify-content: space-between; font-family: var(--font-mono);">
        <span>APOGEE: ${apogeeKm} km</span>
        <span>MASS: ${(cad.mass_kg || 0).toLocaleString()} kg</span>
      </div>
    `;
    container.appendChild(card);
  });
}

// ── Render Requirements Matrix ──────────────────────────────────────────────
function renderComplianceMatrix(rev) {
  const container = document.getElementById("compliance-matrix");
  const comp = rev.compliance || { passed: true, violations: [], badges: {} };
  const badges = comp.badges || {};
  const inp = rev.inputs || {};
  const fm = rev.flight_metrics || {};
  const fea = rev.fea_metrics || {};
  const vtvl = fm.vtvl_landing;

  // Overall status pill
  const overallPill = document.getElementById("overall-status-pill");
  overallPill.className = `status-badge ${comp.passed ? "" : "violation"}`;
  overallPill.textContent = comp.passed ? "ALL PASS (0 VIOLATIONS)" : `${comp.violations.length} VIOLATION(S)`;

  const targetOrbitKm = inp.target_orbit_km;
  const targetApogeeM = inp.target_apogee_m;
  const achievedAlt = targetOrbitKm ? `${(fm.apogee_m / 1000.0).toFixed(1)} km` : `${(fm.apogee_m || 0).toFixed(0)} m`;
  const targetAlt = targetOrbitKm ? `${targetOrbitKm} km Orbit` : `${targetApogeeM} m Suborbital`;

  const isTvc = inp.stabilization_mode === "tvc_guided";
  const stabVal = isTvc
    ? `${fm.tvc_metrics?.gimbal_angle_required_deg?.toFixed(2) || "0.00"}°`
    : `${fm.static_margin_calibers?.rail_departure?.toFixed(2) || "--"} cal`;
  const stabTarget = isTvc ? "Max 5.0° Authority" : "2.0 - 3.0 cal Static Margin";

  const cards = [
    {
      label: targetOrbitKm ? "ORBIT ALTITUDE" : "APOGEE ALTITUDE",
      val: achievedAlt,
      target: targetAlt,
      passed: badges.apogee_or_orbit !== false,
    },
    {
      label: isTvc ? "TVC GIMBAL AUTHORITY" : "LAUNCH STABILITY",
      val: stabVal,
      target: stabTarget,
      passed: badges.stability !== false,
    },
    {
      label: "STRUCTURAL YIELD FOS",
      val: `${fea.yield_fos?.toFixed(2) || "--"}x`,
      target: "Requirement >= 2.00x",
      passed: badges.structural_yield !== false,
    },
    {
      label: "BUCKLING LOAD FACTOR",
      val: `${fea.buckling_load_factor_blf?.toFixed(2) || "--"}x`,
      target: "NASA SP-8007 >= 2.00x",
      passed: badges.buckling_blf !== false,
    },
    {
      label: "MAX DYNAMIC PRESSURE",
      val: `${((fm.max_dynamic_pressure_pa || 0) / 1000.0).toFixed(1)} kPa`,
      target: "Limit <= 65.0 kPa",
      passed: badges.max_q !== false,
    },
  ];

  if (vtvl || inp.reusable_booster) {
    cards.push({
      label: "BOOSTER VTVL LANDING",
      val: `${vtvl?.touchdown_velocity_ms?.toFixed(2) || "--"} m/s`,
      target: `Soft Touchdown <= 2.50 m/s (${vtvl?.propellant_remaining_kg?.toLocaleString() || 0} kg margin)`,
      passed: badges.vtvl_landing !== false,
    });
  }

  container.innerHTML = cards.map(c => `
    <div class="gate-card ${c.passed ? "passed" : "failed"}">
      <div class="gate-label">${c.label}</div>
      <div class="gate-val" style="color: ${c.passed ? "#ffffff" : "var(--accent-red)"};">${c.val}</div>
      <div class="gate-target">${c.target}</div>
    </div>
  `).join("");
}

// ── Render Subsystem Telemetry Rollup ───────────────────────────────────────
function renderTelemetryRollup(rev) {
  const container = document.getElementById("telemetry-rollup");
  const inp = rev.inputs || {};
  const cad = rev.cad_metrics || {};
  const sizing = rev.sizing_metrics || {};
  const mass = sizing.mass_breakdown || {};
  const stages = sizing.stages || [];
  const s1 = stages[0] || {};

  const items = [
    { label: "AIRFRAME DRY MASS", val: `${(cad.mass_kg || 0).toLocaleString()} kg` },
    { label: "TOTAL WET MASS", val: `${((mass.total_wet_mass_kg || 0) / 1000.0).toFixed(1)} tons` },
    { label: "STAGE 1 THRUST", val: `${((s1.total_thrust_n || 0) / 1e6).toFixed(2)} MN` },
    { label: "PROPULSION CLUSTER", val: `${inp.engine_count_stage1 || 1}x ${inp.propellant || "LOX/CH4"}` },
    { label: "STRUCTURAL ALLOY", val: `${inp.structural_material || "AL6061-T6"}` },
    { label: "TANK WALL GAUGE", val: `${s1.tank_wall_thickness_mm?.toFixed(2) || "1.65"} mm` },
  ];

  container.innerHTML = items.map(item => `
    <div class="gate-card">
      <div class="gate-label">${item.label}</div>
      <div class="gate-val" style="font-size: 13px;">${item.val}</div>
    </div>
  `).join("");
}

// ── Render Parameter Diff Table ─────────────────────────────────────────────
function renderDiffTable(rev) {
  const tbody = document.getElementById("diff-table-body");
  const prev = state.revisions.find(r => r.revision_id === rev.revision_id - 1);

  if (!prev) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-dim); padding:14px;">BASELINE REVISION (NO PREVIOUS DATA)</td></tr>`;
    return;
  }

  const pInp = prev.inputs || {};
  const cInp = rev.inputs || {};
  const pCad = prev.cad_metrics || {};
  const cCad = rev.cad_metrics || {};
  const pFea = prev.fea_metrics || {};
  const cFea = rev.fea_metrics || {};
  const pFm = prev.flight_metrics || {};
  const cFm = rev.flight_metrics || {};

  const rows = [
    {
      param: "CAD Airframe Dry Mass",
      prev: `${(pCad.mass_kg || 0).toLocaleString()} kg`,
      curr: `${(cCad.mass_kg || 0).toLocaleString()} kg`,
      delta: (cCad.mass_kg || 0) - (pCad.mass_kg || 0),
      format: (d) => `${d >= 0 ? "+" : ""}${d.toLocaleString()} kg`,
    },
    {
      param: "Booster Outer Radius",
      prev: `${(pInp.body_radius_m || 0).toFixed(2)} m`,
      curr: `${(cInp.body_radius_m || 0).toFixed(2)} m`,
      delta: (cInp.body_radius_m || 0) - (pInp.body_radius_m || 0),
      format: (d) => `${d >= 0 ? "+" : ""}${d.toFixed(2)} m`,
    },
    {
      param: "First-Stage Engines",
      prev: `${pInp.engine_count_stage1 || 1}`,
      curr: `${cInp.engine_count_stage1 || 1}`,
      delta: (cInp.engine_count_stage1 || 1) - (pInp.engine_count_stage1 || 1),
      format: (d) => `${d >= 0 ? "+" : ""}${d}`,
    },
    {
      param: "Yield Safety Factor (FoS)",
      prev: `${pFea.yield_fos?.toFixed(2) || "--"}x`,
      curr: `${cFea.yield_fos?.toFixed(2) || "--"}x`,
      delta: (cFea.yield_fos || 0) - (pFea.yield_fos || 0),
      format: (d) => `${d >= 0 ? "+" : ""}${d.toFixed(2)}x`,
    },
    {
      param: "Buckling Margin (BLF)",
      prev: `${pFea.buckling_load_factor_blf?.toFixed(2) || "--"}x`,
      curr: `${cFea.buckling_load_factor_blf?.toFixed(2) || "--"}x`,
      delta: (cFea.buckling_load_factor_blf || 0) - (pFea.buckling_load_factor_blf || 0),
      format: (d) => `${d >= 0 ? "+" : ""}${d.toFixed(2)}x`,
    },
    {
      param: "Apogee / Orbit Altitude",
      prev: `${((pFm.apogee_m || 0) / 1000.0).toFixed(1)} km`,
      curr: `${((cFm.apogee_m || 0) / 1000.0).toFixed(1)} km`,
      delta: ((cFm.apogee_m || 0) - (pFm.apogee_m || 0)) / 1000.0,
      format: (d) => `${d >= 0 ? "+" : ""}${d.toFixed(1)} km`,
    },
  ];

  tbody.innerHTML = rows.map(r => {
    let deltaClass = "delta-neu";
    if (r.delta > 0) deltaClass = "delta-pos";
    else if (r.delta < 0) deltaClass = "delta-neg";

    return `
      <tr>
        <td><strong>${r.param}</strong></td>
        <td style="color:var(--text-dim);">${r.prev}</td>
        <td>${r.curr}</td>
        <td class="${deltaClass}">${r.format(r.delta)}</td>
      </tr>
    `;
  }).join("");
}

// ── Multi-Revision Trade-Space Charts (Chart.js) ─────────────────────────────
function renderTradeSpaceCharts() {
  const revs = state.revisions;
  if (!revs || revs.length === 0) return;

  const labels = revs.map(r => `Rev ${r.revision_id}`);

  // Chart defaults for dark theme
  Chart.defaults.color = "#94a3b8";
  Chart.defaults.borderColor = "rgba(255, 255, 255, 0.08)";
  Chart.defaults.font.family = "'JetBrains Mono', monospace";
  Chart.defaults.font.size = 10;

  // 1. Altitude Chart
  const altCtx = document.getElementById("chart-altitude");
  if (state.charts.altitude) state.charts.altitude.destroy();

  const apogees = revs.map(r => (r.flight_metrics?.apogee_m || 0) / 1000.0);
  state.charts.altitude = new Chart(altCtx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Achieved Altitude (km)",
          data: apogees,
          borderColor: "#00e5ff",
          backgroundColor: "rgba(0, 229, 255, 0.15)",
          borderWidth: 2,
          pointBackgroundColor: "#00e5ff",
          pointRadius: 4,
          tension: 0.25,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, title: { display: true, text: "km" } },
      },
    },
  });

  // 2. Structural Margins Chart (FoS & BLF with 2.0 safety limit line)
  const structCtx = document.getElementById("chart-structural");
  if (state.charts.structural) state.charts.structural.destroy();

  const fosData = revs.map(r => r.fea_metrics?.yield_fos || 0);
  const blfData = revs.map(r => r.fea_metrics?.buckling_load_factor_blf || 0);

  state.charts.structural = new Chart(structCtx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Yield FoS",
          data: fosData,
          borderColor: "#10b981",
          borderWidth: 2,
          pointBackgroundColor: "#10b981",
          pointRadius: 4,
        },
        {
          label: "Buckling BLF",
          data: blfData,
          borderColor: "#f59e0b",
          borderWidth: 2,
          pointBackgroundColor: "#f59e0b",
          pointRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "top", labels: { boxWidth: 10, padding: 6 } },
      },
      scales: {
        y: {
          min: 0,
          title: { display: true, text: "Margin Factor" },
        },
      },
    },
  });

  // 3. Mass Rollup (Tons)
  const massCtx = document.getElementById("chart-mass");
  if (state.charts.mass) state.charts.mass.destroy();

  const dryMass = revs.map(r => (r.cad_metrics?.mass_kg || 0) / 1000.0);
  const wetMass = revs.map(r => ((r.sizing_metrics?.mass_breakdown?.total_wet_mass_kg || 0) / 1000.0));

  state.charts.mass = new Chart(massCtx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Dry Mass (Tons)",
          data: dryMass,
          backgroundColor: "#38bdf8",
        },
        {
          label: "Wet Mass (Tons)",
          data: wetMass,
          backgroundColor: "rgba(59, 130, 246, 0.45)",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "top", labels: { boxWidth: 10, padding: 6 } },
      },
      scales: {
        y: { beginAtZero: true, title: { display: true, text: "Tons" } },
      },
    },
  });
}

// ── Engineering Bundle Download ─────────────────────────────────────────────
function downloadActiveBundle() {
  if (!state.activeRevId) return;
  const url = `/api/revisions/${state.activeRevId}/bundle`;
  const a = document.createElement("a");
  a.href = url;
  a.download = `Goddard_Rev_${state.activeRevId.toString().padStart(3, "0")}_Engineering_Package.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// ── Backdrop Mode Management ────────────────────────────────────────────────
const VALID_BACKDROP_MODES = ["liquid-glass", "deep-space", "cad-studio"];

const BACKDROP_CONFIGS = {
  "liquid-glass": {
    background: null,
    clearAlpha: 0.0,
    clearColor: 0x000000,
    fog: null,
  },
  "deep-space": {
    background: new THREE.Color(0x080c14),
    clearAlpha: 1.0,
    clearColor: 0x080c14,
    fog: new THREE.FogExp2(0x080c14, 0.003),
  },
  "cad-studio": {
    background: new THREE.Color(0x222834),
    clearAlpha: 1.0,
    clearColor: 0x222834,
    fog: new THREE.FogExp2(0x222834, 0.002),
  },
};

// Shorthand aliases for backwards compatibility
const BACKDROP_ALIASES = {
  "glass": "liquid-glass",
  "space": "deep-space",
  "studio": "cad-studio",
};

function setBackdropMode(mode) {
  // Normalize aliases if shorthand provided
  if (BACKDROP_ALIASES[mode]) {
    mode = BACKDROP_ALIASES[mode];
  }

  // Safe fallback to 'liquid-glass' on invalid or empty input
  if (!VALID_BACKDROP_MODES.includes(mode)) {
    mode = "liquid-glass";
  }

  if (!state.view) state.view = {};
  state.view.backdropMode = mode;

  const cfg = BACKDROP_CONFIGS[mode];
  const { scene, renderer } = state.three;

  // 1. Update Three.js scene background, fog, and clear color without modifying camera or meshes
  if (scene) {
    scene.background = cfg.background;
    scene.fog = cfg.fog;
  }
  if (renderer) {
    renderer.setClearColor(cfg.clearColor, cfg.clearAlpha);
  }

  // 2. Toggle CSS classes on document body and viewport container
  VALID_BACKDROP_MODES.forEach(m => {
    document.body.classList.remove(`mode-${m}`);
  });
  document.body.classList.add(`mode-${mode}`);

  const container = document.querySelector(".viewport-container");
  if (container) {
    VALID_BACKDROP_MODES.forEach(m => {
      container.classList.remove(`mode-${m}`);
    });
    container.classList.add(`mode-${mode}`);
  }

  // 3. Update HUD pill buttons
  document.querySelectorAll(".backdrop-btn").forEach(btn => {
    const btnMode = BACKDROP_ALIASES[btn.dataset.mode] || btn.dataset.mode;
    const isActive = btnMode === mode;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
  });

  // 4. Haptic feedback pulse via macOS AppKit bridge
  if (window.webkit?.messageHandlers?.goddardBridge) {
    window.webkit.messageHandlers.goddardBridge.postMessage({ action: "haptic", style: "generic" });
  }
}

// Backward compatibility alias
function setBackdrop(mode) {
  setBackdropMode(mode);
}

// ── Clean CAD Solid PBR Material ─────────────────────────────────────────────
function getCadSolidMaterial(materialName) {
  const name = materialName || state.activeRevData?.inputs?.structural_material || "AL6061-T6";
  let bodyColor = 0xe2e8f0; // Aluminum light metallic
  let metalness = 0.70;
  let roughness = 0.28;

  if (name.includes("SS304L")) {
    bodyColor = 0xd1d5db; // Stainless steel
    metalness = 0.85;
    roughness = 0.22;
  } else if (name.includes("Al-Li")) {
    bodyColor = 0xf8fafc; // Clean white/metallic
    metalness = 0.72;
    roughness = 0.26;
  } else if (name.includes("Carbon")) {
    bodyColor = 0x1f2937; // Dark carbon composite
    metalness = 0.25;
    roughness = 0.45;
  }

  return new THREE.MeshStandardMaterial({
    color: bodyColor,
    metalness: metalness,
    roughness: roughness,
    side: THREE.DoubleSide,
  });
}

// ── Google Turbo Colormap (11 Stops) ─────────────────────────────────────────
const TURBO_STOPS = [
  [0.0, 0.1900, 0.0718, 0.2322], // Deep violet #30123b
  [0.1, 0.2697, 0.3488, 0.7963], // Cobalt blue #4557c8
  [0.2, 0.2443, 0.6094, 0.9970], // Sky blue #2892eb
  [0.3, 0.0975, 0.8371, 0.8034], // Cyan #1ee0b7
  [0.4, 0.2760, 0.9709, 0.5165], // Neon green #64f131
  [0.5, 0.6436, 0.9900, 0.2336], // Bright lime #a4fc3c
  [0.6, 0.8833, 0.8655, 0.2172], // Yellow #fbe323
  [0.7, 0.9961, 0.6428, 0.1916], // Orange #fb8022
  [0.8, 0.9408, 0.3557, 0.0703], // Crimson #d82613
  [0.9, 0.7648, 0.1437, 0.0104], // Dark red #b60a1c
  [1.0, 0.4796, 0.0158, 0.0106], // Deep maroon #7a0403
];

function turboColormap(t) {
  t = Math.max(0.0, Math.min(1.0, t));
  const idx = Math.min(Math.floor(t * 10), 9);
  const s0 = TURBO_STOPS[idx];
  const s1 = TURBO_STOPS[idx + 1];
  const f = (t - s0[0]) / (s1[0] - s0[0]);
  return [
    s0[1] + f * (s1[1] - s0[1]),
    s0[2] + f * (s1[2] - s0[2]),
    s0[3] + f * (s1[3] - s0[3]),
  ];
}

function generateStressColors(stressField, yieldFos) {
  const N = stressField.length;
  const colors = new Float32Array(N * 3);
  const isViolation = (yieldFos !== undefined && yieldFos < 1.0);

  for (let i = 0; i < N; i++) {
    const s = stressField[i];
    let rgb;
    if (isViolation && s > 0.85) {
      rgb = [0.95, 0.05, 0.05]; // Alert crimson red
    } else {
      rgb = turboColormap(s);
    }
    colors[i * 3]     = rgb[0];
    colors[i * 3 + 1] = rgb[1];
    colors[i * 3 + 2] = rgb[2];
  }
  return colors;
}

// ── CFD Surface Pressure Aerodynamic Diverging Colormap ──────────────────────
const CFD_CP_STOPS = [
  [-0.60, 0.1137, 0.3098, 0.8471], // Deep Blue (#1d4ed8)
  [-0.30, 0.2196, 0.7412, 0.9725], // Sky Cyan (#38bdf8)
  [ 0.00, 0.9725, 0.9804, 0.9882], // Crisp White (#f8fafc)
  [ 0.40, 0.9608, 0.6196, 0.0431], // Amber Gold (#f59e0b)
  [ 1.00, 0.9373, 0.2667, 0.2667], // Stagnation Red (#ef4444)
];

function sampleCp(cp) {
  cp = Math.max(-0.6, Math.min(1.0, cp));
  for (let i = 0; i < CFD_CP_STOPS.length - 1; i++) {
    const s0 = CFD_CP_STOPS[i];
    const s1 = CFD_CP_STOPS[i + 1];
    if (cp <= s1[0] || i === CFD_CP_STOPS.length - 2) {
      const f = (cp - s0[0]) / (s1[0] - s0[0]);
      return [
        s0[1] + f * (s1[1] - s0[1]),
        s0[2] + f * (s1[2] - s0[2]),
        s0[3] + f * (s1[3] - s0[3]),
      ];
    }
  }
  return [0.9373, 0.2667, 0.2667];
}

function generateCpColors(cpField) {
  const N = cpField.length;
  const colors = new Float32Array(N * 3);
  for (let i = 0; i < N; i++) {
    const rgb = sampleCp(cpField[i]);
    colors[i * 3]     = rgb[0];
    colors[i * 3 + 1] = rgb[1];
    colors[i * 3 + 2] = rgb[2];
  }
  return colors;
}

// ── Multi-Physics Overlay & HUD Legend System ────────────────────────────────
function updateLegend(mode, meshData) {
  const legend = document.getElementById("physics-legend");
  const title = document.getElementById("legend-title");
  const bar = document.getElementById("legend-colorbar");
  const ticks = document.getElementById("legend-ticks");
  const footer = document.getElementById("legend-footer");

  if (!legend || !meshData) return;

  if (mode === "solid") {
    legend.style.display = "none";
    return;
  }

  legend.style.display = "block";

  if (mode === "stress") {
    if (title) title.textContent = "FEA VON MISES STRESS";
    if (bar) {
      bar.style.display = "block";
      bar.className = "legend-colorbar colorbar-turbo";
    }

    const peak = meshData.peak_von_mises_mpa || 185.4;
    const yieldStr = meshData.yield_strength_mpa || 276.0;
    const fos = meshData.yield_fos || (yieldStr / peak);
    const isViolation = fos < 1.0;

    if (ticks) {
      ticks.innerHTML = `
        <div><strong>${peak.toFixed(1)}</strong> MPa <span style="color:var(--text-dim);">Peak</span></div>
        <div><strong>${(peak * 0.75).toFixed(1)}</strong> MPa</div>
        <div><strong>${(peak * 0.50).toFixed(1)}</strong> MPa</div>
        <div><strong>${(peak * 0.25).toFixed(1)}</strong> MPa</div>
        <div><strong>0.0</strong> MPa</div>
      `;
    }

    if (footer) {
      footer.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span>YIELD FoS:</span>
          <span class="status-badge ${isViolation ? "violation" : ""}" style="font-size:10px; padding:1px 6px;">
            ${fos.toFixed(2)}x ${isViolation ? "ALERT" : "PASS"}
          </span>
        </div>
        <div style="color:var(--text-dim); margin-top:2px;">σ_yield: ${yieldStr.toFixed(1)} MPa</div>
      `;
    }
  } else if (mode === "cp") {
    if (title) title.textContent = "CFD SURFACE PRESSURE Cp";
    if (bar) {
      bar.style.display = "block";
      bar.className = "legend-colorbar colorbar-cp";
    }

    if (ticks) {
      ticks.innerHTML = `
        <div><strong>+1.00</strong> <span style="color:#ef4444;">Stagnation</span></div>
        <div><strong>+0.50</strong> Compression</div>
        <div><strong> 0.00</strong> <span style="color:#f8fafc;">Freestream</span></div>
        <div><strong>-0.30</strong> Shoulder Exp</div>
        <div><strong>-0.60</strong> <span style="color:#38bdf8;">Base Suction</span></div>
      `;
    }

    if (footer) {
      footer.innerHTML = `
        <div>AERODYNAMIC PRESSURE Cp</div>
        <div style="color:var(--text-dim); margin-top:2px;">Mach 1.5 Shock Field</div>
      `;
    }
  } else if (mode === "wireframe") {
    if (title) title.textContent = "GMSH MESH TOPOLOGY";
    if (bar) bar.style.display = "none";

    const triCount = (meshData.triangle_count || 0).toLocaleString();
    const vertCount = (meshData.vertex_count || (meshData.vertices ? meshData.vertices.length / 3 : 0)).toLocaleString();

    if (ticks) {
      ticks.innerHTML = `
        <div>TRIANGLES: <span style="color:var(--accent-cyan); font-weight:700;">${triCount}</span></div>
        <div>VERTICES: <span style="color:var(--accent-cyan);">${vertCount}</span></div>
        <div>TYPE: <span>3-Node Triangle</span></div>
        <div>CURVATURE: <span>Adaptive 6°</span></div>
      `;
    }

    if (footer) {
      footer.innerHTML = `
        <div style="color:var(--accent-cyan);">Gmsh 2D Boundary Elements</div>
      `;
    }
  }
}

function updateOverlayLegends(mode, meshData) {
  const stressLegend = document.getElementById("stress-legend");
  const cpLegend = document.getElementById("cp-legend");

  if (stressLegend) stressLegend.style.display = (mode === "stress") ? "block" : "none";
  if (cpLegend) cpLegend.style.display = (mode === "cp") ? "block" : "none";

  if (mode === "stress" && meshData) {
    const peakStressEl = document.getElementById("legend-peak-stress");
    const yieldFosEl = document.getElementById("legend-yield-fos");
    if (peakStressEl && meshData.peak_von_mises_mpa) {
      peakStressEl.textContent = `${meshData.peak_von_mises_mpa.toFixed(1)} MPa`;
    }
    if (yieldFosEl && meshData.yield_fos) {
      yieldFosEl.textContent = `Yield FoS: ${meshData.yield_fos.toFixed(2)}`;
    }
  }
}

function setOverlay(mode) {
  state.overlay.mode = mode;
  document.querySelectorAll('.overlay-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
  applyOverlayToMesh(state.overlay.meshData || state.activeMeshData, mode);
  if (window.webkit?.messageHandlers?.goddardBridge) {
    window.webkit.messageHandlers.goddardBridge.postMessage({ action: "haptic", style: "generic" });
  }
}

function buildGeometry(meshData) {
  const vertices = new Float32Array(meshData.vertices);
  const normals = new Float32Array(meshData.normals);
  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.BufferAttribute(vertices, 3));
  geom.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
  geom.rotateX(-Math.PI / 2);
  geom.computeBoundingBox();
  const bbox = geom.boundingBox;
  const center = new THREE.Vector3();
  bbox.getCenter(center);
  geom.translate(-center.x, -bbox.min.y, -center.z);
  return geom;
}

function lerp(a, b, t) { return a + (b - a) * t; }

function buildHeatmapMaterial(scalarField, colorStops) {
  const low = colorStops[0];
  const high = colorStops[colorStops.length - 1];
  const minVal = Math.min(...scalarField);
  const maxVal = Math.max(...scalarField);
  const range = maxVal - minVal || 1;
  const colors = [];
  for (const v of scalarField) {
    const t = (v - minVal) / range;
    const r = lerp(((low >> 16) & 0xff), ((high >> 16) & 0xff), t) / 255;
    const g = lerp(((low >> 8) & 0xff), ((high >> 8) & 0xff), t) / 255;
    const b = lerp((low & 0xff), (high & 0xff), t) / 255;
    colors.push(r, g, b);
  }
  return new THREE.MeshBasicMaterial({ vertexColors: true });
}

function applyOverlayToMesh(meshData, mode) {
  if (!meshData || !state.three.solidMesh) return;

  // Fallback to solid if scalar fields missing
  if (mode === "stress" && (!meshData.stress_field || meshData.stress_field.length === 0)) {
    mode = "solid";
    state.overlay.mode = "solid";
  } else if (mode === "cp" && (!meshData.cp_field || meshData.cp_field.length === 0)) {
    mode = "solid";
    state.overlay.mode = "solid";
  }

  const solidMesh = state.three.solidMesh;
  const wireframeMesh = state.three.wireframeMesh;
  const geom = solidMesh.geometry;

  if (mode === "solid") {
    // Mode A: Clean CAD Solid PBR
    solidMesh.material = getCadSolidMaterial();
    solidMesh.visible = (state.view.shadingMode !== "wireframe");
    if (wireframeMesh) {
      wireframeMesh.material = new THREE.MeshBasicMaterial({
        color: 0x00e5ff,
        wireframe: true,
        transparent: true,
        opacity: 0.20,
      });
      wireframeMesh.visible = (state.view.shadingMode === "both" || state.view.shadingMode === "wireframe");
    }
  } else if (mode === "stress" && meshData.stress_field) {
    // Mode B: FEA von Mises Stress Heatmap
    const yieldFos = meshData.yield_fos ?? ((meshData.yield_strength_mpa && meshData.peak_von_mises_mpa) ? (meshData.yield_strength_mpa / meshData.peak_von_mises_mpa) : 2.0);
    const stressColors = generateStressColors(meshData.stress_field, yieldFos);
    geom.setAttribute("color", new THREE.BufferAttribute(stressColors, 3));

    solidMesh.material = new THREE.MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.35,
      metalness: 0.15,
      side: THREE.DoubleSide,
    });
    solidMesh.visible = true;
    if (wireframeMesh) wireframeMesh.visible = false;
  } else if (mode === "cp" && meshData.cp_field) {
    // Mode C: CFD Surface Pressure Cp
    const cpColors = generateCpColors(meshData.cp_field);
    geom.setAttribute("color", new THREE.BufferAttribute(cpColors, 3));

    solidMesh.material = new THREE.MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.35,
      metalness: 0.15,
      side: THREE.DoubleSide,
    });
    solidMesh.visible = true;
    if (wireframeMesh) wireframeMesh.visible = false;
  } else if (mode === "wireframe") {
    // Mode D: Gmsh Boundary Wireframe Dual-Layer Composite
    solidMesh.material = new THREE.MeshStandardMaterial({
      color: 0x0a101d,
      transparent: true,
      opacity: 0.55,
      depthWrite: true,
      side: THREE.DoubleSide,
    });
    solidMesh.visible = true;

    if (wireframeMesh) {
      wireframeMesh.material = new THREE.MeshBasicMaterial({
        color: 0x00e5ff,
        wireframe: true,
        transparent: true,
        opacity: 0.90,
        depthTest: true,
      });
      wireframeMesh.visible = true;
    }
  }

  document.querySelectorAll('.overlay-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === mode);
  });

  updateLegend(mode, meshData);
  updateOverlayLegends(mode, meshData);
}

// ── 3D Revision Ghosting System ──────────────────────────────────────────────
async function updateRevisionGhost(priorRevId) {
  state.ghost.priorRevId = priorRevId;

  if (priorRevId < 1) {
    clearRevisionGhost();
    return;
  }

  if (!state.ghost.enabled) {
    if (state.three.ghostGroup) state.three.ghostGroup.visible = false;
    return;
  }

  // Check in-memory cache first
  if (state.ghost.cache.has(priorRevId)) {
    renderRevisionGhostGeometry(state.ghost.cache.get(priorRevId));
    return;
  }

  try {
    const res = await fetch(`/api/revisions/${priorRevId}/mesh`);
    if (!res.ok) {
      clearRevisionGhost();
      return;
    }
    const priorMeshData = await res.json();
    state.ghost.cache.set(priorRevId, priorMeshData);
    renderRevisionGhostGeometry(priorMeshData);
  } catch (err) {
    console.warn(`Could not load ghost mesh for Rev ${priorRevId}:`, err);
    clearRevisionGhost();
  }
}

function renderRevisionGhostGeometry(meshData) {
  const ghostGroup = state.three.ghostGroup;
  if (!ghostGroup || !meshData || !meshData.vertices) return;

  clearRevisionGhost();

  const vertices = new Float32Array(meshData.vertices);
  const normals = new Float32Array(meshData.normals);

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(vertices, 3));
  geometry.setAttribute("normal", new THREE.BufferAttribute(normals, 3));

  // Coordinate transform: Onshape Z-up to Three.js Y-up
  geometry.rotateX(-Math.PI / 2);
  geometry.computeBoundingBox();

  const bbox = geometry.boundingBox;
  const center = new THREE.Vector3();
  bbox.getCenter(center);

  // Ground plane datum translation (Y = 0 base datum)
  geometry.translate(-center.x, -bbox.min.y, -center.z);

  // Layer 1: Translucent Phantom Violet Solid Shell
  // Color 0x8b5cf6, transparent: true, opacity: 0.25, depthWrite: false
  const phantomSolidMat = new THREE.MeshBasicMaterial({
    color: 0x8b5cf6,
    transparent: true,
    opacity: 0.25,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const solidPhantomMesh = new THREE.Mesh(geometry, phantomSolidMat);
  solidPhantomMesh.renderOrder = 0;
  ghostGroup.add(solidPhantomMesh);
  state.ghost.solidMesh = solidPhantomMesh;

  // Layer 2: Glowing Neon Fuchsia Wireframe
  // Color 0xd946ef, wireframe: true, transparent: true, opacity: 0.65, depthWrite: false
  const phantomWireMat = new THREE.MeshBasicMaterial({
    color: 0xd946ef,
    wireframe: true,
    transparent: true,
    opacity: 0.65,
    depthWrite: false,
  });
  const wirePhantomMesh = new THREE.Mesh(geometry, phantomWireMat);
  wirePhantomMesh.renderOrder = 1;
  ghostGroup.add(wirePhantomMesh);
  state.ghost.wireframeMesh = wirePhantomMesh;

  ghostGroup.visible = state.ghost.enabled;
}

function clearRevisionGhost() {
  const ghostGroup = state.three.ghostGroup;
  if (!ghostGroup) return;
  while (ghostGroup.children.length > 0) {
    const obj = ghostGroup.children[0];
    if (obj.geometry) obj.geometry.dispose();
    if (obj.material) {
      if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
      else obj.material.dispose();
    }
    ghostGroup.remove(obj);
  }
  state.ghost.solidMesh = null;
  state.ghost.wireframeMesh = null;
}

function toggleRevisionGhosting() {
  state.ghost.enabled = !state.ghost.enabled;
  const btn = document.getElementById("btn-ghosting");
  if (btn) {
    btn.classList.toggle("active", state.ghost.enabled);
    btn.textContent = state.ghost.enabled ? "👻 GHOST: ON" : "👻 GHOST: OFF";
  }

  if (state.three.ghostGroup) {
    if (state.ghost.enabled && state.activeRevId > 1) {
      if (state.ghost.solidMesh) {
        state.three.ghostGroup.visible = true;
      } else {
        updateRevisionGhost(state.activeRevId - 1);
      }
    } else {
      state.three.ghostGroup.visible = false;
    }
  }

  // Tactile haptic feedback via macOS AppKit bridge
  if (window.webkit?.messageHandlers?.goddardBridge) {
    window.webkit.messageHandlers.goddardBridge.postMessage({
      action: "haptic",
      style: "generic",
    });
  }
  playAeroCue("click");
}

function showRevisionGhost(priorMeshData) {
  renderRevisionGhostGeometry(priorMeshData);
}

// ── Keyboard Shortcuts ───────────────────────────────────────────────────────
function initKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    const isMac = navigator.platform.includes('Mac');
    const mod = isMac ? e.metaKey : e.ctrlKey;
    if (mod && e.key === 'k') { e.preventDefault(); toggleCopilotDrawer(); }
    if (mod && e.key === 'r') { e.preventDefault(); triggerResimulateCurrent(); }
    if (mod && e.key === 'd') { e.preventDefault(); toggleDiffModal(); }
    if (mod && e.key === 'e') { e.preventDefault(); triggerExportBundle(); }
    if (e.key === ' ' && !e.target.matches('input,textarea')) { e.preventDefault(); toggleAutoSpin(); }
    if (e.key === 'Escape') { closeAllDrawers(); }
  });
}

function toggleCopilotDrawer() {
  const drawer = document.getElementById('copilot-drawer');
  if (drawer) drawer.classList.toggle('open');
}
function toggleAutoSpin() {
  state.three.autoSpin = !state.three.autoSpin;
}
function closeAllDrawers() {
  document.querySelectorAll('.drawer.open, .modal.open').forEach(el => el.classList.remove('open'));
}
function triggerResimulateCurrent() {
  showToast('Re-simulating...', 'info');
}
function triggerExportBundle() {
  const revId = state.activeRevisionId || 1;
  window.location.href = `/api/revisions/${revId}/bundle`;
}
function toggleDiffModal() {
  const modal = document.getElementById('diff-modal');
  if (modal) modal.classList.toggle('open');
}

// Copilot placeholders
function submitCopilotReview() {
  showToast('Copilot review submitted...', 'info');
}
function applyProposedDiff() {
  showToast('Applying diff to CAD...', 'info');
}

// ── Web Audio Aerospace Cues ─────────────────────────────────────────────────
function initAudio() {
  try { state.audio.ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch(e) {}
}

function playAeroCue(type) {
  if (state.audio.muted || !state.audio.ctx) return;
  const ctx = state.audio.ctx;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  if (type === 'complete') {
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(1760, ctx.currentTime + 0.3);
    gain.gain.setValueAtTime(0.1, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
    osc.start(); osc.stop(ctx.currentTime + 0.4);
  } else if (type === 'alert') {
    osc.frequency.setValueAtTime(220, ctx.currentTime);
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
    osc.start(); osc.stop(ctx.currentTime + 0.5);
  } else if (type === 'click') {
    osc.frequency.setValueAtTime(440, ctx.currentTime);
    gain.gain.setValueAtTime(0.05, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.08);
    osc.start(); osc.stop(ctx.currentTime + 0.08);
  }
}

// ── Toast Notification ───────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const t = document.createElement('div');
  t.style.cssText = `position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:rgba(0,229,255,0.15);backdrop-filter:blur(16px);border:1px solid rgba(0,229,255,0.3);color:#00e5ff;padding:10px 24px;border-radius:24px;font-size:13px;z-index:9999;pointer-events:none;transition:opacity 0.3s`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, 2000);
}
