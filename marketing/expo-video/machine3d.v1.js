// Procedural 3D model of the sCure Box + camera work, drawn with three.js r147 (classic build).
// API:  M3D.init(canvas)   M3D.render(state)   state = {T, uv, bl, heat, n2, door, xray, dmp, aW, aC, cure, fan, mode, modeCol, temp, ledCol}
(function () {
  const W = 0.72, D = 0.80;           // body width / depth (m)
  const Y0 = 0.24, Y1 = 1.20;         // chamber floor / ceiling
  const IX = W / 2 - 0.03, IZ = D / 2 - 0.03;
  let R, scene, cam, comp, bloom, M = {}, G = {}, screenCtx, screenTex, parts = {};

  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, t) => a + (b - a) * t;
  const col = (h) => new THREE.Color(h);

  function canvasTex(w, h, draw, repeat) {
    const c = document.createElement('canvas'); c.width = w; c.height = h;
    draw(c.getContext('2d'), w, h);
    const t = new THREE.CanvasTexture(c); t.anisotropy = 8;
    if (repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; }
    return t;
  }
  function radialTex(stops) {
    return canvasTex(256, 256, (g, w, h) => {
      const r = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
      stops.forEach(([o, c]) => r.addColorStop(o, c)); g.fillStyle = r; g.fillRect(0, 0, w, h);
    });
  }
  // Stratasys wordmark + mark drawn in code (replace with shots/stratasys-logo.png when available)
  function drawMark(g, x, y, k, color) {
    g.save(); g.translate(x, y); g.scale(k, k); g.strokeStyle = color; g.lineWidth = 9; g.lineJoin = 'miter';
    g.beginPath(); g.moveTo(0, -60); g.lineTo(60, 0); g.lineTo(0, 60); g.lineTo(-60, 0); g.closePath(); g.stroke();
    g.beginPath(); g.moveTo(0, -60); g.lineTo(0, 0); g.moveTo(-60, 0); g.lineTo(60, 0); g.stroke();
    g.beginPath(); g.moveTo(-60, 0); g.lineTo(0, 55); g.lineTo(60, 0); g.stroke();
    g.restore();
  }
  function box(w, h, d, mat, x, y, z, parent) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat); m.position.set(x, y, z);
    (parent || G.machine).add(m); return m;
  }

  function buildEnv() {
    const s = new THREE.Scene();
    const room = new THREE.Mesh(new THREE.BoxGeometry(20, 12, 20), new THREE.MeshBasicMaterial({ color: 0x1b2036, side: THREE.BackSide }));
    room.position.y = 5; s.add(room);
    const soft = (w, h, x, y, z, ry, k) => {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(k, k, k * 1.05), side: THREE.DoubleSide }));
      m.position.set(x, y, z); m.rotation.y = ry; s.add(m);
    };
    soft(8, 5, 0, 5, 9, Math.PI, 5);       // key light
    soft(5, 8, -9, 4, 2, Math.PI / 2, 3);  // left strip
    soft(6, 4, 8, 6, -4, -Math.PI / 2, 2.2);
    soft(10, 10, 0, 11, 0, 0, 1.6); s.children[s.children.length - 1].rotation.x = Math.PI / 2;
    const pm = new THREE.PMREMGenerator(R);
    const rt = pm.fromScene(s, 0.02); pm.dispose();
    return rt.texture;
  }

  function init(canvas) {
    R = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
    R.setPixelRatio(1); R.setSize(1920, 1080, false);
    scene = new THREE.Scene();
    scene.background = canvasTex(16, 512, (g, w, h) => { const l = g.createLinearGradient(0, 0, 0, h); l.addColorStop(0, '#0b1020'); l.addColorStop(1, '#04060c'); g.fillStyle = l; g.fillRect(0, 0, w, h); });
    cam = new THREE.PerspectiveCamera(32, 16 / 9, 0.05, 60);
    const env = buildEnv(); scene.environment = env; scene.fog = new THREE.Fog(0x070a14, 5, 12);

    G.machine = new THREE.Group(); scene.add(G.machine);

    // ---------- materials
    M.silver = new THREE.MeshStandardMaterial({ color: 0xe2e5ea, metalness: 0.85, roughness: 0.36, envMapIntensity: 1.9 });
    M.dark = new THREE.MeshStandardMaterial({ color: 0x15171b, metalness: 0.35, roughness: 0.42, envMapIntensity: 0.9 });
    M.base = new THREE.MeshStandardMaterial({ color: 0xa6a9ae, metalness: 0.6, roughness: 0.5, envMapIntensity: 1.5 });
    M.inner = new THREE.MeshStandardMaterial({ color: 0x9aa7b5, metalness: 0.75, roughness: 0.55 });
    M.led = new THREE.MeshBasicMaterial({ color: 0x39d0ff });
    M.doorFront = M.silver.clone(); M.doorFront.transparent = true;
    M.doorEdge = M.silver.clone(); M.doorEdge.transparent = true;
    M.glass = new THREE.MeshBasicMaterial({ color: 0x7fb4ff, transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide });

    const dots = canvasTex(512, 512, (g, w, h) => {
      g.fillStyle = '#000'; g.fillRect(0, 0, w, h); g.fillStyle = '#fff';
      for (let i = 0; i < 12; i++) for (let j = 0; j < 12; j++) { g.beginPath(); g.arc(21 + i * 43 + (j % 2) * 10, 21 + j * 43, 6.5, 0, 7); g.fill(); }
    });
    const mkPanel = () => new THREE.MeshStandardMaterial({ color: 0x9a9da3, roughness: 0.95, metalness: 0, emissive: 0x000000, emissiveMap: dots, emissiveIntensity: 0 });
    M.pDoor = mkPanel(); M.pBack = mkPanel(); M.pL = mkPanel(); M.pR = mkPanel();

    // ---------- base + LED ring
    const labelTex = canvasTex(512, 128, (g, w, h) => { g.fillStyle = '#8e9196'; g.fillRect(0, 0, w, h); g.fillStyle = '#e8eaee'; g.font = '600 64px Segoe UI, Arial'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText('sCure', w / 2 - 14, h / 2 + 2); g.font = '600 22px Segoe UI, Arial'; g.fillText('TM', w / 2 + 84, h / 2 - 18); });
    const baseMats = [M.base, M.base, M.base, M.base, new THREE.MeshStandardMaterial({ map: labelTex, metalness: 0.5, roughness: 0.5 }), M.base];
    box(W - 0.02, 0.22, D - 0.02, baseMats, 0, 0.11, 0);
    M.ring = box(W + 0.004, 0.018, D + 0.004, M.led, 0, 0.23, 0);

    // ---------- body panels (front open, door closes it)
    const decal = canvasTex(512, 1024, (g, w, h) => {
      const l = g.createLinearGradient(0, 0, w, 0); l.addColorStop(0, '#9da0a6'); l.addColorStop(1, '#c9ccd1'); g.fillStyle = l; g.fillRect(0, 0, w, h);
      g.fillStyle = '#16181c'; g.beginPath(); g.moveTo(40, 240); g.lineTo(300, 40); g.lineTo(300, 984); g.lineTo(40, 984); g.closePath(); g.fill();
      g.save(); g.translate(172, 640); g.rotate(-Math.PI / 2); g.fillStyle = '#f2f3f5'; g.font = '800 150px Segoe UI, Arial'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText('stratasys', 0, 0); g.restore();
      drawMark(g, 172, 150, 0.7, '#f2f3f5');
    });
    const sideMats = (leftOuter) => [M.silver, leftOuter ? new THREE.MeshStandardMaterial({ map: decal, metalness: 0.6, roughness: 0.4 }) : M.silver, M.silver, M.silver, M.silver, M.silver];
    const bh = Y1 - Y0, bc = (Y0 + Y1) / 2;
    box(0.03, bh, D, sideMats(true), -W / 2 + 0.015, bc, 0);
    box(0.03, bh, D, M.silver, W / 2 - 0.015, bc, 0);
    box(W, bh, 0.03, M.silver, 0, bc, -D / 2 + 0.015);
    box(W - 0.06, 0.03, D - 0.06, M.inner, 0, Y0 + 0.015, 0);
    box(W - 0.02, 0.03, D - 0.02, M.silver, 0, Y1 - 0.015, 0);
    // head (black) with screen
    box(W + 0.03, 0.38, D + 0.03, M.dark, 0, Y1 + 0.19, 0);
    box(0.34, 0.22, 0.01, new THREE.MeshStandardMaterial({ color: 0x050607, metalness: 0.8, roughness: 0.2 }), 0.12, 1.39, (D + 0.03) / 2 + 0.004);
    const sc = document.createElement('canvas'); sc.width = 640; sc.height = 384; screenCtx = sc.getContext('2d');
    screenTex = new THREE.CanvasTexture(sc); screenTex.anisotropy = 8;
    const screen = new THREE.Mesh(new THREE.PlaneGeometry(0.31, 0.186), new THREE.MeshBasicMaterial({ map: screenTex }));
    screen.position.set(0.12, 1.39, (D + 0.03) / 2 + 0.0105); G.machine.add(screen);

    // ---------- interior LED panels
    const pDoorGeo = new THREE.PlaneGeometry(W - 0.12, bh - 0.1);
    const pw_ = new THREE.PlaneGeometry(D - 0.12, bh - 0.1), pb_ = new THREE.PlaneGeometry(W - 0.12, bh - 0.1);
    const back = new THREE.Mesh(pb_, M.pBack); back.position.set(0, bc, -IZ + 0.002); G.machine.add(back);
    const left = new THREE.Mesh(pw_, M.pL); left.rotation.y = Math.PI / 2; left.position.set(-IX + 0.002, bc, 0); G.machine.add(left);
    const right = new THREE.Mesh(pw_, M.pR); right.rotation.y = -Math.PI / 2; right.position.set(IX - 0.002, bc, 0); G.machine.add(right);

    // ---------- door (hinged on the left, swings out toward the viewer)
    G.door = new THREE.Group(); G.door.position.set(-W / 2 + 0.01, bc, D / 2 - 0.005); G.machine.add(G.door);
    const dw = W - 0.02, dh = bh;
    const doorTex = canvasTex(512, 1024, (g, w, h) => {
      const l = g.createLinearGradient(0, 0, w, 0); l.addColorStop(0, '#9fa3a9'); l.addColorStop(0.5, '#d4d6da'); l.addColorStop(1, '#a8abb0'); g.fillStyle = l; g.fillRect(0, 0, w, h);
      drawMark(g, 70, 88, 0.3, '#f4f5f7'); g.fillStyle = '#f4f5f7'; g.font = '700 34px Segoe UI, Arial'; g.textBaseline = 'middle'; g.fillText('stratasys', 100, 90);
    });
    M.doorFront = new THREE.MeshStandardMaterial({ map: doorTex, color: 0xffffff, metalness: 0.8, roughness: 0.32, transparent: true });
    const frontMats = [M.doorEdge, M.doorEdge, M.doorEdge, M.doorEdge, M.doorFront, M.doorEdge];
    const doorBody = new THREE.Mesh(new THREE.BoxGeometry(dw, dh, 0.035), frontMats); doorBody.position.set(dw / 2, 0, 0.0175); G.door.add(doorBody);
    const inner = new THREE.Mesh(pDoorGeo, M.pDoor); inner.rotation.y = Math.PI; inner.position.set(dw / 2, 0, -0.0015); G.door.add(inner);
    const handle = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.3, 0.02), M.dark); handle.position.set(dw - 0.04, 0, 0.045); G.door.add(handle);
    const glass = new THREE.Mesh(new THREE.PlaneGeometry(dw, dh), M.glass); glass.position.set(dw / 2, 0, 0.037); G.door.add(glass); G.glass = glass;

    // ---------- shelf + parts
    const rod = new THREE.MeshStandardMaterial({ color: 0xd0d3d8, metalness: 0.9, roughness: 0.25 });
    for (const z of [-0.2, 0.2]) { const r = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, W - 0.1, 12), rod); r.rotation.z = Math.PI / 2; r.position.set(0, 0.6, z); G.machine.add(r); }
    box(W - 0.1, 0.008, 0.46, rod, 0, 0.598, 0);
    // gear part
    const sh = new THREE.Shape(), n = 14, ro = 0.16, ri = 0.125;
    for (let i = 0; i < n * 2; i++) { const a = (i / (n * 2)) * Math.PI * 2, r = i % 2 ? ri : ro; const a2 = a + 0.06; const x1 = Math.cos(a) * r, y1 = Math.sin(a) * r; if (i === 0) sh.moveTo(x1, y1); else sh.lineTo(x1, y1); sh.lineTo(Math.cos(a2) * r, Math.sin(a2) * r); }
    const hole = new THREE.Path(); hole.absarc(0, 0, 0.05, 0, Math.PI * 2, true); sh.holes.push(hole);
    M.part = new THREE.MeshStandardMaterial({ color: 0x7684ad, metalness: 0.1, roughness: 0.45, emissive: 0x000000 });
    parts.gear = new THREE.Mesh(new THREE.ExtrudeGeometry(sh, { depth: 0.05, bevelEnabled: true, bevelSize: 0.004, bevelThickness: 0.004, bevelSegments: 2 }), M.part);
    parts.gear.rotation.x = -Math.PI / 2; parts.gear.position.set(-0.09, 0.604, 0); G.machine.add(parts.gear);
    parts.knot = new THREE.Mesh(new THREE.TorusKnotGeometry(0.06, 0.02, 120, 14), M.part); parts.knot.position.set(0.18, 0.68, 0.02); G.machine.add(parts.knot);

    // ---------- heater coil + fan + damper + valve
    const pts = []; for (let i = 0; i <= 18; i++) pts.push(new THREE.Vector3(-0.28 + i * 0.031, Y0 + 0.05, (i % 2 ? 0.12 : -0.12)));
    M.coil = new THREE.MeshStandardMaterial({ color: 0x4a3b36, emissive: 0xff6a1f, emissiveIntensity: 0, metalness: 0.4, roughness: 0.5 });
    G.machine.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts, false, 'catmullrom', 0.1), 200, 0.009, 8), M.coil));
    G.fan = new THREE.Group(); G.fan.position.set(-0.2, 0.42, -IZ + 0.05); G.machine.add(G.fan);
    G.fan.add(new THREE.Mesh(new THREE.CylinderGeometry(0.085, 0.085, 0.02, 24), new THREE.MeshStandardMaterial({ color: 0x1b1f2a, metalness: 0.5, roughness: 0.5 })));
    G.fan.children[0].rotation.x = Math.PI / 2;
    G.blades = new THREE.Group(); G.blades.position.z = 0.014; G.fan.add(G.blades);
    for (let i = 0; i < 5; i++) { const b = new THREE.Mesh(new THREE.BoxGeometry(0.075, 0.03, 0.004), new THREE.MeshStandardMaterial({ color: 0x9aa7c8, metalness: 0.4, roughness: 0.4 })); b.position.x = 0.04; b.rotation.z = 0.35; const gp = new THREE.Group(); gp.rotation.z = i * Math.PI * 2 / 5; gp.add(b); G.blades.add(gp); }
    box(0.2, 0.012, 0.16, M.dark, 0.17, Y1 - 0.036, -0.1);
    G.flapPivot = new THREE.Group(); G.flapPivot.position.set(0.17, Y1 - 0.045, -0.18); G.machine.add(G.flapPivot);
    const flap = new THREE.Mesh(new THREE.BoxGeometry(0.19, 0.006, 0.14), M.silver); flap.position.z = 0.07; G.flapPivot.add(flap);
    const valve = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.022, 0.06, 16), new THREE.MeshStandardMaterial({ color: 0x3aa0d8, metalness: 0.5, roughness: 0.3, emissive: 0x0a3a5a })); valve.position.set(0.28, Y0 + 0.06, -0.3); G.machine.add(valve);

    // ---------- particles
    const mkPts = (N, size) => {
      const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(N * 3), 3)); g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(N * 3), 3));
      const p = new THREE.Points(g, new THREE.PointsMaterial({ size, vertexColors: true, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true, map: radialTex([[0, '#fff'], [0.4, 'rgba(255,255,255,.6)'], [1, 'rgba(255,255,255,0)']]) }));
      p.frustumCulled = false; G.machine.add(p); return p;
    };
    let s = 11; const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
    parts.n2 = mkPts(160, 0.03); parts.n2.seed = Array.from({ length: 160 }, () => ({ sp: 0.1 + rnd() * 0.18, ph: rnd(), dx: (rnd() - 0.5) * 0.5, dz: (rnd() - 0.2) * 0.5 }));
    parts.air = mkPts(110, 0.026); parts.air.seed = Array.from({ length: 110 }, () => ({ ph: rnd(), jx: (rnd() - 0.5) * 0.08, jy: (rnd() - 0.5) * 0.08, jz: (rnd() - 0.5) * 0.08 }));
    G.airCurve = new THREE.CatmullRomCurve3([new THREE.Vector3(-0.28, 0.34, 0.12), new THREE.Vector3(-0.3, 0.62, 0.0), new THREE.Vector3(-0.05, 0.98, -0.1), new THREE.Vector3(0.17, 1.15, -0.12)]);

    // ---------- lights
    scene.add(new THREE.HemisphereLight(0xaab8ff, 0x20242e, 0.18));
    const key = new THREE.DirectionalLight(0xffffff, 1.1); key.position.set(2.5, 4, 4); scene.add(key);
    const rim = new THREE.DirectionalLight(0x8fb0ff, 0.9); rim.position.set(-4, 2, -3); scene.add(rim);
    G.pl = new THREE.PointLight(0xa66bff, 0, 2.2, 1.6); G.pl.position.set(0, 0.72, 0); scene.add(G.pl);
    G.plHeat = new THREE.PointLight(0xff7a33, 0, 1.4, 1.8); G.plHeat.position.set(0, 0.34, 0.05); scene.add(G.plHeat);
    G.plRing = new THREE.PointLight(0x39d0ff, 0, 2.2, 2); G.plRing.position.set(0, 0.3, 0.6); scene.add(G.plRing);

    // ---------- ground
    const floor = new THREE.Mesh(new THREE.CircleGeometry(6, 64), new THREE.MeshStandardMaterial({ color: 0x0b0f19, metalness: 0.15, roughness: 0.8 }));
    floor.rotation.x = -Math.PI / 2; scene.add(floor);
    const shadow = new THREE.Mesh(new THREE.PlaneGeometry(2.2, 2.2), new THREE.MeshBasicMaterial({ map: radialTex([[0, 'rgba(0,0,0,.85)'], [0.55, 'rgba(0,0,0,.45)'], [1, 'rgba(0,0,0,0)']]), transparent: true, depthWrite: false }));
    shadow.rotation.x = -Math.PI / 2; shadow.position.y = 0.002; scene.add(shadow);
    M.glow = new THREE.MeshBasicMaterial({ map: radialTex([[0, 'rgba(255,255,255,.55)'], [0.3, 'rgba(255,255,255,.16)'], [1, 'rgba(255,255,255,0)']]), color: 0x39d0ff, opacity: 0.55, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false });
    const glow = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 3.4), M.glow); glow.rotation.x = -Math.PI / 2; glow.position.y = 0.006; scene.add(glow);

    // ---------- post: bloom
    comp = new THREE.EffectComposer(R);
    comp.setSize(1920, 1080);
    comp.addPass(new THREE.RenderPass(scene, cam));
    bloom = new THREE.UnrealBloomPass(new THREE.Vector2(960, 540), 0.4, 0.5, 0.92);
    comp.addPass(bloom);
  }

  // ---------- camera keyframes (real seconds)
  const KF = {
    az:    [[0, 24], [4, 50], [4.6, 26], [9, 8], [29.8, -34], [30.5, -26], [48, 24], [53.4, 28], [54, 42], [60, 66]],
    r:     [[0, 3.9], [4, 3.5], [4.6, 3.4], [9, 2.5], [29.8, 4.0], [30.5, 3.9], [47.8, 3.7], [48.6, 4.1], [53.4, 3.9], [54, 3.9], [60, 3.6]],
    h:     [[0, 1.3], [4, 1.2], [4.6, 1.05], [9, 0.95], [30, 1.15], [48, 1.0], [53.4, 1.25], [60, 1.3]],
    ty:    [[0, 0.8], [4.6, 0.78], [9, 0.74], [30, 0.84], [48, 0.84], [53.4, 0.8], [60, 0.8]],
    shift: [[0, -430], [3.8, -430], [4.8, 400], [29.8, 400], [30.4, 360], [53.2, 360], [54, -430], [60, -430]],
    fov:   [[0, 31], [60, 31]],
  };
  const P = (T, k) => pw(T, k);

  function drawScreen(st) {
    const g = screenCtx, w = 640, h = 384;
    g.fillStyle = '#0b0b0d'; g.fillRect(0, 0, w, h);
    g.fillStyle = '#1b1c1f'; g.fillRect(0, 0, w, 64);
    g.fillStyle = '#e9ecf5'; g.font = '700 30px Segoe UI, Arial'; g.textBaseline = 'middle'; g.fillText('sCure', 56, 32);
    g.strokeStyle = '#e9ecf5'; g.lineWidth = 3; g.beginPath(); g.moveTo(24, 20); g.lineTo(38, 32); g.lineTo(24, 44); g.lineTo(10, 32); g.closePath(); g.stroke();
    g.fillStyle = '#fff'; g.font = '700 28px Segoe UI, Arial'; g.textAlign = 'right'; g.fillText(Math.round(st.temp) + '.0°C', w - 24, 32); g.textAlign = 'left';
    g.fillStyle = '#141416'; g.fillRect(16, 80, w - 32, 70);
    g.fillStyle = st.modeCol; g.beginPath(); g.arc(46, 115, 12, 0, 7); g.fill();
    g.fillStyle = '#fff'; g.font = '600 30px Segoe UI, Arial'; g.fillText(st.mode, 76, 116);
    // step cards
    const names = ['Drying', 'Heating', 'Cure', 'Cooling'];
    for (let i = 0; i < 4; i++) {
      const x = 16 + i * 154; g.fillStyle = '#121214'; g.fillRect(x, 168, 146, 200);
      g.strokeStyle = i === st.step ? '#3b82f6' : '#26272b'; g.lineWidth = 3; g.strokeRect(x + 1.5, 169.5, 143, 197);
      g.fillStyle = '#9aa3b8'; g.font = '600 20px Segoe UI, Arial'; g.textAlign = 'center'; g.fillText(names[i], x + 73, 194);
      g.strokeStyle = '#25262b'; g.lineWidth = 8; g.beginPath(); g.arc(x + 73, 275, 44, 0, 7); g.stroke();
      g.strokeStyle = i === st.step ? '#3b82f6' : '#3a3b40'; g.beginPath(); g.arc(x + 73, 275, 44, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * (i === st.step ? st.prog : 0.02)); g.stroke();
      g.textAlign = 'left';
    }
    screenTex.needsUpdate = true;
  }

  function render(s) {
    const T = s.T;
    // camera
    const az = P(T, KF.az) * Math.PI / 180, r = P(T, KF.r), hh = P(T, KF.h), ty = P(T, KF.ty);
    const bob = Math.sin(T * 0.5) * 0.04;
    cam.position.set(Math.sin(az) * r, hh + bob, Math.cos(az) * r); cam.fov = P(T, KF.fov);
    cam.lookAt(0, ty, 0);
    cam.setViewOffset(1920, 1080, P(T, KF.shift), 0, 1920, 1080); cam.updateProjectionMatrix();

    // door + x-ray
    G.door.rotation.y = -s.door * 1.95;
    const xr = s.xray;
    M.doorFront.opacity = lerp(1, 0.1, xr); M.doorEdge.opacity = lerp(1, 0.18, xr);
    M.glass.opacity = xr * 0.07;
    M.doorFront.depthWrite = xr < 0.5;

    // LED panels
    const lit = Math.max(s.uv, s.bl);
    const c405 = col(0xa66bff), c450 = col(0x4aa3ff);
    const cc = s.bl > s.uv ? c450 : c405;
    for (const k of ['pBack', 'pL', 'pDoor', 'pR']) {
      const doorOnly = s.bl > s.uv && k !== 'pDoor';
      const k_ = doorOnly ? 0 : lit;
      M[k].emissive.copy(cc); M[k].emissiveIntensity = k_ * 2.6;
      M[k].color.setRGB(lerp(0.42, 0.35, k_), lerp(0.43, 0.28, k_), lerp(0.45, 0.7, k_));
    }
    G.pl.color.copy(cc); G.pl.intensity = lit * 0.9;
    G.plHeat.intensity = s.heat * 1.6;
    M.coil.emissiveIntensity = s.heat * 2.6; M.coil.color.setRGB(lerp(0.29, 1, s.heat), lerp(0.23, 0.45, s.heat), lerp(0.21, 0.2, s.heat));

    // base ring
    const ringC = col(s.ledCol); M.led.color.copy(ringC).multiplyScalar(1.25);
    M.glow.color.copy(ringC); G.plRing.color.copy(ringC);

    // parts
    M.part.color.setRGB(lerp(0.30, 0.62, s.cure), lerp(0.36, 0.58, s.cure), lerp(0.55, 0.78, s.cure));
    M.part.emissive.copy(cc).multiplyScalar(0.12 * lit);
    parts.gear.rotation.z = T * 0.5; parts.knot.rotation.set(T * 0.4, T * 0.7, 0);

    // fan, damper
    G.blades.rotation.z = -s.fan * Math.PI / 180;
    G.flapPivot.rotation.x = -s.dmp * 1.15;

    // nitrogen
    const n2 = parts.n2, na = n2.geometry.attributes.position, nc = n2.geometry.attributes.color;
    n2.seed.forEach((p, i) => { const u = (T * p.sp + p.ph) % 1, f = Math.sin(u * Math.PI) * s.n2;
      na.setXYZ(i, 0.28 - p.dx * u * 0.9, Y0 + 0.08 + u * 0.8, -0.3 + p.dz * u * 0.9); nc.setXYZ(i, 0.3 * f, 0.85 * f, 1.0 * f); });
    na.needsUpdate = nc.needsUpdate = true;
    // air
    const ar = parts.air, aa = ar.geometry.attributes.position, ac = ar.geometry.attributes.color, a = Math.max(s.aW, s.aC);
    const cw = s.aC > s.aW ? [0.3, 0.8, 1.0] : [1.0, 0.62, 0.28];
    ar.seed.forEach((p, i) => { const u = (T * 0.22 + p.ph) % 1, pt = G.airCurve.getPoint(u), f = Math.sin(u * Math.PI) * a;
      aa.setXYZ(i, pt.x + p.jx, pt.y + p.jy, pt.z + p.jz); ac.setXYZ(i, cw[0] * f, cw[1] * f, cw[2] * f); });
    aa.needsUpdate = ac.needsUpdate = true;

    drawScreen(s);
    bloom.strength = 0.35 + lit * 0.3 + s.heat * 0.08;
    comp.render();
  }

  window.M3D = { init, render };
})();
