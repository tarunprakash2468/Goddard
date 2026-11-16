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
  cad: {
    connected: false,
    mode: "mock",
    document_id: "mock-doc-001",
    access_key_configured: false,
  },
  copilot: {
    vram: null,
    models: [],
    selectedModel: null,
    downloading: false,
    proposedModifications: null,
    optimizing: false,
  },
};

// ── Initialization ──────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initThreeJS();
  initClock();
  initAudio();
  fetchCadStatus();
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

  // Apply active focus preset if set
  if (state.three.cameraFocus && state.three.cameraFocus !== "full") {
    setCameraFocus(state.three.cameraFocus, false);
  }
}

// ── Camera Focus Presets & Smooth Framing ──────────────────────────────────
function setCameraFocus(target = "full", triggerEffects = true) {
  const { camera, controls, rocketHeight, rocketRadius } = state.three;
  if (!camera || !controls) return;

  const h = rocketHeight || 60.0;
  const r = rocketRadius || 1.85;

  const validTargets = ["full", "engines", "fins", "staging", "nose"];
  if (!validTargets.includes(target)) target = "full";

  state.three.cameraFocus = target;

  validTargets.forEach(t => {
    const btn = document.getElementById(`btn-cam-${t}`);
    if (btn) btn.classList.toggle("active", t === target);
  });

  if (target === "engines") {
    // Macro zoom directly into the engine cluster and nozzles at vehicle base
    const targetY = Math.min(2.5, Math.max(0.4, h * 0.02));
    const dist = Math.max(4.5, r * 3.8);
    controls.target.set(0, targetY, 0);
    camera.position.set(dist * 0.72, Math.max(1.2, r * 0.9), dist * 0.72);
  } else if (target === "fins") {
    // Zoom to aerodynamic stabilizing fins and lower empennage
    const targetY = Math.min(5.0, Math.max(1.5, r * 2.2));
    const dist = Math.max(6.5, r * 4.6);
    controls.target.set(0, targetY, 0);
    camera.position.set(dist * 0.8, targetY + 1.2, dist * 0.8);
  } else if (target === "staging") {
    // Zoom to interstage adapter
    const targetY = h * 0.70;
    const dist = Math.max(7.0, r * 4.5);
    controls.target.set(0, targetY, 0);
    camera.position.set(dist * 0.75, targetY, dist * 0.75);
  } else if (target === "nose") {
    // Zoom into aerodynamic nose cone / fairing curvature
    const targetY = h - Math.min(6.0, Math.max(2.0, h * 0.08));
    const dist = Math.max(5.5, r * 3.8);
    controls.target.set(0, targetY, 0);
    camera.position.set(dist * 0.7, h - Math.min(2.0, h * 0.03), dist * 0.7);
  } else {
    // Full vehicle overview framing
    const maxDim = Math.max(h, r * 2);
    const fov = camera.fov * (Math.PI / 180);
    let cameraDist = Math.abs(maxDim / Math.tan(fov / 2)) * 0.75;
    cameraDist = Math.max(cameraDist, 10);
    controls.target.set(0, h * 0.45, 0);
    camera.position.set(cameraDist * 0.75, h * 0.55, cameraDist * 0.95);
  }

  camera.lookAt(controls.target);
  controls.update();

  if (triggerEffects) {
    triggerHaptic("generic");
    playAeroCue("click");
  }
}

function resetCamera() {
  setCameraFocus("full", true);
}
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
  state.three.autoSpin = state.view.autoRotate;
  const btn = document.getElementById("btn-autorotate");
  if (btn) btn.classList.toggle("active", state.view.autoRotate);
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
  "design-studio": "cad-studio",
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
  triggerHaptic("generic");
  playAeroCue("click");
}

function showRevisionGhost(priorMeshData) {
  renderRevisionGhostGeometry(priorMeshData);
}

// ── WebKit IPC Bridge & Haptics ──────────────────────────────────────────────
function dispatchIPC(message) {
  let delivered = false;
  try {
    if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.goddardBridge) {
      window.webkit.messageHandlers.goddardBridge.postMessage(message);
      delivered = true;
    }
  } catch (err) {
    console.debug("WebKit IPC dispatch error:", err);
  }

  // Web fallback if running in standalone browser without AppKit WKWebView
  if (!delivered) {
    if (message.action === "haptic" && message.style) {
      fetch("/api/events/haptic", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ style: message.style }),
      }).catch(() => {});
    } else if (message.action === "playSound" && message.sound) {
      playAeroCue(message.sound);
    }
  }
  return delivered;
}

