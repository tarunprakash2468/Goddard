/**
 * Goddard Mission Control Dashboard - Interactive 3D & Telemetry Client
 */

// ── Global Application State ────────────────────────────────────────────────
const state = {
  revisions: [],
  activeRevId: null,
  activeRevData: null,
  activeMeshData: null,
  three: {
    scene: null,
    camera: null,
    renderer: null,
    controls: null,
    meshGroup: null,
    solidMesh: null,
    wireframeMesh: null,
    gridHelper: null,
    axesHelper: null,
    rocketHeight: 0,
    rocketRadius: 0,
  },
  view: {
    wireframeOverlay: true,
    shadingMode: "solid", // "solid", "wireframe", "both"
    autoRotate: false,
  },
  charts: {
    altitude: null,
    structural: null,
    mass: null,
  },
};

// ── Initialization ──────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initThreeJS();
  initClock();
  fetchRevisions();
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
  const width = container.clientWidth;
  const height = container.clientHeight;

  // Scene
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x080c14);
  scene.fog = new THREE.FogExp2(0x080c14, 0.003);
  state.three.scene = scene;

  // Camera
  const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 3000);
  camera.position.set(45, 30, 60);
  state.three.camera = camera;

  // Renderer
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(width, height);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
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

  // Mesh Group
  const meshGroup = new THREE.Group();
  scene.add(meshGroup);
  state.three.meshGroup = meshGroup;

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
    if (state.view.autoRotate && state.three.meshGroup) {
      state.three.meshGroup.rotation.y += 0.005;
    }
    controls.update();
    renderer.render(scene, camera);
  }
  animate();
}

function onWindowResize() {
  const container = document.getElementById("threejs-canvas");
  if (!container || !state.three.camera || !state.three.renderer) return;
  const width = container.clientWidth;
  const height = container.clientHeight;
  state.three.camera.aspect = width / height;
  state.three.camera.updateProjectionMatrix();
  state.three.renderer.setSize(width, height);
}

// ── 3D Mesh Rendering ───────────────────────────────────────────────────────
async function loadRevisionMesh(revId) {
  const hudTri = document.getElementById("hud-tri");
  hudTri.innerHTML = '<span class="spinner"></span> LOADING...';

  try {
    const res = await fetch(`/api/revisions/${revId}/mesh`);
    if (!res.ok) throw new Error(`Mesh fetch failed: ${res.status}`);
    const meshData = await res.json();
    state.activeMeshData = meshData;

    renderMeshGeometry(meshData);
  } catch (err) {
    console.error("Error loading mesh:", err);
    hudTri.textContent = "MESH ERROR";
  }
}

function renderMeshGeometry(meshData) {
  const { meshGroup, scene, camera, controls } = state.three;

  // Clear previous meshes
  while (meshGroup.children.length > 0) {
    const obj = meshGroup.children[0];
    if (obj.geometry) obj.geometry.dispose();
    if (obj.material) {
      if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
      else obj.material.dispose();
    }
    meshGroup.remove(obj);
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
  document.getElementById("hud-len").textContent = `${rocketHeight.toFixed(2)} m`;
  document.getElementById("hud-diam").textContent = `${(rocketRadius * 2.0).toFixed(2)} m`;
  document.getElementById("hud-tri").textContent = meshData.triangle_count.toLocaleString();

  // Solid Mesh Material (Aerospace Metallic finish)
  const matName = state.activeRevData?.inputs?.structural_material || "AL6061-T6";
  let bodyColor = 0xe2e8f0; // Aluminum light metallic
  let metalness = 0.65;
  let roughness = 0.32;

  if (matName.includes("SS304L")) {
    bodyColor = 0xd1d5db; // Stainless steel
    metalness = 0.85;
    roughness = 0.22;
  } else if (matName.includes("Al-Li")) {
    bodyColor = 0xf8fafc; // Clean white/metallic
    metalness = 0.70;
    roughness = 0.28;
  } else if (matName.includes("Carbon")) {
    bodyColor = 0x1f2937; // Dark carbon composite
    metalness = 0.25;
    roughness = 0.45;
  }

  const solidMat = new THREE.MeshStandardMaterial({
    color: bodyColor,
    metalness: metalness,
    roughness: roughness,
    side: THREE.DoubleSide,
  });

  const solidMesh = new THREE.Mesh(geometry, solidMat);
  solidMesh.castShadow = true;
  solidMesh.receiveShadow = true;
  meshGroup.add(solidMesh);
  state.three.solidMesh = solidMesh;

  // Wireframe Mesh Overlay
  const wireMat = new THREE.MeshBasicMaterial({
    color: 0x00e5ff,
    wireframe: true,
    transparent: true,
    opacity: 0.20,
  });
  const wireMesh = new THREE.Mesh(geometry, wireMat);
  meshGroup.add(wireMesh);
  state.three.wireframeMesh = wireMesh;

  applyShadingMode();

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
  state.three.gridHelper.scale.set(maxDim / 20, 1, maxDim / 20);
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
