// Procedural 3D model of the sCure Box, matched to the reference views sheet (shots/reference-views.png):
// 410 W x 461 D x 665 H mm, black head (~27 % of the height) with a large screen, brushed-aluminium door,
// blue LED strip over the base, side panels with a front pillar, a black diagonal and the "stratasys" band.
// Chamber 293 x 174 x 410 mm (sheet). Drawn with three.js r147 (classic build).
// API:  M3D.init(canvas, {imgKey: HTMLImageElement})   M3D.render(state)
//       state.cam = {pos:[x,y,z], at:[x,y,z], fov} and state.bg = '#hex' override the film camera (compare views)
(function () {
  const K = 1.58 / 665;                       // mm -> world units (machine is 1.58 tall)
  const mm = v => v * K;
  const W = mm(410), D = mm(461), ST = mm(22);                // width, depth, side-panel thickness
  const FEET = mm(15), BASE1 = mm(106), STRIP1 = mm(120), DOOR1 = mm(485), TOP = mm(665);
  const CX = mm(170), CY0 = mm(128), CY1 = mm(478);      // chamber half-width, floor, ceiling
  const ZF = D / 2 - mm(30), ZB = ZF - mm(174);              // chamber front opening / back wall
  const PLATE = mm(395);                                     // perforated plate under the top compartment
  const SCR = { x: -mm(6), y: mm(578), z: D / 2 + mm(4) + 0.002, w: mm(205), h: mm(123) };

  let R, scene, cam, comp, bloom, M = {}, G = {}, sctx, stex, imgs = {}, parts = {}, defaultBg;
  const lerp = (a, b, t) => a + (b - a) * t;
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));

  function canvasTex(w, h, draw) {
    const c = document.createElement('canvas'); c.width = w; c.height = h; draw(c.getContext('2d'), w, h);
    const t = new THREE.CanvasTexture(c); t.anisotropy = 8; return t;
  }
  function radialTex(stops) {
    return canvasTex(256, 256, (g, w, h) => { const r = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2); stops.forEach(([o, c]) => r.addColorStop(o, c)); g.fillStyle = r; g.fillRect(0, 0, w, h); });
  }
  const rbox = (w, h, d, r, mat) => new THREE.Mesh(new THREE.RoundedBoxGeometry(w, h, d, 5, r), mat);
  function add(mesh, x, y, z, parent) { mesh.position.set(x, y, z); (parent || G.m).add(mesh); return mesh; }
  const box = (w, h, d, mat, x, y, z, p) => add(new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat), x, y, z, p);

  // brushed aluminium base coat (fine vertical streaks)
  function brushed(g, w, h, light, dark) {
    const l = g.createLinearGradient(0, 0, w, 0); l.addColorStop(0, dark); l.addColorStop(0.5, light); l.addColorStop(1, dark);
    g.fillStyle = l; g.fillRect(0, 0, w, h);
    let s = 7; const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
    for (let i = 0; i < w * 0.8; i++) { g.fillStyle = `rgba(${rnd() < 0.5 ? '255,255,255' : '0,0,0'},${0.006 + rnd() * 0.01})`; g.fillRect(rnd() * w, 0, 1 + rnd(), h); }
  }
  // Stratasys mark + wordmark (approximation drawn in code; swap for the official artwork when available)
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
    g.font = `400 ${size * 0.22}px "Segoe UI", Arial`; g.fillText('®', x0 + w1 + w2 + size * 0.04, y - size * 0.32);
    g.restore(); return w1 + w2;
  }

  function buildEnv() {   // neutral studio: grey room + white soft boxes
    const s = new THREE.Scene();
    const room = new THREE.Mesh(new THREE.BoxGeometry(20, 12, 20), new THREE.MeshBasicMaterial({ color: 0x26272a, side: THREE.BackSide }));
    room.position.y = 5; s.add(room);
    const soft = (w, h, x, y, z, ry, k, rx) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(k, k, k), side: THREE.DoubleSide })); m.position.set(x, y, z); m.rotation.set(rx || 0, ry, 0); s.add(m); };
    soft(8, 5, 0, 5, 9, Math.PI, 4.5); soft(4, 9, -9, 4, 3, Math.PI / 2, 3.2); soft(4, 9, 9, 4, 3, -Math.PI / 2, 2.6); soft(12, 12, 0, 11, 0, 0, 1.8, Math.PI / 2);
    const pm = new THREE.PMREMGenerator(R); const t = pm.fromScene(s, 0.02).texture; pm.dispose(); return t;
  }

  // side panel artwork; canvas left = front (right side) — mirrored for the left side
  function sideDecal(frontLeft) {
    return canvasTex(512, 722, (g, w, h) => {
      const X = u => (frontLeft ? u : 1 - u) * w;           // u: 0 = front edge, 1 = rear edge
      brushed(g, w, h, '#d5d8dc', '#b4b8be');
      // front pillar: cylindrical shading + seam
      const px0 = Math.min(X(0), X(0.10)), px1 = Math.max(X(0), X(0.10));
      const pg = g.createLinearGradient(px0, 0, px1, 0); pg.addColorStop(0, '#9da1a7'); pg.addColorStop(0.45, '#eef0f2'); pg.addColorStop(1, '#a3a7ad');
      g.fillStyle = pg; g.fillRect(px0, 0.25 * h, px1 - px0, h);
      g.fillStyle = 'rgba(0,0,0,.55)'; g.fillRect(X(0.10) - 3, 0.25 * h, 6, h);
      // black head + diagonal
      g.fillStyle = '#141518'; g.beginPath();
      [[0, 0], [1, 0], [1, 0.10], [0.55, 0.10], [0.12, 0.25], [0, 0.25]].forEach(([u, v], i) => i ? g.lineTo(X(u), v * h) : g.moveTo(X(u), v * h));
      g.closePath(); g.fill();
      // rounded black band with the vertical wordmark
      const bx = Math.min(X(0.61), X(0.91)), bw = 0.30 * w, by = 0.17 * h, bh = 0.63 * h, r = 36;
      g.beginPath(); g.moveTo(bx + r, by); g.arcTo(bx + bw, by, bx + bw, by + bh, r); g.arcTo(bx + bw, by + bh, bx, by + bh, r); g.arcTo(bx, by + bh, bx, by, r); g.arcTo(bx, by, bx + bw, by, r); g.fill();
      g.save(); g.translate(bx + bw / 2, by + bh / 2); g.rotate(-Math.PI / 2);
      g.font = '900 100px "Segoe UI Black", "Arial Black", Arial'; const wt = g.measureText('stratasys').width;
      wordmark(g, 0, 0, 100 * (bh * 0.80) / wt, '#f3f4f6', 'center'); g.restore();
      // LED dot on the pillar
      g.fillStyle = '#5b8cff'; g.fillRect(px0 + 2, 0.835 * h, px1 - px0 - 4, 0.016 * h);
    });
  }

  function init(canvas, images) {
    imgs = images || {};
    R = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
    R.setPixelRatio(1); R.setSize(1920, 1080, false);
    scene = new THREE.Scene();
    defaultBg = canvasTex(16, 512, (g, w, h) => { const l = g.createLinearGradient(0, 0, 0, h); l.addColorStop(0, '#0b1020'); l.addColorStop(1, '#04060c'); g.fillStyle = l; g.fillRect(0, 0, w, h); });
    scene.background = defaultBg;
    scene.fog = new THREE.Fog(0x070a14, 5, 12);
    cam = new THREE.PerspectiveCamera(31, 16 / 9, 0.02, 60);
    scene.environment = buildEnv();
    G.m = new THREE.Group(); scene.add(G.m);

    // ---------- materials
    const brushTex = canvasTex(512, 512, (g, w, h) => brushed(g, w, h, '#d6d9dd', '#b3b7bd'));
    M.silver = new THREE.MeshStandardMaterial({ map: brushTex, color: 0xffffff, metalness: 0.8, roughness: 0.36, envMapIntensity: 1.5 });
    M.black = new THREE.MeshStandardMaterial({ color: 0x111214, metalness: 0.3, roughness: 0.32, envMapIntensity: 1.0 });
    M.inner = new THREE.MeshStandardMaterial({ color: 0xdadee3, metalness: 0.96, roughness: 0.16, envMapIntensity: 1.7 });
    M.led = new THREE.MeshBasicMaterial({ color: 0x2f7bff });
    M.feet = new THREE.MeshStandardMaterial({ color: 0x0c0c0e, roughness: 0.8 });
    const dots = canvasTex(512, 512, (g, w, h) => { g.fillStyle = '#000'; g.fillRect(0, 0, w, h); g.fillStyle = '#fff'; for (let i = 0; i < 11; i++) for (let j = 0; j < 13; j++) { g.beginPath(); g.arc(26 + i * 46, 20 + j * 38, 6, 0, 7); g.fill(); } });
    const dotsC = canvasTex(512, 512, (g, w, h) => { g.fillStyle = '#eceef1'; g.fillRect(0, 0, w, h); g.fillStyle = '#d2bd62'; for (let i = 0; i < 11; i++) for (let j = 0; j < 13; j++) g.fillRect(22 + i * 46, 16 + j * 38, 8, 8); });
    const panel = () => new THREE.MeshStandardMaterial({ map: dotsC, color: 0xb4b8be, roughness: 0.9, metalness: 0, emissive: 0, emissiveMap: dots, emissiveIntensity: 0 });
    M.pDoor = panel(); M.pBack = panel(); M.pL = panel(); M.pR = panel();

    const inW = W - 2 * ST;                                   // width between the side panels
    // ---------- feet + side panels (full height, rounded) + back
    for (const [x, z] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) add(new THREE.Mesh(new THREE.CylinderGeometry(mm(16), mm(16), FEET, 20), M.feet), x * (W / 2 - mm(38)), FEET / 2, z * (D / 2 - mm(38)));
    const sideH = TOP - mm(26) - FEET, sideC = (TOP - mm(26) + FEET) / 2;   // stops under the rounded head cap
    const decR = new THREE.MeshStandardMaterial({ map: sideDecal(true), metalness: 0.78, roughness: 0.36, envMapIntensity: 1.5 });
    const decL = new THREE.MeshStandardMaterial({ map: sideDecal(false), metalness: 0.78, roughness: 0.36, envMapIntensity: 1.5 });
    const R0 = mm(12);                                         // vertical front-corner radius
    add(new THREE.Mesh(new THREE.BoxGeometry(ST, sideH, D - R0), [decR, M.silver, M.black, M.silver, M.silver, M.black]), W / 2 - ST / 2, sideC, -R0 / 2);
    add(new THREE.Mesh(new THREE.BoxGeometry(ST, sideH, D - R0), [M.silver, decL, M.black, M.silver, M.silver, M.black]), -W / 2 + ST / 2, sideC, -R0 / 2);
    // rounded front corners: quarter cylinder + filler, silver below the head and black on the head
    for (const sx of [-1, 1]) for (const [y0, y1, mat] of [[FEET, DOOR1, M.silver], [DOOR1, TOP - mm(40), M.black]]) {
      const pil = new THREE.Mesh(new THREE.CylinderGeometry(R0, R0, y1 - y0, 24, 1, false, sx > 0 ? 0 : -Math.PI / 2, Math.PI / 2), mat);
      add(pil, sx * (W / 2 - R0), (y0 + y1) / 2, D / 2 - R0);
      box(ST - R0, y1 - y0, R0, mat, sx * (W / 2 - ST + (ST - R0) / 2), (y0 + y1) / 2, D / 2 - R0 / 2);
    }
    box(inW, sideH, mm(16), M.black, 0, sideC, -D / 2 + mm(8));
    // ---------- head: black front + rounded black top cap
    add(rbox(W + mm(2), mm(70), D + mm(2), mm(24), M.black), 0, TOP - mm(35), 0);
    box(inW, TOP - DOOR1 - mm(40), mm(20), M.black, 0, (DOOR1 + TOP - mm(40)) / 2, D / 2 - mm(10));
    for (const sx of [-1, 1]) {                                // black corner pillars of the head
      const pil = new THREE.Mesh(new THREE.CylinderGeometry(mm(11), mm(11), TOP - DOOR1 - mm(13), 24, 1, false, sx > 0 ? 0 : Math.PI / 2, Math.PI / 2), M.black);
      add(pil, sx * (W / 2 - mm(11)), (DOOR1 + TOP - mm(13)) / 2, D / 2 - mm(11));
    }
    box(SCR.w + mm(12), SCR.h + mm(12), mm(3), new THREE.MeshStandardMaterial({ color: 0x050607, metalness: 0.6, roughness: 0.12 }), SCR.x, SCR.y, D / 2 + mm(1.5));
    const scv = document.createElement('canvas'); scv.width = 800; scv.height = 480; sctx = scv.getContext('2d');
    stex = new THREE.CanvasTexture(scv); stex.anisotropy = 8;
    G.screen = add(new THREE.Mesh(new THREE.PlaneGeometry(SCR.w, SCR.h), new THREE.MeshBasicMaterial({ map: stex })), SCR.x, SCR.y, SCR.z);
    // ---------- base front with the sCure label (right-aligned) + LED strip
    const baseTex = canvasTex(512, 120, (g, w, h) => {
      brushed(g, w, h, '#b9bdc2', '#9a9ea4');
      g.shadowColor = 'rgba(0,0,0,.35)'; g.shadowBlur = 4; g.shadowOffsetY = 1;
      g.fillStyle = '#ffffff'; g.textBaseline = 'middle'; g.textAlign = 'center'; g.font = '600 64px "Segoe UI", Arial'; g.fillText('sCure', w * 0.55, h / 2 + 8);
      g.font = '600 20px "Segoe UI", Arial'; g.fillText('TM', w * 0.55 + 98, h / 2 - 20);
    });
    box(inW, BASE1 - FEET, mm(20), [M.silver, M.silver, M.silver, M.silver, new THREE.MeshStandardMaterial({ map: baseTex, metalness: 0.78, roughness: 0.36, envMapIntensity: 1.5 }), M.silver], 0, (FEET + BASE1) / 2, D / 2 - mm(10));
    const stripTex = canvasTex(512, 16, (g, w, h) => { g.fillStyle = '#9bb8ff'; g.fillRect(0, 0, w, h); g.fillStyle = '#ffffff'; for (let i = 0; i < 5; i++) g.fillRect(36 + i * 104, 2, 40, h - 4); });
    M.led.map = stripTex;
    M.strip = box(inW + mm(2), STRIP1 - BASE1, mm(6), M.led, 0, (BASE1 + STRIP1) / 2, D / 2 - mm(2));
    for (const sx of [-1, 1]) box(mm(3), STRIP1 - BASE1, mm(14), M.led, sx * (W / 2 + 0.0005), (BASE1 + STRIP1) / 2, D / 2 - mm(22));

    // ---------- chamber: front frame, shell, LED panels
    const fz = ZF + mm(4), fd = mm(8), sw = W / 2 - ST - CX, bc = (STRIP1 + DOOR1) / 2, bh = DOOR1 - STRIP1;
    box(sw, bh, fd, M.inner, -(CX + sw / 2), bc, fz);
    box(sw, bh, fd, M.inner, CX + sw / 2, bc, fz);
    box(2 * CX, DOOR1 - CY1, fd, M.inner, 0, (CY1 + DOOR1) / 2, fz);
    box(2 * CX, CY0 - STRIP1, fd, M.inner, 0, (STRIP1 + CY0) / 2, fz);
    const cd = ZF - ZB, cz = (ZF + ZB) / 2;
    box(2 * CX, mm(6), cd, M.inner, 0, CY0 - mm(3), cz);
    box(2 * CX, mm(6), cd, M.inner, 0, CY1 + mm(3), cz);
    for (const x of [-CX - 0.002, CX + 0.002]) box(0.003, CY1 - CY0, cd, M.inner, x, (CY0 + CY1) / 2, cz);
    box(2 * CX, CY1 - CY0, 0.003, M.inner, 0, (CY0 + CY1) / 2, ZB - 0.002);
    const ph = mm(240), pc = mm(265);
    add(new THREE.Mesh(new THREE.PlaneGeometry(2 * CX - mm(24), mm(118)), M.pBack), 0, mm(200), ZB + 0.002);
    add(new THREE.Mesh(new THREE.PlaneGeometry(2 * CX - mm(24), mm(105)), M.pBack), 0, mm(330), ZB + 0.002);
    add(new THREE.Mesh(new THREE.PlaneGeometry(cd - mm(10), ph), M.pL), -CX + 0.002, pc, cz).rotation.y = Math.PI / 2;
    add(new THREE.Mesh(new THREE.PlaneGeometry(cd - mm(10), ph), M.pR), CX - 0.002, pc, cz).rotation.y = -Math.PI / 2;

    // top compartment: perforated plate, heater coil, fan, diagonal grilles (as in the sheet's open view)
    const perf = canvasTex(512, 128, (g, w, h) => { g.fillStyle = '#c4cad3'; g.fillRect(0, 0, w, h); g.fillStyle = '#20242c'; for (let i = 0; i < 40; i++) for (let j = 0; j < 8; j++) { g.beginPath(); g.arc(8 + i * 12.6, 8 + j * 15, 3.4, 0, 7); g.fill(); } });
    box(2 * CX, mm(3), cd, new THREE.MeshStandardMaterial({ map: perf, metalness: 0.8, roughness: 0.35, transparent: true, opacity: 0.92 }), 0, PLATE, cz);
    const pts = []; for (let i = 0; i <= 14; i++) pts.push(new THREE.Vector3(-CX + mm(30) + i * (2 * CX - mm(60)) / 14, PLATE + mm(26) + (i % 2 ? mm(11) : 0), cz));
    M.coil = new THREE.MeshStandardMaterial({ color: 0x4a3b36, emissive: 0xff6a1f, emissiveIntensity: 0, metalness: 0.4, roughness: 0.5 });
    G.m.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 160, mm(4), 8), M.coil));
    G.fan = add(new THREE.Group(), CX - mm(50), PLATE + mm(45), ZB + mm(14));
    G.fan.add(new THREE.Mesh(new THREE.TorusGeometry(mm(32), mm(5), 10, 32), M.inner));
    G.blades = new THREE.Group(); G.fan.add(G.blades);
    for (let i = 0; i < 5; i++) { const b = new THREE.Mesh(new THREE.BoxGeometry(mm(28), mm(11), mm(2)), new THREE.MeshStandardMaterial({ color: 0x2a2f3a, metalness: 0.4, roughness: 0.4 })); b.position.x = mm(15); b.rotation.x = 0.4; const gp = new THREE.Group(); gp.rotation.z = i * Math.PI * 2 / 5; gp.add(b); G.blades.add(gp); }
    const grille = canvasTex(256, 256, (g, w, h) => { g.fillStyle = '#d9dde3'; g.fillRect(0, 0, w, h); g.strokeStyle = '#15181d'; g.lineWidth = 14; for (let i = -10; i < 20; i++) { g.beginPath(); g.moveTo(i * 28, h); g.lineTo(i * 28 + h, 0); g.stroke(); } });
    const grM = new THREE.MeshStandardMaterial({ map: grille, metalness: 0.7, roughness: 0.4 });
    const tri = (w, h, flip) => { const t = new THREE.Shape(); if (flip) { t.moveTo(0, 0); t.lineTo(w, 0); t.lineTo(0, h); } else { t.moveTo(0, 0); t.lineTo(w, h); t.lineTo(0, h); } t.closePath();
      const g = new THREE.ShapeGeometry(t); const uv = g.attributes.uv, p = g.attributes.position; for (let i = 0; i < p.count; i++) uv.setXY(i, p.getX(i) / w, p.getY(i) / h); return g; };
    add(new THREE.Mesh(tri(mm(95), mm(70), false), grM), -CX + mm(8), PLATE + mm(8), ZB + 0.004);
    G.vent = add(new THREE.Mesh(tri(mm(85), mm(70), true), grM.clone()), -CX + mm(8), CY0 + mm(4), ZB + 0.004);
    box(mm(40), mm(34), mm(10), new THREE.MeshStandardMaterial({ color: 0x1a1c20, metalness: 0.5, roughness: 0.3 }), 0, PLATE + mm(45), ZB + mm(10));
    const duct = new THREE.Mesh(new THREE.TorusGeometry(mm(60), mm(13), 12, 40, Math.PI * 0.75), M.inner); duct.rotation.set(0, 0, Math.PI * 0.1);
    add(duct, mm(40), PLATE + mm(10), cz - mm(20));

    // shelf + parts
    const rod = new THREE.MeshStandardMaterial({ color: 0xd0d3d8, metalness: 0.9, roughness: 0.25 });
    for (const z of [ZB + mm(25), ZF - mm(25)]) { const r = new THREE.Mesh(new THREE.CylinderGeometry(mm(3), mm(3), 2 * CX, 10), rod); r.rotation.z = Math.PI / 2; add(r, 0, mm(265), z); }
    box(2 * CX - mm(10), mm(3), cd - mm(30), new THREE.MeshStandardMaterial({ color: 0xd0d3d8, metalness: 0.9, roughness: 0.25, transparent: true, opacity: 0.6 }), 0, mm(263), cz);
    const sh = new THREE.Shape(), n = 14, ro = mm(58), ri = mm(47);
    for (let i = 0; i < n * 2; i++) { const a = (i / (n * 2)) * Math.PI * 2, r = i % 2 ? ri : ro, a2 = a + 0.08; if (i === 0) sh.moveTo(Math.cos(a) * r, Math.sin(a) * r); else sh.lineTo(Math.cos(a) * r, Math.sin(a) * r); sh.lineTo(Math.cos(a2) * r, Math.sin(a2) * r); }
    const hole = new THREE.Path(); hole.absarc(0, 0, mm(18), 0, Math.PI * 2, true); sh.holes.push(hole);
    M.part = new THREE.MeshStandardMaterial({ color: 0x7684ad, metalness: 0.1, roughness: 0.42, emissive: 0 });
    parts.gear = new THREE.Mesh(new THREE.ExtrudeGeometry(sh, { depth: mm(16), bevelEnabled: true, bevelSize: mm(1.5), bevelThickness: mm(1.5), bevelSegments: 2 }), M.part);
    parts.gear.rotation.x = -Math.PI / 2; add(parts.gear, -mm(55), mm(267), cz);
    parts.knot = add(new THREE.Mesh(new THREE.TorusKnotGeometry(mm(26), mm(8), 120, 14), M.part), mm(85), mm(306), cz);
    add(new THREE.Mesh(new THREE.CylinderGeometry(mm(9), mm(9), mm(26), 16), new THREE.MeshStandardMaterial({ color: 0x3aa0d8, metalness: 0.5, roughness: 0.3, emissive: 0x0a3a5a })), CX - mm(25), CY0 + mm(14), ZB + mm(20));

    // ---------- door (hinge on the left, swings toward the viewer), logo top-left
    const dw = inW, dh = DOOR1 - STRIP1 - mm(3), dt = mm(24);
    G.door = add(new THREE.Group(), -W / 2 + ST, bc, D / 2);
    const doorTex = canvasTex(512, 480, (g, w, h) => {
      brushed(g, w, h, '#d8dbdf', '#b0b4ba');
      const k = 0.21; mark(g, 44, 52, k, '#f7f8fa', 13); wordmark(g, 64, 54, 36, '#f7f8fa');
    });
    M.doorFront = new THREE.MeshStandardMaterial({ map: doorTex, metalness: 0.78, roughness: 0.34, envMapIntensity: 1.5, transparent: true });
    M.doorEdge = M.silver.clone(); M.doorEdge.transparent = true;
    const db = new THREE.Mesh(new THREE.BoxGeometry(dw, dh, dt), [M.doorEdge, M.doorEdge, M.doorEdge, M.doorEdge, M.doorFront, M.doorEdge]); db.position.set(dw / 2, 0, -dt / 2); G.door.add(db);
    const dIn = new THREE.Mesh(new THREE.PlaneGeometry(dw - mm(50), dh - mm(50)), M.pDoor); dIn.rotation.y = Math.PI; dIn.position.set(dw / 2, 0, -dt - 0.002); G.door.add(dIn);

    // ---------- particles
    const mkPts = (N, size) => { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(N * 3), 3)); g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(N * 3), 3));
      const p = new THREE.Points(g, new THREE.PointsMaterial({ size, vertexColors: true, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, map: radialTex([[0, '#fff'], [0.4, 'rgba(255,255,255,.6)'], [1, 'rgba(255,255,255,0)']]) }));
      p.frustumCulled = false; G.m.add(p); return p; };
    let s = 11; const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
    parts.n2 = mkPts(150, mm(12)); parts.n2.seed = Array.from({ length: 150 }, () => ({ sp: 0.12 + rnd() * 0.2, ph: rnd(), dx: rnd(), dz: rnd() }));
    parts.air = mkPts(110, mm(11)); parts.air.seed = Array.from({ length: 110 }, () => ({ ph: rnd(), j: [(rnd() - 0.5) * mm(30), (rnd() - 0.5) * mm(30), (rnd() - 0.5) * mm(30)] }));
    G.air = new THREE.CatmullRomCurve3([new THREE.Vector3(-CX + mm(45), CY0 + mm(40), ZB + mm(20)), new THREE.Vector3(-mm(60), mm(210), cz), new THREE.Vector3(mm(40), mm(330), cz), new THREE.Vector3(CX - mm(50), PLATE + mm(40), ZB + mm(20))]);

    // ---------- lights (neutral)
    scene.add(new THREE.HemisphereLight(0xffffff, 0x2a2a2e, 0.25));
    const key = new THREE.DirectionalLight(0xffffff, 1.0); key.position.set(2.5, 4, 4); scene.add(key);
    const rim = new THREE.DirectionalLight(0xdfe6ff, 0.7); rim.position.set(-4, 2, -3); scene.add(rim);
    G.pl = new THREE.PointLight(0xa66bff, 0, 1.6, 1.6); G.pl.position.set(0, mm(265), cz); scene.add(G.pl);
    G.plHeat = new THREE.PointLight(0xff7a33, 0, 1.0, 1.8); G.plHeat.position.set(0, PLATE + mm(35), cz); scene.add(G.plHeat);
    G.plShow = new THREE.SpotLight(0xffffff, 0, 3, 0.5, 0.6, 1.5); G.plShow.position.set(0.4, 1.6, 1.6); G.plShow.target.position.set(-mm(20), mm(270), cz); scene.add(G.plShow, G.plShow.target);

    // ---------- ground
    G.floor = new THREE.Mesh(new THREE.CircleGeometry(6, 64), new THREE.MeshStandardMaterial({ color: 0x0b0f19, metalness: 0.15, roughness: 0.8 }));
    G.floor.rotation.x = -Math.PI / 2; scene.add(G.floor);
    const shadow = new THREE.Mesh(new THREE.PlaneGeometry(1.8, 1.8), new THREE.MeshBasicMaterial({ map: radialTex([[0, 'rgba(0,0,0,.85)'], [0.55, 'rgba(0,0,0,.45)'], [1, 'rgba(0,0,0,0)']]), transparent: true, depthWrite: false }));
    shadow.rotation.x = -Math.PI / 2; shadow.position.y = 0.002; G.m.add(shadow);
    M.glow = new THREE.MeshBasicMaterial({ map: radialTex([[0, 'rgba(255,255,255,.55)'], [0.3, 'rgba(255,255,255,.16)'], [1, 'rgba(255,255,255,0)']]), color: 0x2f7bff, opacity: 0.45, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false });
    G.glow = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 2.6), M.glow); G.glow.rotation.x = -Math.PI / 2; G.glow.position.set(0, 0.006, 0.3); G.m.add(G.glow);

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
    const e = s.cam ? 1 : clamp((T - 4.2) / 2.6), ee = e * e * (3 - 2 * e);
    G.m.position.y = lerp(-0.35, 0, ee); G.m.rotation.y = lerp(-0.9, 0, ee); G.m.scale.setScalar(lerp(0.92, 1, ee));
    // camera (film keyframes, or a fixed compare view)
    let z = 0;
    if (s.cam) {
      cam.fov = s.cam.fov || 20; cam.position.set(...s.cam.pos); cam.lookAt(new THREE.Vector3(...s.cam.at)); cam.clearViewOffset(); cam.updateProjectionMatrix();
      scene.background = new THREE.Color(s.bg || '#ffffff'); scene.fog = null; G.floor.visible = false; G.glow.visible = false;
    } else {
      const az = P(KF.az) * Math.PI / 180, r = P(KF.r), hh = P(KF.h), ty = P(KF.ty); z = P(ZOOM);
      const bob = Math.sin(T * 0.5) * 0.03 * (1 - z);
      const orb = new THREE.Vector3(Math.sin(az) * r, hh + bob, Math.cos(az) * r), at = new THREE.Vector3(0, ty, 0);
      const sp = screenPose();
      cam.fov = 31; cam.position.copy(orb.lerp(sp.pos, z)); cam.lookAt(at.lerp(sp.at, z));
      cam.setViewOffset(1920, 1080, P(KF.shift) * (1 - z), 42 * z, 1920, 1080); cam.updateProjectionMatrix();
    }

    // door + x-ray
    G.door.rotation.y = -s.door * 1.9;
    const xr = s.xray;
    M.doorFront.opacity = lerp(1, 0.1, xr); M.doorEdge.opacity = lerp(1, 0.16, xr); M.doorFront.depthWrite = xr < 0.5;

    // LED panels
    const lit = Math.max(s.uv, s.bl), c405 = new THREE.Color(0xa66bff), c450 = new THREE.Color(0x4aa3ff), cc = s.bl > s.uv ? c450 : c405;
    for (const k of ['pBack', 'pL', 'pDoor', 'pR']) {
      const on = (s.bl > s.uv && k !== 'pDoor') ? 0 : lit;
      M[k].emissive.copy(cc); M[k].emissiveIntensity = on * 2.6;
      M[k].color.setRGB(lerp(0.70, 0.32, on), lerp(0.72, 0.26, on), lerp(0.75, 0.66, on));
    }
    G.pl.color.copy(cc); G.pl.intensity = lit * 0.9;
    G.plHeat.intensity = s.heat * 0.45;
    M.coil.emissiveIntensity = s.heat * 1.5; M.coil.color.setRGB(lerp(0.29, 1, s.heat), lerp(0.23, 0.45, s.heat), lerp(0.21, 0.2, s.heat));
    G.plShow.intensity = s.show * 0.8;
    const scol = new THREE.Color(s.ledCol); M.led.color.copy(scol).multiplyScalar(1.4); M.glow.color.copy(scol);
    // parts
    M.part.color.setRGB(lerp(0.30, 0.55, s.cure), lerp(0.36, 0.52, s.cure), lerp(0.55, 0.68, s.cure));
    M.part.emissive.copy(cc).multiplyScalar(0.12 * lit);
    parts.gear.rotation.z = T * 0.5; parts.knot.rotation.set(T * 0.4, T * 0.7, 0);
    G.blades.rotation.z = -s.fan * Math.PI / 180;
    G.vent.material.color.setScalar(lerp(1, 1.6, s.dmp));
    // nitrogen + air
    const n2 = parts.n2, na = n2.geometry.attributes.position, nc = n2.geometry.attributes.color;
    n2.seed.forEach((p, i) => { const u = (T * p.sp + p.ph) % 1, f = Math.sin(u * Math.PI) * s.n2;
      na.setXYZ(i, lerp(CX - mm(25), -CX + 2 * CX * p.dx, u), CY0 + mm(20) + u * mm(240), lerp(ZB + mm(20), ZB + (ZF - ZB) * p.dz, u)); nc.setXYZ(i, 0.3 * f, 0.85 * f, f); });
    na.needsUpdate = nc.needsUpdate = true;
    const ar = parts.air, aa = ar.geometry.attributes.position, ac = ar.geometry.attributes.color, a = Math.max(s.aW, s.aC), cw = s.aC > s.aW ? [0.3, 0.8, 1] : [1, 0.62, 0.28];
    ar.seed.forEach((p, i) => { const u = (T * 0.3 + p.ph) % 1, pt = G.air.getPoint(u), f = Math.sin(u * Math.PI) * a; aa.setXYZ(i, pt.x + p.j[0], pt.y + p.j[1], pt.z + p.j[2]); ac.setXYZ(i, cw[0] * f, cw[1] * f, cw[2] * f); });
    aa.needsUpdate = ac.needsUpdate = true;

    drawScreen(s);
    bloom.strength = s.cam ? 0.15 : (0.35 + lit * 0.3 + s.heat * 0.08) * (1 - 0.7 * z);
    comp.render();
  }

  window.M3D = { init, render, dims: { H: mm(665), W, D } };
})();