function triggerHaptic(style = "generic") {
  dispatchIPC({ action: "haptic", style: style });
  // If not delivered to WebKit, ensure the REST telemetry endpoint logs the haptic
  if (!window.webkit?.messageHandlers?.goddardBridge) {
    fetch("/api/events/haptic", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ style: style }),
    }).catch(() => {});
  }
}

function triggerSoundCue(soundName) {
  playAeroCue(soundName);
  dispatchIPC({ action: "playSound", sound: soundName });
}

// ── Web Audio Aerospace Cues ─────────────────────────────────────────────────
function initAudio() {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (AudioContextClass) {
      state.audio.ctx = new AudioContextClass();
    }
  } catch (e) {
    console.debug("Web Audio initialization skipped:", e);
  }

  // Restore persisted mute preferences
  const savedMuted = localStorage.getItem("goddard_audio_muted") || localStorage.getItem("goddard_muted");
  if (savedMuted !== null) {
    state.audio.muted = (savedMuted === "true");
    updateAudioMuteUI();
  }

  // Auto-resume AudioContext on first user interaction gesture
  const resumeAudioContext = () => {
    if (state.audio.ctx && state.audio.ctx.state === "suspended") {
      state.audio.ctx.resume().catch(() => {});
    }
    window.removeEventListener("click", resumeAudioContext);
    window.removeEventListener("keydown", resumeAudioContext);
  };
  window.addEventListener("click", resumeAudioContext, { once: true });
  window.addEventListener("keydown", resumeAudioContext, { once: true });
}

