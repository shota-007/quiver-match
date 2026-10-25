// Quiver Match 3D wave visualizer. Illustrative, not a physics simulation:
// wave height, period and power come from the forecast; shapes are stylized so a few waves fit on screen.
import * as THREE from "three";

const PLANE_W = 70, PLANE_D = 46;
const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;
let renderer, scene, camera, water, foam, boardsGroup, clock, started = false;
let params = { face_ft: 3, period_s: 10, power: 3 };

// ---------------------------------------------------------------- waves
function lambda() { return Math.min(46, Math.max(16, 2.4 * params.period_s)); }   // compressed wavelength (ft)
function waveY(x, z, t) {
  const A = Math.max(0.6, params.face_ft) * 0.7;
  const k = (2 * Math.PI) / lambda();
  const sharp = 1 + 0.35 * params.power;                                  // heavier waves stand up steeper
  const peel = 0.85 + 0.15 * Math.sin(0.12 * z - 0.7 * t);               // crest height peels along the line
  const swell = Math.pow((1 + Math.cos(k * x)) / 2, sharp) * 2 * A * peel;
  const chop = 0.06 * A * Math.sin(1.1 * z - 2.2 * t + 0.6 * x) + 0.04 * A * Math.sin(0.7 * z + 1.6 * t);
  return swell + chop;
}

// ---------------------------------------------------------------- boards (same outline formula as the 2D drawing)
const LONGISH = ["foam longboard", "longboard", "funboard", "mid-length"];
const ROCKER = { "foam longboard": [3.5, 1.8], longboard: [4.2, 2.4], funboard: [4.4, 2.0], "mid-length": [4.0, 1.8], fish: [3.8, 1.6],
                 groveler: [3.9, 1.7], "hybrid shortboard": [4.6, 2.0], "performance shortboard": [5.2, 2.3], "step-up": [5.6, 2.5] };
function halfFn(t) {
  const longish = LONGISH.includes(t);
  const wide = t === "fish" ? 0.42 : longish ? 0.5 : 0.47;
  const tail = { "foam longboard": 0.62, longboard: 0.6, funboard: 0.5, "mid-length": 0.38, fish: 0.6, groveler: 0.5, "step-up": 0.22 }[t] ?? 0.4;
  const nose = longish ? 3.2 : t === "fish" ? 2.2 : 1.7;
  return (u) => {
    if (u <= wide) return tail + (1 - tail) * Math.sin((Math.PI / 2) * (u / wide));
    const v = (u - wide) / (1 - wide);
    return Math.max(0.02, Math.pow(Math.max(0, 1 - Math.pow(v, nose)), 0.6));
  };
}
function rocker(t, u) {
  const [nr, tr] = ROCKER[t] || [4.4, 2.0];
  return u < 0.4 ? tr * Math.pow((0.4 - u) / 0.4, 2) : u > 0.6 ? nr * Math.pow((u - 0.6) / 0.4, 2.2) : 0;
}
function labelSprite(text) {
  const c = document.createElement("canvas"); c.width = 512; c.height = 96;
  const g = c.getContext("2d");
  g.fillStyle = "rgba(255,250,240,0.92)"; g.beginPath(); g.roundRect(4, 14, 504, 68, 34); g.fill();
  g.fillStyle = "#5a2e14"; g.font = "bold 34px Avenir Next, Helvetica, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(text, 256, 50);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), depthTest: false }));
  s.scale.set(4.6, 0.86, 1);
  return s;
}
function boardMesh(b, color) {
  const L = b.length_in / 12, W = b.width_in / 12, T = b.thickness_in / 12, half = halfFn(b.board_type);
  const shape = new THREE.Shape(), n = 48;
  for (let i = 0; i <= n; i++) { const u = i / n; const p = [u * L - L / 2, (half(u) * W) / 2]; i ? shape.lineTo(...p) : shape.moveTo(...p); }
  for (let i = n; i >= 0; i--) { const u = i / n; shape.lineTo(u * L - L / 2, (-half(u) * W) / 2); }
  const geo = new THREE.ExtrudeGeometry(shape, { depth: T * 0.7, bevelEnabled: true, bevelThickness: T * 0.15, bevelSize: Math.min(W * 0.07, 0.07), bevelSegments: 3, curveSegments: 4 });
  geo.translate(0, 0, -T * 0.35);
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) pos.setZ(i, pos.getZ(i) + rocker(b.board_type, (pos.getX(i) + L / 2) / L) / 12);
  geo.computeVertexNormals();
  geo.rotateX(-Math.PI / 2);   // thickness -> up
  geo.rotateY(Math.PI / 2);    // length -> along the wave (down the line)
  const group = new THREE.Group();
  group.add(new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color, roughness: 0.35, metalness: 0.05 })));
  if (b.board_type !== "foam longboard") {
    const s = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.02, L * 0.94), new THREE.MeshStandardMaterial({ color: 0xb48a5a }));
    s.position.y = T * 0.36; group.add(s);
  }
  const fin = new THREE.Mesh(new THREE.ConeGeometry(0.22, 0.55, 3), new THREE.MeshStandardMaterial({ color: 0x5a2e14 }));
  fin.rotation.x = Math.PI; fin.position.set(0, -T * 0.5, L / 2 - 0.5); group.add(fin);
  const label = labelSprite(b.label || b.name || b.board_type);
  label.position.set(0, 2.1, 0); group.add(label);
  return group;
}

