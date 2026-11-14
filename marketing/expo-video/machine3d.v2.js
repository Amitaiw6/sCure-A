// Procedural 3D model of the sCure Box (proportions from the reference sheet: 410 x 461 x 665 mm,
// chamber 293 x 174 x 410 mm) + camera work, drawn with three.js r147 (classic build).
// API:  M3D.init(canvas, {imgKey: HTMLImageElement})   M3D.render(state)
(function () {
  const K = 1.58 / 665;                       // mm -> world units (machine is 1.58 tall)
  const mm = v => v * K;
  const W = mm(410), D = mm(461);
  const BASE0 = mm(10), BASE1 = mm(90), STRIP1 = mm(98), BODY1 = mm(555), TOP = mm(665);
  const CX = mm(293 / 2), CY0 = mm(115), CY1 = mm(525);   // chamber half-width, floor, ceiling
  const ZF = D / 2 - mm(30), ZB = ZF - mm(174);              // chamber front opening / back wall
  const PLATE = mm(415);                                     // perforated plate under the top compartment
  const SCR = { x: 0, y: mm(610), z: D / 2 + mm(3) + 0.004, w: mm(170), h: mm(102) };

  let R, scene, cam, comp, bloom, M = {}, G = {}, sctx, stex, imgs = {}, parts = {};
  const lerp = (a, b, t) => a + (b - a) * t;
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));

  function canvasTex(w, h, draw) {
    const c = document.createElement('canvas'); c.width = w; c.height = h; draw(c.getContext('2d'), w, h);
    const t = new THREE.CanvasTexture(c); t.anisotropy = 8; return t;
  }
  function radialTex(stops) {
    return canvasTex(256, 256, (g, w, h) => { const r = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2); stops.forEach(([o, c]) => r.addColorStop(o, c)); g.fillStyle = r; g.fillRect(0, 0, w, h); });
  }
  const rbox = (w, h, d, r, mat) => new THREE.Mesh(new THREE.RoundedBoxGeometry(w, h, d, 4, r), mat);
  function add(mesh, x, y, z, parent) { mesh.position.set(x, y, z); (parent || G.m).add(mesh); return mesh; }
  const box = (w, h, d, mat, x, y, z, p) => add(new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat), x, y, z, p);

  // Stratasys mark (approximation drawn in code; swap for the official artwork when available)
  function mark(g, x, y, k, color, lw) {
    g.save(); g.translate(x, y); g.scale(k, k); g.strokeStyle = color; g.lineWidth = lw || 9; g.lineJoin = 'miter';
    const P = (pts, close) => { g.beginPath(); pts.forEach(([a, b], i) => i ? g.lineTo(a, b) : g.moveTo(a, b)); if (close) g.closePath(); g.stroke(); };
    P([[0, -62], [58, -16], [0, 30], [-58, -16]], true); P([[0, -62], [0, -16]]); P([[-58, -16], [58, -16]]);
    P([[-58, 30], [0, -16], [58, 30], [0, 76], [-58, 30]]); P([[-58, 30], [58, 30]]); P([[0, 30], [0, 76]]);
    g.restore();
  }
  function wordmark(g, x, y, size, color, align) {
    g.save(); g.fillStyle = color; g.textBaseline = 'middle'; g.textAlign = 'left';
    g.font = `900 ${size}px "Segoe UI Black", "Arial Black", Arial`; const w1 = g.measureText('strata').width;
    g.font = `400 ${size}px "Segoe UI", Arial`; const w2 = g.measureText('sys').width;
    const x0 = align === 'center' ? x - (w1 + w2) / 2 : x;
    g.font = `900 ${size}px "Segoe UI Black", "Arial Black", Arial`; g.fillText('strata', x0, y);
    g.font = `400 ${size}px "Segoe UI", Arial`; g.fillText('sys', x0 + w1, y);
    g.restore();
  }

  function buildEnv() {
    const s = new THREE.Scene();
    const room = new THREE.Mesh(new THREE.BoxGeometry(20, 12, 20), new THREE.MeshBasicMaterial({ color: 0x1b2036, side: THREE.BackSide }));
    room.position.y = 5; s.add(room);
    const soft = (w, h, x, y, z, ry, k, rx) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(k, k, k * 1.05), side: THREE.DoubleSide })); m.position.set(x, y, z); m.rotation.set(rx || 0, ry, 0); s.add(m); };
    soft(8, 5, 0, 5, 9, Math.PI, 5); soft(5, 8, -9, 4, 2, Math.PI / 2, 3); soft(6, 4, 8, 6, -4, -Math.PI / 2, 2.2); soft(10, 10, 0, 11, 0, 0, 1.6, Math.PI / 2);
    const pm = new THREE.PMREMGenerator(R); const t = pm.fromScene(s, 0.02).texture; pm.dispose(); return t;
  }

  function sideDecal(frontLeft) {
    return canvasTex(512, 512, (g, w, h) => {
      if (!frontLeft) { g.translate(w, 0); g.scale(-1, 1); }
      const l = g.createLinearGradient(0, 0, w, 0); l.addColorStop(0, '#c9ccd1'); l.addColorStop(1, '#a9adb3'); g.fillStyle = l; g.fillRect(0, 0, w, h);
      g.fillStyle = '#121316'; g.beginPath(); g.moveTo(0.30 * w, 0); g.lineTo(w, 0); g.lineTo(w, 0.42 * h); g.lineTo(0.70 * w, 0.42 * h); g.closePath(); g.fill();
      const bx = 0.60 * w, bw = 0.30 * w, by = 0.10 * h, bh = 0.84 * h, r = 40;
      g.beginPath(); g.moveTo(bx + r, by); g.lineTo(bx + bw - r, by); g.quadraticCurveTo(bx + bw, by, bx + bw, by + r); g.lineTo(bx + bw, by + bh - r); g.quadraticCurveTo(bx + bw, by + bh, bx + bw - r, by + bh); g.lineTo(bx + r, by + bh); g.quadraticCurveTo(bx, by + bh, bx, by + bh - r); g.lineTo(bx, by + r); g.quadraticCurveTo(bx, by, bx + r, by); g.fill();
      g.save(); g.translate(bx + bw / 2, by + bh / 2); g.rotate(-Math.PI / 2); if (!frontLeft) g.scale(-1, 1);
      wordmark(g, 0, 0, 92, '#f1f2f4', 'center'); g.restore();
    });
  }

  function init(canvas, images) {
    imgs = images || {};
    R = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
    R.setPixelRatio(1); R.setSize(1920, 1080, false);
    scene = new THREE.Scene();
    scene.background = canvasTex(16, 512, (g, w, h) => { const l = g.createLinearGradient(0, 0, 0, h); l.addColorStop(0, '#0b1020'); l.addColorStop(1, '#04060c'); g.fillStyle = l; g.fillRect(0, 0, w, h); });
    scene.fog = new THREE.Fog(0x070a14, 5, 12);
    cam = new THREE.PerspectiveCamera(31, 16 / 9, 0.02, 60);
    scene.environment = buildEnv();
    G.m = new THREE.Group(); scene.add(G.m);

    M.silver = new THREE.MeshStandardMaterial({ color: 0xe0e3e8, metalness: 0.85, roughness: 0.34, envMapIntensity: 1.9 });
    M.black = new THREE.MeshStandardMaterial({ color: 0x141518, metalness: 0.35, roughness: 0.4, envMapIntensity: 1.0 });
    M.inner = new THREE.MeshStandardMaterial({ color: 0xb8c0ca, metalness: 0.9, roughness: 0.28, envMapIntensity: 1.6 });
    M.led = new THREE.MeshBasicMaterial({ color: 0x3b82f6 });
    M.feet = new THREE.MeshStandardMaterial({ color: 0x0c0c0e, roughness: 0.8 });

    const dots = canvasTex(512, 512, (g, w, h) => { g.fillStyle = '#000'; g.fillRect(0, 0, w, h); g.fillStyle = '#fff'; for (let i = 0; i < 11; i++) for (let j = 0; j < 13; j++) { g.beginPath(); g.arc(26 + i * 46, 20 + j * 38, 6, 0, 7); g.fill(); } });
    const dotsC = canvasTex(512, 512, (g, w, h) => { g.fillStyle = '#e9ebef'; g.fillRect(0, 0, w, h); g.fillStyle = '#c8b46a'; for (let i = 0; i < 11; i++) for (let j = 0; j < 13; j++) g.fillRect(22 + i * 46, 16 + j * 38, 8, 8); });
    const panel = () => new THREE.MeshStandardMaterial({ map: dotsC, color: 0x8f949b, roughness: 0.9, metalness: 0, emissive: 0, emissiveMap: dots, emissiveIntensity: 0 });
    M.pDoor = panel(); M.pBack = panel(); M.pL = panel(); M.pR = panel();

    // feet, base, LED strip
    for (const [x, z] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) add(new THREE.Mesh(new THREE.CylinderGeometry(mm(18), mm(18), mm(10), 20), M.feet), x * (W / 2 - mm(45)), mm(5), z * (D / 2 - mm(45)));
    add(rbox(W, BASE1 - BASE0, D, mm(16), M.silver), 0, (BASE0 + BASE1) / 2, 0);
    const label = canvasTex(512, 160, (g, w, h) => { g.fillStyle = '#f4f5f7'; g.font = '600 92px "Segoe UI", Arial'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText('sCure', w / 2 - 10, h / 2 + 6); g.font = '600 30px "Segoe UI", Arial'; g.fillText('TM', w / 2 + 128, h / 2 - 30); });
    add(new THREE.Mesh(new THREE.PlaneGeometry(mm(190), mm(60)), new THREE.MeshBasicMaterial({ map: label, transparent: true })), 0, mm(48), D / 2 + 0.003);
    M.strip = add(rbox(W + 0.006, STRIP1 - BASE1, D + 0.006, mm(3), M.led), 0, (BASE1 + STRIP1) / 2, 0);

    // body shell: sides (with decal), black back, front frame around the chamber opening
    const bh = BODY1 - STRIP1, bc = (STRIP1 + BODY1) / 2, st = mm(20);
    const decR = new THREE.MeshStandardMaterial({ map: sideDecal(true), metalness: 0.75, roughness: 0.36, envMapIntensity: 1.6 });
    const decL = new THREE.MeshStandardMaterial({ map: sideDecal(false), metalness: 0.75, roughness: 0.36, envMapIntensity: 1.6 });
    box(st, bh, D - mm(4), [decR, M.silver, M.silver, M.silver, M.silver, M.silver], W / 2 - st / 2, bc, 0);
    box(st, bh, D - mm(4), [M.silver, decL, M.silver, M.silver, M.silver, M.silver], -W / 2 + st / 2, bc, 0);
    box(W - 2 * st, bh, mm(20), M.black, 0, bc, -D / 2 + mm(10));
    const fz = ZF + mm(4), fd = mm(8), sw = W / 2 - st - CX;
    box(sw, bh, fd, M.inner, -(CX + sw / 2), bc, fz);
    box(sw, bh, fd, M.inner, CX + sw / 2, bc, fz);
    box(2 * CX, BODY1 - CY1, fd, M.inner, 0, (CY1 + BODY1) / 2, fz);
    box(2 * CX, CY0 - STRIP1, fd, M.inner, 0, (STRIP1 + CY0) / 2, fz);
    // chamber shell
    const cd = ZF - ZB, cz = (ZF + ZB) / 2;
    box(2 * CX, mm(6), cd, M.inner, 0, CY0 - mm(3), cz);
    box(2 * CX, mm(6), cd, M.inner, 0, CY1 + mm(3), cz);
    for (const x of [-CX - 0.002, CX + 0.002]) box(0.003, CY1 - CY0, cd, M.inner, x, (CY0 + CY1) / 2, cz);
    box(2 * CX, CY1 - CY0, 0.003, M.inner, 0, (CY0 + CY1) / 2, ZB - 0.002);
    // head with screen
    add(rbox(W + mm(2), TOP - BODY1, D + mm(2), mm(18), M.black), 0, (BODY1 + TOP) / 2, 0);
    box(SCR.w + mm(14), SCR.h + mm(14), mm(3), new THREE.MeshStandardMaterial({ color: 0x050607, metalness: 0.8, roughness: 0.15 }), SCR.x, SCR.y, D / 2 + mm(1.5));
    const scv = document.createElement('canvas'); scv.width = 800; scv.height = 480; sctx = scv.getContext('2d');
    stex = new THREE.CanvasTexture(scv); stex.anisotropy = 8;
    G.screen = add(new THREE.Mesh(new THREE.PlaneGeometry(SCR.w, SCR.h), new THREE.MeshBasicMaterial({ map: stex })), SCR.x, SCR.y, SCR.z);

    // LED panels: back, left, right walls + door
    const ph = mm(270), pc = mm(255);
    add(new THREE.Mesh(new THREE.PlaneGeometry(2 * CX - mm(20), ph), M.pBack), 0, pc, ZB + 0.002);
    add(new THREE.Mesh(new THREE.PlaneGeometry(cd - mm(10), ph), M.pL), -CX + 0.002, pc, cz).rotation.y = Math.PI / 2;
    add(new THREE.Mesh(new THREE.PlaneGeometry(cd - mm(10), ph), M.pR), CX - 0.002, pc, cz).rotation.y = -Math.PI / 2;

    // top compartment: perforated plate, heater coil, fan, diagonal grilles
    const perf = canvasTex(512, 128, (g, w, h) => { g.fillStyle = '#c4cad3'; g.fillRect(0, 0, w, h); g.fillStyle = '#20242c'; for (let i = 0; i < 40; i++) for (let j = 0; j < 8; j++) { g.beginPath(); g.arc(8 + i * 12.6, 8 + j * 15, 3.4, 0, 7); g.fill(); } });
    box(2 * CX, mm(3), cd, new THREE.MeshStandardMaterial({ map: perf, metalness: 0.8, roughness: 0.35, transparent: true, opacity: 0.92 }), 0, PLATE, cz);
    const pts = []; for (let i = 0; i <= 14; i++) pts.push(new THREE.Vector3(-CX + mm(30) + i * (2 * CX - mm(60)) / 14, PLATE + mm(30) + (i % 2 ? mm(12) : 0), cz));
    M.coil = new THREE.MeshStandardMaterial({ color: 0x4a3b36, emissive: 0xff6a1f, emissiveIntensity: 0, metalness: 0.4, roughness: 0.5 });
    G.m.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 160, mm(4), 8), M.coil));
    G.fan = add(new THREE.Group(), CX - mm(55), PLATE + mm(60), ZB + mm(14));
    G.fan.add(new THREE.Mesh(new THREE.TorusGeometry(mm(38), mm(5), 10, 32), M.inner));
    G.blades = new THREE.Group(); G.fan.add(G.blades);
    for (let i = 0; i < 5; i++) { const b = new THREE.Mesh(new THREE.BoxGeometry(mm(34), mm(13), mm(2)), new THREE.MeshStandardMaterial({ color: 0x2a2f3a, metalness: 0.4, roughness: 0.4 })); b.position.x = mm(18); b.rotation.x = 0.4; const gp = new THREE.Group(); gp.rotation.z = i * Math.PI * 2 / 5; gp.add(b); G.blades.add(gp); }
    const grille = canvasTex(256, 256, (g, w, h) => { g.fillStyle = '#d9dde3'; g.fillRect(0, 0, w, h); g.strokeStyle = '#15181d'; g.lineWidth = 14; for (let i = -10; i < 20; i++) { g.beginPath(); g.moveTo(i * 28, h); g.lineTo(i * 28 + h, 0); g.stroke(); } });
    const grM = new THREE.MeshStandardMaterial({ map: grille, metalness: 0.7, roughness: 0.4 });
    add(new THREE.Mesh(new THREE.PlaneGeometry(mm(80), mm(70)), grM), -CX + mm(50), PLATE + mm(55), ZB + 0.004);
    G.vent = add(new THREE.Mesh(new THREE.PlaneGeometry(mm(70), mm(55)), grM.clone()), -CX + mm(45), CY0 + mm(35), ZB + 0.004);

    // shelf + parts
    const rod = new THREE.MeshStandardMaterial({ color: 0xd0d3d8, metalness: 0.9, roughness: 0.25 });
    for (const z of [ZB + mm(25), ZF - mm(25)]) { const r = new THREE.Mesh(new THREE.CylinderGeometry(mm(3), mm(3), 2 * CX, 10), rod); r.rotation.z = Math.PI / 2; add(r, 0, mm(260), z); }
    box(2 * CX - mm(10), mm(3), cd - mm(30), new THREE.MeshStandardMaterial({ color: 0xd0d3d8, metalness: 0.9, roughness: 0.25, transparent: true, opacity: 0.6 }), 0, mm(258), cz);
    const sh = new THREE.Shape(), n = 14, ro = mm(62), ri = mm(50);
    for (let i = 0; i < n * 2; i++) { const a = (i / (n * 2)) * Math.PI * 2, r = i % 2 ? ri : ro, a2 = a + 0.08; if (i === 0) sh.moveTo(Math.cos(a) * r, Math.sin(a) * r); else sh.lineTo(Math.cos(a) * r, Math.sin(a) * r); sh.lineTo(Math.cos(a2) * r, Math.sin(a2) * r); }
    const hole = new THREE.Path(); hole.absarc(0, 0, mm(20), 0, Math.PI * 2, true); sh.holes.push(hole);
    M.part = new THREE.MeshStandardMaterial({ color: 0x7684ad, metalness: 0.1, roughness: 0.42, emissive: 0 });
    parts.gear = new THREE.Mesh(new THREE.ExtrudeGeometry(sh, { depth: mm(18), bevelEnabled: true, bevelSize: mm(1.5), bevelThickness: mm(1.5), bevelSegments: 2 }), M.part);
    parts.gear.rotation.x = -Math.PI / 2; add(parts.gear, -mm(55), mm(262), cz);
    parts.knot = add(new THREE.Mesh(new THREE.TorusKnotGeometry(mm(28), mm(9), 120, 14), M.part), mm(85), mm(305), cz);
    add(new THREE.Mesh(new THREE.CylinderGeometry(mm(9), mm(9), mm(26), 16), new THREE.MeshStandardMaterial({ color: 0x3aa0d8, metalness: 0.5, roughness: 0.3, emissive: 0x0a3a5a })), CX - mm(25), CY0 + mm(14), ZB + mm(20));

    // door (hinge on the left, swings toward the viewer)
    G.door = add(new THREE.Group(), -W / 2, bc, D / 2);
    const dw = W, dh = bh - mm(4), dt = mm(26);
    const doorTex = canvasTex(512, 576, (g, w, h) => {
      const l = g.createLinearGradient(0, 0, w, 0); l.addColorStop(0, '#a3a7ad'); l.addColorStop(0.5, '#d7d9dd'); l.addColorStop(1, '#adb1b6'); g.fillStyle = l; g.fillRect(0, 0, w, h);
      mark(g, 46, 42, 0.26, '#f6f7f9', 10); wordmark(g, 72, 44, 30, '#f6f7f9');
    });
    M.doorFront = new THREE.MeshStandardMaterial({ map: doorTex, metalness: 0.78, roughness: 0.32, envMapIntensity: 1.7, transparent: true });
    M.doorEdge = M.silver.clone(); M.doorEdge.transparent = true;
    const db = new THREE.Mesh(new THREE.BoxGeometry(dw, dh, dt), [M.doorEdge, M.doorEdge, M.doorEdge, M.doorEdge, M.doorFront, M.doorEdge]); db.position.set(dw / 2, 0, -dt / 2); G.door.add(db);
    const dIn = new THREE.Mesh(new THREE.PlaneGeometry(mm(270), mm(330)), M.pDoor); dIn.rotation.y = Math.PI; dIn.position.set(dw / 2, -mm(10), -dt - 0.002); G.door.add(dIn);

    // particles
    const mkPts = (N, size) => { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(N * 3), 3)); g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(N * 3), 3));
      const p = new THREE.Points(g, new THREE.PointsMaterial({ size, vertexColors: true, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, map: radialTex([[0, '#fff'], [0.4, 'rgba(255,255,255,.6)'], [1, 'rgba(255,255,255,0)']]) }));
      p.frustumCulled = false; G.m.add(p); return p; };
    let s = 11; const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
    parts.n2 = mkPts(150, mm(12)); parts.n2.seed = Array.from({ length: 150 }, () => ({ sp: 0.12 + rnd() * 0.2, ph: rnd(), dx: rnd(), dz: rnd() }));
    parts.air = mkPts(110, mm(11)); parts.air.seed = Array.from({ length: 110 }, () => ({ ph: rnd(), j: [(rnd() - 0.5) * mm(30), (rnd() - 0.5) * mm(30), (rnd() - 0.5) * mm(30)] }));
    G.air = new THREE.CatmullRomCurve3([new THREE.Vector3(-CX + mm(45), CY0 + mm(40), ZB + mm(20)), new THREE.Vector3(-mm(60), mm(200), cz), new THREE.Vector3(mm(40), mm(360), cz), new THREE.Vector3(CX - mm(55), PLATE + mm(50), ZB + mm(20))]);

    // lights
    scene.add(new THREE.HemisphereLight(0xaab8ff, 0x20242e, 0.18));
    const key = new THREE.DirectionalLight(0xffffff, 1.1); key.position.set(2.5, 4, 4); scene.add(key);
    const rim = new THREE.DirectionalLight(0x8fb0ff, 0.9); rim.position.set(-4, 2, -3); scene.add(rim);
    G.pl = new THREE.PointLight(0xa66bff, 0, 1.6, 1.6); G.pl.position.set(0, mm(260), cz); scene.add(G.pl);
    G.plHeat = new THREE.PointLight(0xff7a33, 0, 1.0, 1.8); G.plHeat.position.set(0, PLATE + mm(40), cz); scene.add(G.plHeat);
    G.plShow = new THREE.SpotLight(0xffffff, 0, 3, 0.5, 0.6, 1.5); G.plShow.position.set(0.4, 1.6, 1.6); G.plShow.target.position.set(-mm(20), mm(270), cz); scene.add(G.plShow, G.plShow.target);

    // ground
    const floor = new THREE.Mesh(new THREE.CircleGeometry(6, 64), new THREE.MeshStandardMaterial({ color: 0x0b0f19, metalness: 0.15, roughness: 0.8 }));
    floor.rotation.x = -Math.PI / 2; scene.add(floor);
    const shadow = new THREE.Mesh(new THREE.PlaneGeometry(2.0, 2.0), new THREE.MeshBasicMaterial({ map: radialTex([[0, 'rgba(0,0,0,.85)'], [0.55, 'rgba(0,0,0,.45)'], [1, 'rgba(0,0,0,0)']]), transparent: true, depthWrite: false }));
    shadow.rotation.x = -Math.PI / 2; shadow.position.y = 0.002; G.m.add(shadow);
    M.glow = new THREE.MeshBasicMaterial({ map: radialTex([[0, 'rgba(255,255,255,.55)'], [0.3, 'rgba(255,255,255,.16)'], [1, 'rgba(255,255,255,0)']]), color: 0x3b82f6, opacity: 0.5, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false });
    const glow = new THREE.Mesh(new THREE.PlaneGeometry(3.0, 3.0), M.glow); glow.rotation.x = -Math.PI / 2; glow.position.y = 0.006; G.m.add(glow);

    comp = new THREE.EffectComposer(R); comp.setSize(1920, 1080);
    comp.addPass(new THREE.RenderPass(scene, cam));
    bloom = new THREE.UnrealBloomPass(new THREE.Vector2(960, 540), 0.4, 0.5, 0.92); comp.addPass(bloom);
  }

  // ---------- camera: orbit keyframes (real seconds) + "screen" pose for the zoom in/out
  const KF = {
    az:    [[4, -30], [8, 28], [13, 18], [15, 14], [41, 12], [44, -18], [53, 26], [56.5, 12], [60, 12]],
    r:     [[4, 5.2], [8, 4.4], [13, 4.0], [15, 3.9], [41, 4.2], [44, 4.1], [53, 3.8], [56.5, 2.7], [60, 2.6]],
    h:     [[4, 1.4], [8, 1.25], [15, 1.2], [44, 1.2], [53, 1.05], [56.5, 0.9], [60, 0.9]],
    ty:    [[4, 0.85], [15, 0.8], [44, 0.82], [53, 0.8], [56.5, 0.7], [60, 0.7]],
    shift: [[4, -360], [12.6, -360], [14.6, 0], [60, 0]],
  };
  const ZOOM = [[15, 0], [18.6, 1], [41, 1], [43.6, 0]];       // 1 = camera square on the screen
  function screenPose() { const d = SCR.w * 1.218; return { pos: new THREE.Vector3(SCR.x, SCR.y, SCR.z + d), at: new THREE.Vector3(SCR.x, SCR.y, SCR.z) }; }

  function drawScreen(st) {
    const g = sctx, w = 800, h = 480, im = st.screenImg && imgs[st.screenImg];
    if (im && im.complete && im.naturalWidth) { g.drawImage(im, 0, 0, w, h); stex.needsUpdate = true; return; }
    g.fillStyle = '#0b0b0d'; g.fillRect(0, 0, w, h);
    g.fillStyle = '#1b1c1f'; g.fillRect(0, 0, w, 72);
    g.fillStyle = '#e9ecf5'; g.font = '700 34px "Segoe UI", Arial'; g.textBaseline = 'middle'; g.fillText('sCure', 66, 36);
    g.strokeStyle = '#e9ecf5'; g.lineWidth = 3; g.beginPath(); g.moveTo(30, 20); g.lineTo(46, 36); g.lineTo(30, 52); g.lineTo(14, 36); g.closePath(); g.stroke();
    g.fillStyle = '#fff'; g.font = '700 32px "Segoe UI", Arial'; g.textAlign = 'right'; g.fillText(st.temp.toFixed(1) + '°C', w - 28, 36); g.textAlign = 'left';
    g.fillStyle = '#141416'; g.fillRect(20, 88, w - 40, 78);
    g.fillStyle = st.modeCol; g.beginPath(); g.arc(54, 127, 13, 0, 7); g.fill();
    g.fillStyle = '#fff'; g.font = '600 34px "Segoe UI", Arial'; g.fillText(st.mode, 86, 128);
    g.fillStyle = '#4ade80'; g.textAlign = 'right'; g.fillText(Math.round(st.total * 100) + '%', w - 40, 128); g.textAlign = 'left';
    const names = ['Heating', 'N₂ Purge', 'Cure', 'Bleach', 'Cooling'];
    for (let i = 0; i < 5; i++) {
      const x = 20 + i * 154, on = i === st.step; g.fillStyle = '#121214'; g.fillRect(x, 184, 144, 276);
      g.strokeStyle = on ? '#3b82f6' : '#26272b'; g.lineWidth = 4; g.strokeRect(x + 2, 186, 140, 272);
      g.fillStyle = on ? '#fff' : '#8b93a7'; g.font = '600 24px "Segoe UI", Arial'; g.textAlign = 'center'; g.fillText(names[i], x + 72, 216);
      const p = i < st.step ? 1 : on ? st.prog : 0;
      g.strokeStyle = '#25262b'; g.lineWidth = 10; g.beginPath(); g.arc(x + 72, 320, 50, 0, 7); g.stroke();
      g.strokeStyle = i < st.step ? '#4ade80' : '#3b82f6'; g.beginPath(); g.arc(x + 72, 320, 50, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * p); g.stroke();
      g.fillStyle = on ? '#fff' : '#5c6273'; g.font = '700 30px "Segoe UI", Arial'; g.fillText(Math.round(p * 100) + '%', x + 72, 322);
      g.textAlign = 'left';
    }
    stex.needsUpdate = true;
  }

  function render(s) {
    const T = s.T, P = k => pw(T, k);
    // machine entrance (rises and turns in)
    const e = clamp((T - 4.2) / 2.6), ee = e * e * (3 - 2 * e);
    G.m.position.y = lerp(-0.35, 0, ee); G.m.rotation.y = lerp(-0.9, 0, ee); G.m.scale.setScalar(lerp(0.92, 1, ee));
    // camera
    const az = P(KF.az) * Math.PI / 180, r = P(KF.r), hh = P(KF.h), ty = P(KF.ty), z = P(ZOOM);
    const bob = Math.sin(T * 0.5) * 0.03 * (1 - z);
    const orb = new THREE.Vector3(Math.sin(az) * r, hh + bob, Math.cos(az) * r), at = new THREE.Vector3(0, ty, 0);
    const sp = screenPose();
    cam.position.copy(orb.lerp(sp.pos, z)); cam.lookAt(at.lerp(sp.at, z));
    cam.setViewOffset(1920, 1080, P(KF.shift) * (1 - z), 42 * z, 1920, 1080); cam.updateProjectionMatrix();

    // door + x-ray
    G.door.rotation.y = -s.door * 1.9;
    const xr = s.xray;
    M.doorFront.opacity = lerp(1, 0.1, xr); M.doorEdge.opacity = lerp(1, 0.16, xr); M.doorFront.depthWrite = xr < 0.5;

    // LED panels
    const lit = Math.max(s.uv, s.bl), c405 = new THREE.Color(0xa66bff), c450 = new THREE.Color(0x4aa3ff), cc = s.bl > s.uv ? c450 : c405;
    for (const k of ['pBack', 'pL', 'pDoor', 'pR']) {
      const on = (s.bl > s.uv && k !== 'pDoor') ? 0 : lit;
      M[k].emissive.copy(cc); M[k].emissiveIntensity = on * 2.6;
      M[k].color.setRGB(lerp(0.56, 0.32, on), lerp(0.58, 0.26, on), lerp(0.61, 0.66, on));
    }
    G.pl.color.copy(cc); G.pl.intensity = lit * 0.9;
    G.plHeat.intensity = s.heat * 0.45;
    M.coil.emissiveIntensity = s.heat * 1.5; M.coil.color.setRGB(lerp(0.29, 1, s.heat), lerp(0.23, 0.45, s.heat), lerp(0.21, 0.2, s.heat));
    G.plShow.intensity = s.show * 0.8;
    const scol = new THREE.Color(s.ledCol); M.led.color.copy(scol).multiplyScalar(1.25); M.glow.color.copy(scol);
    // parts
    M.part.color.setRGB(lerp(0.30, 0.55, s.cure), lerp(0.36, 0.52, s.cure), lerp(0.55, 0.68, s.cure));
    M.part.emissive.copy(cc).multiplyScalar(0.12 * lit);
    parts.gear.rotation.z = T * 0.5; parts.knot.rotation.set(T * 0.4, T * 0.7, 0);
    G.blades.rotation.z = -s.fan * Math.PI / 180;
    G.vent.material.color.setScalar(lerp(1, 1.6, s.dmp));
    // nitrogen + air
    const n2 = parts.n2, na = n2.geometry.attributes.position, nc = n2.geometry.attributes.color;
    n2.seed.forEach((p, i) => { const u = (T * p.sp + p.ph) % 1, f = Math.sin(u * Math.PI) * s.n2;
      na.setXYZ(i, lerp(CX - mm(25), -CX + 2 * CX * p.dx, u), CY0 + mm(20) + u * mm(380), lerp(ZB + mm(20), ZB + (ZF - ZB) * p.dz, u)); nc.setXYZ(i, 0.3 * f, 0.85 * f, f); });
    na.needsUpdate = nc.needsUpdate = true;
    const ar = parts.air, aa = ar.geometry.attributes.position, ac = ar.geometry.attributes.color, a = Math.max(s.aW, s.aC), cw = s.aC > s.aW ? [0.3, 0.8, 1] : [1, 0.62, 0.28];
    ar.seed.forEach((p, i) => { const u = (T * 0.3 + p.ph) % 1, pt = G.air.getPoint(u), f = Math.sin(u * Math.PI) * a; aa.setXYZ(i, pt.x + p.j[0], pt.y + p.j[1], pt.z + p.j[2]); ac.setXYZ(i, cw[0] * f, cw[1] * f, cw[2] * f); });
    aa.needsUpdate = ac.needsUpdate = true;

    drawScreen(s);
    bloom.strength = (0.35 + lit * 0.3 + s.heat * 0.08) * (1 - 0.7 * z);
    comp.render();
  }

  window.M3D = { init, render };
})();