function playAeroCue(type) {
  if (state.audio.muted || !state.audio.ctx) return;
  const ctx = state.audio.ctx;
  if (ctx.state === "suspended") {
    ctx.resume().catch(() => {});
  }
  const now = ctx.currentTime;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);

  if (type === 'complete') {
    // Rising two-tone arpeggio (880 Hz -> 1760 Hz)
    osc.type = "sine";
    osc.frequency.setValueAtTime(880, now);
    osc.frequency.exponentialRampToValueAtTime(1760, now + 0.28);
    gain.gain.setValueAtTime(0.12, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.38);
    osc.start(now);
    osc.stop(now + 0.38);
  } else if (type === 'touchdown') {
    // Hoverslam touchdown harmonic chime (C5: 523.25Hz -> 659.25Hz -> 783.99Hz)
    osc.type = "triangle";
    osc.frequency.setValueAtTime(523.25, now);
    osc.frequency.exponentialRampToValueAtTime(659.25, now + 0.15);
    osc.frequency.exponentialRampToValueAtTime(783.99, now + 0.35);
    gain.gain.setValueAtTime(0.14, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.6);
    osc.start(now);
    osc.stop(now + 0.6);
  } else if (type === 'alert') {
    // Urgent alarm tone (220 Hz low square/sawtooth tone)
    osc.type = "sawtooth";
    osc.frequency.setValueAtTime(220, now);
    gain.gain.setValueAtTime(0.15, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
    osc.start(now);
    osc.stop(now + 0.45);
  } else if (type === 'warning') {
    // Advisory tone (370 Hz)
    osc.type = "sine";
    osc.frequency.setValueAtTime(370, now);
    gain.gain.setValueAtTime(0.08, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
    osc.start(now);
    osc.stop(now + 0.25);
  } else if (type === 'click') {
    // UI transient click
    osc.type = "sine";
    osc.frequency.setValueAtTime(440, now);
    gain.gain.setValueAtTime(0.05, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
    osc.start(now);
    osc.stop(now + 0.05);
  }
}

function updateAudioMuteUI() {
  const btn = document.getElementById("btn-audio-mute");
  const icon = document.getElementById("audio-mute-icon");
  if (icon) icon.textContent = state.audio.muted ? "🔇" : "🔊";
  if (btn) {
    btn.innerHTML = `<span id="audio-mute-icon">${state.audio.muted ? "🔇" : "🔊"}</span> AUDIO: ${state.audio.muted ? "MUTED" : "ON"}`;
    btn.classList.toggle("active", state.audio.muted);
  }
}

function toggleAudioMute(forceState) {
  state.audio.muted = (forceState !== undefined) ? !!forceState : !state.audio.muted;
  localStorage.setItem("goddard_audio_muted", state.audio.muted ? "true" : "false");
  localStorage.setItem("goddard_muted", state.audio.muted ? "true" : "false");
  updateAudioMuteUI();

  fetch("/api/audio/mute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ muted: state.audio.muted }),
  }).catch(() => {});

  dispatchIPC({ action: "toggleMute", muted: state.audio.muted });
  showToast(`Audio Cues: ${state.audio.muted ? "MUTED" : "ENABLED"}`, "info");
}

// ── CAD Connection Drawer & Credentials ─────────────────────────────────────
function fetchCadStatus() {
  fetch("/api/cad/status")
    .then(res => res.json())
    .then(data => {
      state.cad = { ...state.cad, ...data };
      updateCadUI();
    })
    .catch(err => console.debug("CAD status fetch failed:", err));
}

function updateCadUI() {
  const pill = document.getElementById("cad-status-pill");
  const pillText = document.getElementById("cad-status-text");
  const drawerBadge = document.getElementById("cad-drawer-status-badge");
  const drawerDocId = document.getElementById("cad-drawer-doc-id");
  const drawerKeyStatus = document.getElementById("cad-drawer-key-status");
  const mockBtn = document.getElementById("cad-mode-mock-btn");
  const liveBtn = document.getElementById("cad-mode-live-btn");

  const isLive = (state.cad.mode === "live");
  const isConnected = state.cad.connected;

  if (mockBtn) mockBtn.classList.toggle("active", !isLive);
  if (liveBtn) liveBtn.classList.toggle("active", isLive);

  if (pill) {
    pill.className = `status-badge ${isLive && isConnected ? "cad-badge-live" : "cad-badge-mock"}`;
  }
  if (pillText) {
    pillText.textContent = isLive ? (isConnected ? "CAD CONNECTED" : "CAD DISCONNECTED") : "OFFLINE MOCK";
  }
  if (drawerBadge) {
    if (isLive && isConnected) {
      drawerBadge.style.background = "rgba(16,185,129,0.15)";
      drawerBadge.style.borderColor = "rgba(16,185,129,0.4)";
      drawerBadge.style.color = "var(--accent-green)";
      drawerBadge.textContent = "● CONNECTED (LIVE)";
    } else if (isLive) {
      drawerBadge.style.background = "rgba(239,68,68,0.15)";
      drawerBadge.style.borderColor = "rgba(239,68,68,0.4)";
      drawerBadge.style.color = "var(--accent-red)";
      drawerBadge.textContent = "● DISCONNECTED";
    } else {
      drawerBadge.style.background = "rgba(245,158,11,0.15)";
      drawerBadge.style.borderColor = "rgba(245,158,11,0.4)";
      drawerBadge.style.color = "var(--accent-amber)";
      drawerBadge.textContent = "● OFFLINE MOCK";
    }
  }
  if (drawerDocId) {
    drawerDocId.textContent = state.cad.document_id || "mock-doc-001";
  }
  if (drawerKeyStatus) {
    drawerKeyStatus.textContent = state.cad.access_key_configured ? "Configured" : "Not Configured";
  }
}

function toggleCadDrawer() {
  const drawer = document.getElementById("cad-drawer");
  const backdrop = document.getElementById("drawer-backdrop");
  if (!drawer) return;
  const isOpen = drawer.classList.contains("open");
  if (isOpen) {
    closeAllDrawers();
  } else {
    closeAllDrawers();
    drawer.classList.add("open");
    if (backdrop) backdrop.classList.add("active");
    fetchCadStatus();
    triggerHaptic("generic");
    playAeroCue("click");
  }
}

function switchCadMode(mode) {
  fetch("/api/cad/mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: mode }),
  })
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then(data => {
      state.cad.mode = data.mode;
      state.cad.connected = data.connected;
      updateCadUI();
      triggerHaptic("generic");
      playAeroCue("click");
      showToast(`CAD Mode: ${data.mode.toUpperCase()}`, "info");
    })
    .catch(err => showToast(`Failed to switch CAD mode: ${err.message}`, "error"));
}

function openCadCredentialsModal() {
  const modal = document.getElementById("cad-credentials-modal");
  const docInput = document.getElementById("cad-input-doc-id");
  const errDiv = document.getElementById("cad-credentials-error");
  if (errDiv) errDiv.style.display = "none";
  if (docInput && state.cad.document_id) {
    docInput.value = state.cad.document_id;
  }
  if (modal) {
    modal.style.display = "block";
    modal.classList.add("open");
  }
  const backdrop = document.getElementById("drawer-backdrop");
  if (backdrop) backdrop.classList.add("active");
  triggerHaptic("generic");
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.style.display = "none";
    modal.classList.remove("open");
  }
  const backdrop = document.getElementById("drawer-backdrop");
  const anyOpenDrawer = document.querySelector(".drawer.open");
  if (backdrop && !anyOpenDrawer) {
    backdrop.classList.remove("active");
  }
}