// ---------------------------------------------------------------- scene
function build(container) {
  renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0xffd6a0);
  scene.fog = new THREE.Fog(0xffd6a0, 45, 120);
  camera = new THREE.PerspectiveCamera(42, 2, 0.1, 400);
  camera.position.set(17, 7.5, 15);
  camera.lookAt(2, 1.8, -1);
  scene.add(new THREE.HemisphereLight(0xffe2ad, 0x0b4f5c, 1.1));
  const sun = new THREE.DirectionalLight(0xfff1d0, 1.6); sun.position.set(-40, 50, -30); scene.add(sun);
  const disc = new THREE.Mesh(new THREE.SphereGeometry(7, 24, 16), new THREE.MeshBasicMaterial({ color: 0xfff1b8 }));
  disc.position.set(-70, 32, -90); scene.add(disc);
  const geo = new THREE.PlaneGeometry(PLANE_W, PLANE_D, 140, 92); geo.rotateX(-Math.PI / 2);
  water = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: 0x17a2a8, roughness: 0.28, metalness: 0.08, flatShading: true }));
  scene.add(water);
  const fgeo = new THREE.BufferGeometry(); fgeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(3 * 600), 3));
  foam = new THREE.Points(fgeo, new THREE.PointsMaterial({ color: 0xffffff, size: 0.32, transparent: true, opacity: 0.85 }));
  scene.add(foam);
  boardsGroup = new THREE.Group(); scene.add(boardsGroup);
  clock = new THREE.Clock();
  new ResizeObserver(() => resize()).observe(container);
}
function resize() {
  const el = renderer.domElement.parentElement; if (!el) return;
  const w = el.clientWidth, h = el.clientHeight || 340;
  renderer.setSize(w, h, false); renderer.domElement.style.width = "100%"; renderer.domElement.style.height = h + "px";
  camera.aspect = w / h; camera.updateProjectionMatrix();
}
function frame() {
  const t = REDUCE ? 0 : clock.getElapsedTime();
  const pos = water.geometry.attributes.position;
  for (let i = 0; i < pos.count; i++) pos.setY(i, waveY(pos.getX(i), pos.getZ(i), t));
  pos.needsUpdate = true; water.geometry.computeVertexNormals();
  const lam = lambda(), fp = foam.geometry.attributes.position;
  for (let i = 0; i < 600; i++) {
    const crest = ((i % 3) - 1) * lam, z = -PLANE_D / 2 + ((i * 7.31) % PLANE_D), x = crest + Math.sin(i * 12.9 + t * 1.7) * 0.9;
    fp.setXYZ(i, x, waveY(x, z, t) + 0.15, z);
  }
  fp.needsUpdate = true;
  const xb = lam * 0.17;                                                  // boards sit on the steep part of the face
  boardsGroup.children.forEach((g, i) => {
    const z = g.userData.z + Math.sin(0.5 * t + i) * 1.2;
    const y = waveY(xb, z, t), dx = (waveY(xb + 0.3, z, t) - waveY(xb - 0.3, z, t)) / 0.6;
    g.position.set(xb, y + 0.18, z);
    g.rotation.set(0, 0, 0); g.rotateZ(Math.atan(dx) * 0.9); g.rotateY(Math.sin(0.4 * t + i) * 0.08);
  });
  renderer.render(scene, camera);
  if (!REDUCE) requestAnimationFrame(frame);
}

window.QMViz = {
  mount(container) {
    if (!renderer) build(container);
    container.prepend(renderer.domElement);
    resize();
    if (!started) { started = true; frame(); }
  },
  update({ face_ft, period_s, power, boards, color }) {
    params = { face_ft: face_ft || 2, period_s: period_s || 10, power: power || 3 };
    if (!boardsGroup) return;
    boardsGroup.clear();
    const gap = 10, start = -((boards.length - 1) * gap) / 2;
    boards.forEach((b, i) => {
      const g = boardMesh(b, new THREE.Color(color ? color[1] : "#fffaf0"));
      g.userData.z = start + i * gap; boardsGroup.add(g);
    });
    if (REDUCE) frame();
  },
};