function saveCadCredentials() {
  const accessKey = document.getElementById("cad-input-access-key")?.value || "";
  const secretKey = document.getElementById("cad-input-secret-key")?.value || "";
  const docId = document.getElementById("cad-input-doc-id")?.value || "";
  const errDiv = document.getElementById("cad-credentials-error");

  if (!accessKey.trim() || !secretKey.trim() || !docId.trim()) {
    if (errDiv) {
      errDiv.textContent = "All fields (Access Key, Secret Key, Document ID) are required.";
      errDiv.style.display = "block";
    }
    return;
  }

  fetch("/api/cad/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      access_key: accessKey.trim(),
      secret_key: secretKey.trim(),
      document_id: docId.trim(),
    }),
  })
    .then(res => {
      if (!res.ok) return res.json().then(j => { throw new Error(j.detail || `HTTP ${res.status}`); });
      return res.json();
    })
    .then(data => {
      closeModal("cad-credentials-modal");
      triggerHaptic("alignment");
      triggerSoundCue("complete");
      showToast("Onshape credentials persisted", "success");
      fetchCadStatus();
    })
    .catch(err => {
      if (errDiv) {
        errDiv.textContent = err.message;
        errDiv.style.display = "block";
      }
      showToast(`Credential Error: ${err.message}`, "error");
    });
}

// ── MLX Copilot Drawer & Workflows ──────────────────────────────────────────
function toggleCopilotDrawer() {
  const drawer = document.getElementById("copilot-drawer");
  const backdrop = document.getElementById("drawer-backdrop");
  if (!drawer) return;
  const isOpen = drawer.classList.contains("open");
  if (isOpen) {
    closeAllDrawers();
  } else {
    closeAllDrawers();
    drawer.classList.add("open");
    if (backdrop) backdrop.classList.add("active");
    loadCopilotVram();
    loadCopilotModels();
    triggerHaptic("generic");
    playAeroCue("click");
    setTimeout(() => {
      document.getElementById("copilot-intent")?.focus();
    }, 100);
  }
}

function loadCopilotVram() {
  fetch("/api/copilot/vram")
    .then(res => res.json())
    .then(data => {
      state.copilot.vram = data;
      const txt = document.getElementById("vram-info-text");
      if (txt) {
        const tierStr = data.tier ? data.tier.toUpperCase() : "PRO";
        txt.textContent = `${data.physical_ram_gib.toFixed(1)} GiB RAM (${tierStr}) • ${data.default_quantization} • Ctx: ${data.default_context_length}`;
      }
    })
    .catch(err => console.debug("VRAM load failed:", err));
}

function loadCopilotModels() {
  fetch("/api/copilot/models")
    .then(res => res.json())
    .then(data => {
      const select = document.getElementById("copilot-model-select");
      if (!select) return;
      select.innerHTML = "";
      const models = data.models || data.preset_catalog || [];
      state.copilot.models = models;
      const cached = new Set(data.cached_models || []);

      models.forEach(m => {
        const opt = document.createElement("option");
        opt.value = m.repo_id;
        const isCached = cached.has(m.repo_id);
        opt.textContent = `${m.name || m.repo_id} (${m.size_gib ? m.size_gib + "GB" : m.size || "7B"}${isCached ? " - CACHED" : ""})`;
        if (m.repo_id === data.recommended_repo) {
          opt.selected = true;
        }
        select.appendChild(opt);
      });
      onModelSelectChange();
    })
    .catch(err => console.debug("Models load failed:", err));
}

function onModelSelectChange() {
  const select = document.getElementById("copilot-model-select");
  const badge = document.getElementById("copilot-download-badge");
  const btn = document.getElementById("btn-download-model");
  if (!select) return;
  const selVal = select.value;
  state.copilot.selectedModel = selVal;
  const isCached = select.selectedOptions[0]?.textContent?.includes("CACHED");
  if (badge) badge.style.display = isCached ? "inline-block" : "none";
  if (btn) btn.textContent = isCached ? "✔ Model Cached" : "⬇ Cache Model";
}

function downloadSelectedModel() {
  const select = document.getElementById("copilot-model-select");
  const repoId = select?.value;
  if (!repoId) return;

  const progCont = document.getElementById("copilot-download-progress-container");
  const progBar = document.getElementById("copilot-download-bar");
  const progPct = document.getElementById("copilot-download-percent");
  const progStatus = document.getElementById("copilot-download-status");
  const btn = document.getElementById("btn-download-model");

  if (progCont) progCont.style.display = "block";
  if (btn) btn.disabled = true;

  fetch("/api/copilot/download", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_id: repoId, offline_mock: true }),
  })
    .then(res => res.json())
    .then(data => {
      let pct = 0;
      const interval = setInterval(() => {
        pct += 25;
        if (pct > 100) pct = 100;
        if (progBar) progBar.style.width = `${pct}%`;
        if (progPct) progPct.textContent = `${pct}%`;
        if (progStatus) progStatus.textContent = pct === 100 ? "Complete" : "Downloading...";

        if (pct >= 100) {
          clearInterval(interval);
          if (btn) btn.disabled = false;
          triggerHaptic("levelChange");
          triggerSoundCue("complete");
          showToast(`Model ${repoId} cached successfully!`, "success");
          loadCopilotModels();
        }
      }, 100);
    })
    .catch(err => {
      if (progCont) progCont.style.display = "none";
      if (btn) btn.disabled = false;
      showToast(`Download error: ${err.message}`, "error");
    });
}

function switchCopilotTab(tab) {
  const reviewBtn = document.getElementById("tab-btn-review");
  const goalBtn = document.getElementById("tab-btn-goal");
  const reviewPanel = document.getElementById("panel-copilot-review");
  const goalPanel = document.getElementById("panel-copilot-goal");

  if (tab === "review") {
    if (reviewBtn) reviewBtn.classList.add("active");
    if (goalBtn) goalBtn.classList.remove("active");
    if (reviewPanel) reviewPanel.style.display = "flex";
    if (goalPanel) goalPanel.style.display = "none";
  } else {
    if (reviewBtn) reviewBtn.classList.remove("active");
    if (goalBtn) goalBtn.classList.add("active");
    if (reviewPanel) reviewPanel.style.display = "none";
    if (goalPanel) goalPanel.style.display = "flex";
  }
  playAeroCue("click");
  triggerHaptic("generic");
}

function setCopilotPrompt(text) {
  const ta = document.getElementById("copilot-intent");
  if (ta) {
    ta.value = text;
    ta.focus();
  }
  playAeroCue("click");
}

function renderCopilotDiff(diffData) {
  const out = document.getElementById("copilot-diff-output");
  if (!out) return;
  const mods = diffData.modifications || {};
  const summary = diffData.summary || "Proposed parameter adjustments:";
  const rationale = diffData.rationale || "";

  let tableRows = "";
  for (const [k, v] of Object.entries(mods)) {
    const oldVal = (typeof v.old === 'number') ? v.old.toFixed(2) : v.old;
    const newVal = (typeof v.new === 'number') ? v.new.toFixed(2) : v.new;
    const delta = (typeof v.delta === 'number') ? (v.delta > 0 ? `+${v.delta.toFixed(2)}` : v.delta.toFixed(2)) : "";
    const unit = v.unit || "";
    tableRows += `
      <tr>
        <td style="color:#f1f5f9;font-weight:500;">${k}</td>
        <td class="diff-old">${oldVal} ${unit}</td>
        <td class="diff-new">${newVal} ${unit}</td>
        <td><span class="diff-delta ${v.delta >= 0 ? "diff-delta-positive" : "diff-delta-negative"}">${delta}</span></td>
      </tr>
    `;
  }

  out.innerHTML = `
    <div style="background:rgba(0,0,0,0.3);border:1px solid var(--border-subtle);border-radius:8px;padding:10px;margin-top:10px;display:flex;flex-direction:column;gap:8px;">
      <div style="color:var(--accent-cyan);font-weight:600;font-size:11px;">📋 ${summary}</div>
      ${rationale ? `<div style="color:var(--text-muted);font-size:10px;line-height:1.4;">${rationale}</div>` : ""}
      <table id="copilot-modifications-table" class="diff-table">
        <thead><tr><th>PARAM</th><th>OLD</th><th>NEW</th><th>Δ</th></tr></thead>
        <tbody>${tableRows}</tbody>
      </table>
    </div>
  `;
}

function submitCopilotReview() {
  const intentInput = document.getElementById("copilot-intent");
  const intent = intentInput?.value?.trim();
  if (!intent) {
    showToast("Please enter an engineering goal or click a chip", "warning");
    playAeroCue("warning");
    return;
  }
  const btn = document.getElementById("btn-propose-review");
  if (btn) { btn.disabled = true; btn.textContent = "Analyzing Geometry & Margins..."; }

  const baseRev = state.activeRevId || state.activeRevisionId || 1;
  const currentParams = state.activeRevData?.inputs || {};

  fetch("/api/copilot/review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      intent: intent,
      base_revision_id: baseRev,
      current_params: currentParams,
    }),
  })
    .then(res => {
      if (!res.ok) return res.json().then(j => { throw new Error(j.detail || `HTTP ${res.status}`); });
      return res.json();
    })
    .then(data => {
      if (btn) { btn.disabled = false; btn.textContent = "Propose Design Changes"; }
      state.copilot.proposedModifications = data.modifications;
      renderCopilotDiff(data);
      const applyBtn = document.getElementById("apply-diff-btn");
      if (applyBtn) applyBtn.style.display = "flex";
      triggerHaptic("generic");
      playAeroCue("click");
      showToast("Proposed changes ready for review", "info");
    })
    .catch(err => {
      if (btn) { btn.disabled = false; btn.textContent = "Propose Design Changes"; }
      showToast(`Review error: ${err.message}`, "error");
      triggerSoundCue("alert");
    });
}

function applyProposedDiff() {
  if (!state.copilot.proposedModifications) return;
  const applyBtn = document.getElementById("apply-diff-btn");
  if (applyBtn) { applyBtn.disabled = true; applyBtn.textContent = "⏳ Sizing, Meshing & Simulating..."; }

  const baseRev = state.activeRevId || state.activeRevisionId || 1;

  fetch("/api/copilot/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      base_revision_id: baseRev,
      modifications: state.copilot.proposedModifications,
    }),
  })
    .then(res => {
      if (!res.ok) return res.json().then(j => { throw new Error(j.detail || `HTTP ${res.status}`); });
      return res.json();
    })
    .then(async data => {
      if (applyBtn) { applyBtn.disabled = false; applyBtn.textContent = "✅ Apply to CAD & Re-Simulate"; }
      triggerHaptic("alignment");
      triggerSoundCue("complete");
      const newRevId = data.new_revision_id || data.revision_id;
      showToast(`Revision ${newRevId} created and committed!`, "success");
      await fetchRevisions();
      selectRevision(newRevId);
      closeAllDrawers();
    })
    .catch(err => {
      if (applyBtn) { applyBtn.disabled = false; applyBtn.textContent = "✅ Apply to CAD & Re-Simulate"; }
      showToast(`Apply error: ${err.message}`, "error");
      triggerSoundCue("alert");
    });
}

function startAutonomousOptimization() {
  const apogeeKm = parseFloat(document.getElementById("goal-target-apogee")?.value || "150");
  const maxStress = parseFloat(document.getElementById("goal-target-stress")?.value || "200");
  const minFos = parseFloat(document.getElementById("goal-target-fos")?.value || "1.40");
  const maxIter = parseInt(document.getElementById("goal-max-iterations")?.value || "5", 10);

  const startBtn = document.getElementById("btn-start-optimization");
  const progCont = document.getElementById("goal-progress-container");
  const badge = document.getElementById("goal-status-badge");
  const tbody = document.getElementById("goal-iterations-tbody");
  const sumDiv = document.getElementById("goal-result-summary");

  if (progCont) progCont.style.display = "flex";
  if (badge) { badge.textContent = "OPTIMIZING..."; badge.className = "status-badge"; }
  if (tbody) tbody.innerHTML = "";
  if (sumDiv) sumDiv.textContent = "";
  if (startBtn) { startBtn.disabled = true; startBtn.textContent = "⏳ Running Multi-Physics Loop..."; }

  const baseRev = state.activeRevId || state.activeRevisionId || 1;

  fetch("/api/copilot/optimize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      targets: {
        apogee_m: apogeeKm * 1000.0,
        von_mises_stress_mpa: maxStress,
        yield_fos: minFos,
      },
      max_iterations: maxIter,
      base_revision_id: baseRev,
    }),
  })
    .then(res => {
      if (!res.ok) return res.json().then(j => { throw new Error(j.detail || `HTTP ${res.status}`); });
      return res.json();
    })
    .then(async data => {
      if (startBtn) { startBtn.disabled = false; startBtn.textContent = "🎯 Start Optimization"; }
      const history = data.history || [];
      if (tbody) {
        tbody.innerHTML = history.map((h, i) => `
          <tr>
            <td>#${i + 1}</td>
            <td>${(h.apogee_m ? (h.apogee_m / 1000).toFixed(1) : "-")} km</td>
            <td>${h.von_mises_stress_mpa ? h.von_mises_stress_mpa.toFixed(1) : "-"} MPa</td>
            <td>${h.yield_fos ? h.yield_fos.toFixed(2) : "-"}</td>
          </tr>
        `).join("");
      }

      if (data.status === "converged") {
        if (badge) {
          badge.textContent = `CONVERGED (${data.iterations || data.iterations_run} ITR)`;
          badge.style.background = "rgba(16,185,129,0.2)";
          badge.style.color = "var(--accent-green)";
        }
        if (sumDiv) {
          sumDiv.textContent = `✔ All constraints satisfied! Target Apogee: ${apogeeKm}km, FoS >= ${minFos}. Final Revision: ${data.final_revision_id || data.converged_revision_id || data.revision_id}`;
          sumDiv.style.color = "var(--accent-green)";
        }
        triggerHaptic("levelChange");
        triggerSoundCue("touchdown");
        showToast(`Optimization Converged in ${data.iterations || data.iterations_run} iterations!`, "success");
        const finalRevId = data.final_revision_id || data.converged_revision_id || data.revision_id;
        if (finalRevId) {
          await fetchRevisions();
          selectRevision(finalRevId);
        }
      } else {
        if (badge) {
          badge.textContent = "FAILED CONVERGENCE";
          badge.style.background = "rgba(239,68,68,0.2)";
          badge.style.color = "var(--accent-red)";
        }
        if (sumDiv) {
          sumDiv.textContent = "Reached max iterations before satisfying all margins.";
          sumDiv.style.color = "var(--accent-amber)";
        }
        triggerHaptic("generic");
        triggerSoundCue("alert");
        showToast("Optimization reached limit without full convergence", "warning");
      }
    })
    .catch(err => {
      if (startBtn) { startBtn.disabled = false; startBtn.textContent = "🎯 Start Optimization"; }
      if (badge) { badge.textContent = "ERROR"; badge.style.color = "var(--accent-red)"; }
      showToast(`Optimization error: ${err.message}`, "error");
      triggerSoundCue("alert");
    });
}

// ── Revision Diff Modal ──────────────────────────────────────────────────────
function toggleDiffModal() {
  const modal = document.getElementById("diff-modal");
  const backdrop = document.getElementById("drawer-backdrop");
  if (!modal) return;
  const isHidden = (modal.style.display === "none" || !modal.classList.contains("open"));
  if (!isHidden) {
    closeAllDrawers();
  } else {
    closeAllDrawers();
    renderDiffModalContent();
    modal.style.display = "block";
    modal.classList.add("open");
    if (backdrop) backdrop.classList.add("active");
    triggerHaptic("generic");
    playAeroCue("click");
  }
}

function renderDiffModalContent() {
  const content = document.getElementById("diff-content");
  if (!content) return;
  const rev = state.activeRevData;
  if (!rev) {
    content.innerHTML = "<div style='color:var(--text-muted);'>No active revision loaded.</div>";
    return;
  }
  const revId = rev.revision_id;
  const priorRev = state.revisions.find(r => r.revision_id === revId - 1);
  const diffs = rev.diff_against_predecessor || {};

  let rows = "";
  if (Object.keys(diffs).length > 0) {
    for (const [k, v] of Object.entries(diffs)) {
      const oldVal = (v.old !== undefined) ? v.old : "-";
      const newVal = (v.new !== undefined) ? v.new : "-";
      const delta = (v.delta !== undefined) ? (v.delta > 0 ? `+${v.delta}` : `${v.delta}`) : "";
      rows += `
        <tr>
          <td style="color:#f1f5f9;font-weight:500;">${k}</td>
          <td class="diff-old">${oldVal}</td>
          <td class="diff-new">${newVal}</td>
          <td><span class="diff-delta ${parseFloat(delta) >= 0 ? "diff-delta-positive" : "diff-delta-negative"}">${delta}</span></td>
        </tr>
      `;
    }
  } else if (priorRev && rev.inputs) {
    for (const [k, v] of Object.entries(rev.inputs)) {
      const oldV = priorRev.inputs ? priorRev.inputs[k] : undefined;
      if (oldV !== undefined && oldV !== v) {
        const delta = (typeof v === 'number' && typeof oldV === 'number') ? (v - oldV).toFixed(2) : "";
        rows += `
          <tr>
            <td style="color:#f1f5f9;">${k}</td>
            <td class="diff-old">${oldV}</td>
            <td class="diff-new">${v}</td>
            <td><span class="diff-delta">${delta}</span></td>
          </tr>
        `;
      }
    }
  }

  if (!rows) {
    content.innerHTML = `
      <div style="padding:12px;color:var(--text-muted);text-align:center;">
        ${revId === 1 ? "Baseline design revision (Rev 001) has no predecessor." : "No parametric differences detected from predecessor."}
      </div>
    `;
  } else {
    content.innerHTML = `
      <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;">
        Comparing <span style="color:#00e5ff;font-weight:600;">Rev ${revId}</span> against <span style="color:var(--text-dim);">Rev ${revId - 1}</span>:
      </div>
      <table class="diff-table">
        <thead><tr><th>PARAMETER</th><th>PREVIOUS</th><th>CURRENT</th><th>DELTA</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }
}

function closeAllDrawers() {
  document.querySelectorAll(".drawer.open, .modal.open").forEach(el => {
    el.classList.remove("open");
    if (el.classList.contains("modal")) el.style.display = "none";
  });
  const cadCredModal = document.getElementById("cad-credentials-modal");
  if (cadCredModal) {
    cadCredModal.style.display = "none";
    cadCredModal.classList.remove("open");
  }
  const diffModal = document.getElementById("diff-modal");
  if (diffModal) {
    diffModal.style.display = "none";
    diffModal.classList.remove("open");
  }
  const backdrop = document.getElementById("drawer-backdrop");
  if (backdrop) backdrop.classList.remove("active");
}

function toggleAutoSpin() {
  toggleAutoRotate();
}

function triggerResimulateCurrent() {
  showToast("Re-running sizing & flight simulation...", "info");
  triggerHaptic("alignment");
  playAeroCue("complete");
  fetchRevisions().then(() => {
    if (state.activeRevId) selectRevision(state.activeRevId);
  });
}

function triggerExportBundle() {
  downloadActiveBundle();
}

// ── Global Keyboard Shortcuts ────────────────────────────────────────────────
function initKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    const isMac = navigator.platform.includes('Mac');
    const mod = isMac ? e.metaKey : e.ctrlKey;

    // Native macOS Menu Bar Backdrop Shortcuts: Cmd+Alt+1, 2, 3
    if (mod && e.altKey && e.key === '1') {
      e.preventDefault();
      setBackdropMode('liquid-glass');
      return;
    }
    if (mod && e.altKey && e.key === '2') {
      e.preventDefault();
      setBackdropMode('deep-space');
      return;
    }
    if (mod && e.altKey && e.key === '3') {
      e.preventDefault();
      setBackdropMode('cad-studio');
      return;
    }

    // Camera Focus Presets: Cmd+Alt+0, E, F, N
    if (mod && e.altKey && e.key === '0') {
      e.preventDefault();
      setCameraFocus('full');
      return;
    }
    if (mod && e.altKey && (e.key === 'e' || e.key === 'E')) {
      e.preventDefault();
      setCameraFocus('engines');
      return;
    }
    if (mod && e.altKey && (e.key === 'f' || e.key === 'F')) {
      e.preventDefault();
      setCameraFocus('fins');
      return;
    }
    if (mod && e.altKey && (e.key === 'n' || e.key === 'N')) {
      e.preventDefault();
      setCameraFocus('nose');
      return;
    }

    if (mod && e.key === 'k') {
      e.preventDefault();
      toggleCopilotDrawer();
      return;
    }
    if (mod && e.key === 'r') {
      e.preventDefault();
      triggerResimulateCurrent();
      return;
    }
    if (mod && e.key === 'd') {
      e.preventDefault();
      toggleDiffModal();
      return;
    }
    if (mod && e.key === 'e') {
      e.preventDefault();
      triggerExportBundle();
      return;
    }
    if (e.key === ' ' || e.code === 'Space') {
      const isInput = e.target && (
        e.target.matches('input,textarea') ||
        e.target.matches('select,[contenteditable="true"]') ||
        e.target.isContentEditable
      );
      if (!isInput) {
        e.preventDefault();
        toggleAutoRotate();
      }
      return;
    }
    if (e.key === 'Escape') {
      closeAllDrawers();
    }
  });
}

// ── Toast Notification ───────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const t = document.createElement('div');
  t.style.cssText = `position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:rgba(0,229,255,0.15);backdrop-filter:blur(16px);border:1px solid rgba(0,229,255,0.3);color:#00e5ff;padding:10px 24px;border-radius:24px;font-size:13px;z-index:9999;pointer-events:none;transition:opacity 0.3s`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, 2000);
}
