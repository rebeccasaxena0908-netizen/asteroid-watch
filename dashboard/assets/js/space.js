// Full-screen Three.js background: stars, nebula, Earth, and this week's real close approaches.
//
// - Earth: a procedural shader planet that cross-fades to the local NASA Blue Marble texture
//   once it loads (works offline; the texture lives in assets/img/, three.js in assets/vendor/).
// - Asteroids: one rock per upcoming approach (data from the API). Orbit radius is log-scaled
//   by miss distance, size by diameter, speed by relative velocity. Not to scale.
// - Mouse/touch parallax, drag to rotate, hover for a label, click/tap to open the asteroid.
// - Performance: capped pixel ratio, pause when the tab is hidden, adaptive resolution,
//   and on-demand rendering when the user prefers reduced motion.

import * as THREE from 'three';
import { fmt1, fmtDate } from './format.js';

const TEXTURE_URL = 'assets/img/earth_bluemarble_2048.jpg';
const EARTH_R = 1.15;
const R_MIN = 1.75;          // orbit radius for the closest pass
const R_MAX = 3.4;           // orbit radius for ~200 LD
const SERIES = { non: new THREE.Color('#3987e5'), haz: new THREE.Color('#d95926') };
const SUN_DIR = new THREE.Vector3(-0.9, 0.35, 0.6).normalize();

// Deterministic randomness, so the scene looks the same on every load.
function mulberry32(seed) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const hashString = (s) => [...String(s)].reduce((h, c) => (Math.imul(h, 31) + c.charCodeAt(0)) | 0, 7);
const clamp01 = (v) => Math.min(1, Math.max(0, v));

// ---------------------------------------------------------------- shaders

const NOISE_GLSL = /* glsl */`
// 3D simplex noise (Ashima Arts / Stefan Gustavson, MIT licence)
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z); vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}
float fbm(vec3 p){ float f=0.0, a=0.5; for(int i=0;i<5;i++){ f+=a*snoise(p); p*=2.03; a*=0.5; } return f; }
`;

const EARTH_VERT = /* glsl */`
varying vec2 vUv; varying vec3 vNormalW; varying vec3 vPosW; varying vec3 vPosObj;
void main(){
  vUv = uv; vPosObj = position;
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vPosW = wp.xyz;
  vNormalW = normalize(mat3(modelMatrix) * normal);
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;

const EARTH_FRAG = /* glsl */`
uniform sampler2D uDay; uniform float uTexMix; uniform vec3 uSunDir;
varying vec2 vUv; varying vec3 vNormalW; varying vec3 vPosW; varying vec3 vPosObj;
${NOISE_GLSL}
void main(){
  vec3 n = normalize(vNormalW);
  vec3 V = normalize(cameraPosition - vPosW);
  vec3 L = normalize(uSunDir);

  // Procedural planet (base layer; also what you see if the texture can't load)
  vec3 p = normalize(vPosObj);
  float h = fbm(p * 1.7 + 3.1);
  float land = smoothstep(0.02, 0.09, h);
  vec3 ocean = mix(vec3(0.010, 0.035, 0.12), vec3(0.03, 0.12, 0.30), smoothstep(-0.45, 0.05, h));
  vec3 ground = mix(vec3(0.09, 0.22, 0.07), vec3(0.36, 0.28, 0.14), smoothstep(0.12, 0.38, h));
  vec3 proc = mix(ocean, ground, land);
  proc = mix(proc, vec3(0.82, 0.86, 0.92), smoothstep(0.80, 0.88, abs(p.y) + h * 0.08));

  // Blue Marble texture (decoded to linear by three.js)
  vec3 tex = texture2D(uDay, vUv).rgb;
  vec3 albedo = mix(proc, tex, uTexMix);
  float texWater = smoothstep(0.01, 0.06, tex.b - max(tex.r, tex.g) * 0.85);
  float water = mix(1.0 - land, texWater, uTexMix);

  // Lighting: soft terminator, ocean glint, atmosphere rim
  float ndl = dot(n, L);
  float day = smoothstep(-0.20, 0.30, ndl);
  vec3 col = albedo * (0.025 + 1.05 * max(ndl, 0.0) + 0.12 * day);
  vec3 H = normalize(L + V);
  col += vec3(0.65, 0.78, 1.0) * pow(max(dot(n, H), 0.0), 90.0) * water * day * 0.35;
  col += vec3(0.004, 0.010, 0.030) * (1.0 - day);
  float fres = pow(1.0 - max(dot(n, V), 0.0), 2.6);
  col += vec3(0.28, 0.52, 1.0) * fres * (0.08 + 0.92 * day) * 0.5;

  gl_FragColor = vec4(col, 1.0);
  #include <colorspace_fragment>
}`;

const ATMOS_VERT = /* glsl */`
varying vec3 vNormalV; varying vec3 vNormalW;
void main(){
  vNormalV = normalize(normalMatrix * normal);
  vNormalW = normalize(mat3(modelMatrix) * normal);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;
const ATMOS_FRAG = /* glsl */`
uniform vec3 uSunDir; varying vec3 vNormalV; varying vec3 vNormalW;
void main(){
  // Back faces of a slightly larger sphere: -dot is 0 at the shell's outer edge and grows toward
  // Earth's limb, so the glow is brightest at the planet and fades smoothly to nothing.
  float k = clamp(-dot(normalize(vNormalV), vec3(0.0, 0.0, 1.0)), 0.0, 1.0);
  float i = pow(smoothstep(0.0, 0.42, k), 2.2);
  float lit = 0.2 + 0.8 * smoothstep(-0.35, 0.6, dot(normalize(vNormalW), normalize(uSunDir)));
  gl_FragColor = vec4(vec3(0.32, 0.6, 1.0) * i * lit * 0.95, 1.0);
  #include <colorspace_fragment>
}`;

const POINTS_VERT = /* glsl */`
attribute float aSize; attribute float aPhase; attribute vec3 aColor;
uniform float uTime; uniform float uPixelRatio; uniform float uTwinkle; uniform float uScale;
varying vec3 vColor; varying float vBright;
void main(){
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mv;
  float tw = mix(1.0, 0.62 + 0.38 * sin(uTime * (0.5 + aPhase * 1.4) + aPhase * 6.2831), uTwinkle);
  vBright = tw; vColor = aColor;
  gl_PointSize = aSize * uPixelRatio * (uScale / -mv.z) * (0.85 + 0.3 * tw);
}`;
const POINTS_FRAG = /* glsl */`
varying vec3 vColor; varying float vBright;
void main(){
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.0, d); a *= a;
  gl_FragColor = vec4(vColor * vBright, a);
  #include <colorspace_fragment>
}`;

// ---------------------------------------------------------------- builders

function makeStars(count, rand) {
  const pos = new Float32Array(count * 3), size = new Float32Array(count), phase = new Float32Array(count), color = new Float32Array(count * 3);
  const tints = [new THREE.Color('#b9d3ff'), new THREE.Color('#ffffff'), new THREE.Color('#ffe2c4'), new THREE.Color('#d8ccff')];
  const v = new THREE.Vector3();
  for (let i = 0; i < count; i++) {
    v.set(rand() * 2 - 1, rand() * 2 - 1, rand() * 2 - 1).normalize().multiplyScalar(45 + rand() * 75);
    pos.set([v.x, v.y, v.z], i * 3);
    size[i] = 0.5 + rand() ** 3 * 2.4;
    phase[i] = rand();
    const c = tints[Math.floor(rand() * tints.length)];
    color.set([c.r, c.g, c.b], i * 3);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('aSize', new THREE.BufferAttribute(size, 1));
  g.setAttribute('aPhase', new THREE.BufferAttribute(phase, 1));
  g.setAttribute('aColor', new THREE.BufferAttribute(color, 3));
  return g;
}

function pointsMaterial(scale, twinkle) {
  return new THREE.ShaderMaterial({
    vertexShader: POINTS_VERT, fragmentShader: POINTS_FRAG,
    uniforms: { uTime: { value: 0 }, uPixelRatio: { value: 1 }, uTwinkle: { value: twinkle }, uScale: { value: scale } },
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
}

/** Nebula painted once on a canvas (soft overlapping clouds), wrapped on a huge inside-out sphere. */
function makeNebulaTexture(rand) {
  const W = 1024, H = 512;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
  ctx.globalCompositeOperation = 'lighter';
  const hues = [[120, 80, 230], [50, 150, 210], [190, 70, 170], [70, 90, 220]];
  for (let i = 0; i < 70; i++) {
    const [r, g, b] = hues[Math.floor(rand() * hues.length)];
    const x = rand() * W, y = H * (0.25 + rand() * 0.5), rad = 40 + rand() * 220, a = 0.02 + rand() * 0.06;
    for (const dx of [-W, 0, W]) {   // draw wrapped copies so the sphere seam is invisible
      const grad = ctx.createRadialGradient(x + dx, y, 0, x + dx, y, rad);
      grad.addColorStop(0, `rgba(${r},${g},${b},${a})`);
      grad.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = grad;
      ctx.fillRect(x + dx - rad, y - rad, rad * 2, rad * 2);
    }
  }
  // The browser dithers each faint gradient; stretched across the sky that dither shows up as a
  // grid. One blur pass removes it. Draw the image tiled left/right first so the seam stays invisible.
  const out = document.createElement('canvas');
  out.width = W; out.height = H;
  const octx = out.getContext('2d');
  octx.filter = 'blur(6px)';
  for (const dx of [-W, 0, W]) octx.drawImage(c, dx, 0);
  const tex = new THREE.CanvasTexture(out);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function makeGlowTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(128, 128, 0, 128, 128, 128);
  g.addColorStop(0, 'rgba(90,150,255,0.55)');
  g.addColorStop(0.35, 'rgba(70,110,230,0.18)');
  g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 256, 256);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** Lumpy asteroid: an icosphere with its vertices pushed in/out by smooth pseudo-noise. */
function makeRockGeometry() {
  const g = new THREE.IcosahedronGeometry(1, 2);
  const p = g.attributes.position;
  const v = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i).normalize();
    const n = Math.sin(v.x * 3.1 + 1.3) * Math.sin(v.y * 2.7 + 0.4) * Math.sin(v.z * 3.7 + 2.1);
    const k = 0.82 + 0.22 * n + 0.06 * Math.sin(v.x * 9 + v.z * 7);
    p.setXYZ(i, v.x * k, v.y * k * 0.85, v.z * k);
  }
  g.computeVertexNormals();
  return g;
}

function orbitRadius(ld) {
  return R_MIN + (R_MAX - R_MIN) * clamp01(Math.log10(1 + Math.max(ld, 0)) / Math.log10(201));
}

// ---------------------------------------------------------------- scene

export function startSpace({ canvas, stage, label, textColumn, reducedMotion, onReady }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setClearColor(0x03050c, 1);
  const small = Math.min(window.innerWidth, window.innerHeight) < 700;
  let pixelRatio = Math.min(window.devicePixelRatio || 1, small ? 1.5 : 1.75);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 500);
  camera.position.set(0, 0.25, 8);

  const rand = mulberry32(20261012);

  // Background layers (weaker parallax = feels far away)
  const sky = new THREE.Group();
  scene.add(sky);
  const starMat = pointsMaterial(70, reducedMotion ? 0 : 1);
  const stars = new THREE.Points(makeStars(small ? 1400 : 2600, rand), starMat);
  sky.add(stars);
  const nebula = new THREE.Mesh(new THREE.SphereGeometry(160, 48, 24),
    new THREE.MeshBasicMaterial({ map: makeNebulaTexture(rand), side: THREE.BackSide, depthWrite: false }));
  nebula.renderOrder = -10;   // opaque backdrop, drawn before everything else
  nebula.rotation.set(0.35, 0, 0.2);
  sky.add(nebula);

  // Foreground system: Earth, Moon, asteroids
  const world = new THREE.Group();   // parallax tilt
  const system = new THREE.Group();  // drag rotation + layout position
  world.add(system);
  scene.add(world);

  const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: makeGlowTexture(), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  halo.scale.setScalar(EARTH_R * 6.5);
  halo.position.z = -1.2;
  system.add(halo);

  const sunLight = new THREE.DirectionalLight(0xffffff, 2.4);
  sunLight.position.copy(SUN_DIR).multiplyScalar(10);
  scene.add(sunLight, new THREE.AmbientLight(0x6c7cb8, 0.32));

  const placeholder = new THREE.DataTexture(new Uint8Array([10, 30, 80, 255]), 1, 1);
  placeholder.needsUpdate = true;
  const earthUniforms = { uDay: { value: placeholder }, uTexMix: { value: 0 }, uSunDir: { value: SUN_DIR } };
  const tilt = new THREE.Group();
  tilt.rotation.z = THREE.MathUtils.degToRad(23.4);
  system.add(tilt);
  const earth = new THREE.Mesh(new THREE.SphereGeometry(EARTH_R, 128, 96),
    new THREE.ShaderMaterial({ vertexShader: EARTH_VERT, fragmentShader: EARTH_FRAG, uniforms: earthUniforms }));
  earth.rotation.y = -2.93;   // start with India facing the camera
  tilt.add(earth);
  const atmosphere = new THREE.Mesh(new THREE.SphereGeometry(EARTH_R * 1.09, 128, 96),
    new THREE.ShaderMaterial({ vertexShader: ATMOS_VERT, fragmentShader: ATMOS_FRAG, uniforms: { uSunDir: { value: SUN_DIR } },
      side: THREE.BackSide, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false }));
  system.add(atmosphere);

  let texFade = null;
  new THREE.TextureLoader().load(TEXTURE_URL, (tex) => {
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
    earthUniforms.uDay.value = tex;
    texFade = reducedMotion ? 1 : 0;
    if (reducedMotion) earthUniforms.uTexMix.value = 1;
    requestRender();
  }, undefined, () => console.warn('Earth texture not loaded; using the procedural planet.'));

  // Moon at 1 lunar distance (on the same log scale as the asteroids)
  const moonPivot = new THREE.Group();
  moonPivot.rotation.x = THREE.MathUtils.degToRad(5.1);
  const moon = new THREE.Mesh(new THREE.SphereGeometry(0.11, 32, 16), new THREE.MeshStandardMaterial({ color: 0xbfc3cc, roughness: 1 }));
  moon.position.x = orbitRadius(1);
  moonPivot.add(moon, orbitLine(orbitRadius(1), new THREE.Color('#ffffff'), 0.07));
  system.add(moonPivot);

  function orbitLine(r, color, opacity) {
    const pts = [];
    for (let i = 0; i <= 128; i++) {
      const t = (i / 128) * Math.PI * 2;
      pts.push(new THREE.Vector3(Math.cos(t) * r, 0, Math.sin(t) * r));
    }
    return new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color, transparent: true, opacity, depthWrite: false }));
  }

  // ---------------------------------------------------------- asteroids (set from data)
  const rockGeo = makeRockGeometry();
  const rockMats = {
    non: new THREE.MeshStandardMaterial({ color: 0x8e95a6, roughness: 0.92, metalness: 0.05, flatShading: true }),
    haz: new THREE.MeshStandardMaterial({ color: 0xa8653f, roughness: 0.85, metalness: 0.05, flatShading: true, emissive: 0xd95926, emissiveIntensity: 0.4 }),
  };
  const glowMat = pointsMaterial(8, 0);   // ~aSize CSS px at the system's distance
  let rocks = [];          // per-asteroid state
  let meshes = {};         // InstancedMesh per type
  let glow = null;         // halo points
  const orbitGroup = new THREE.Group();
  system.add(orbitGroup);

  function setAsteroids(list) {
    for (const m of Object.values(meshes)) { system.remove(m); m.dispose(); }
    orbitGroup.clear();
    if (glow) { system.remove(glow); glow.geometry.dispose(); }
    meshes = {};

    rocks = list.map((a) => {
      const r = mulberry32(hashString(a.neo_id));
      const radius = orbitRadius(a.miss_distance_lunar ?? 50);
      const logD = Math.log10(Math.max(a.est_diameter_max_m || 50, 5));
      const haz = !!a.is_potentially_hazardous;
      const orbitQ = new THREE.Quaternion().setFromEuler(new THREE.Euler((r() - 0.5) * 0.8, r() * Math.PI * 2, (r() - 0.5) * 0.3));
      const line = orbitLine(radius, haz ? SERIES.haz : SERIES.non, haz ? 0.22 : 0.11);
      line.quaternion.copy(orbitQ);
      orbitGroup.add(line);
      return {
        data: a, haz, radius, orbitQ, line,
        baseOpacity: line.material.opacity,
        angle: r() * Math.PI * 2,
        speed: (0.05 + (a.relative_velocity_kps || 10) * 0.012) / radius,
        size: 0.035 + 0.075 * clamp01((logD - 1) / (Math.log10(3000) - 1)),
        spinAxis: new THREE.Vector3(r() - 0.5, r() - 0.5, r() - 0.5).normalize(),
        spin: 0.3 + r() * 1.2,
        tumble: r() * Math.PI * 2,
        squash: new THREE.Vector3(1, 0.75 + r() * 0.3, 0.8 + r() * 0.35),
        local: new THREE.Vector3(),
        screen: new THREE.Vector2(-9999, -9999),
      };
    });

    for (const type of ['non', 'haz']) {
      const count = rocks.filter((k) => (type === 'haz') === k.haz).length;
      if (!count) continue;
      const mesh = new THREE.InstancedMesh(rockGeo, rockMats[type], count);
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      mesh.frustumCulled = false;
      meshes[type] = mesh;
      system.add(mesh);
    }

    const n = rocks.length;
    const g = new THREE.BufferGeometry();
    const colors = new Float32Array(n * 3), sizes = new Float32Array(n), phases = new Float32Array(n);
    rocks.forEach((k, i) => {
      const c = k.haz ? SERIES.haz : SERIES.non;
      colors.set([c.r, c.g, c.b], i * 3);
      sizes[i] = 10 + k.size * 160;
      phases[i] = 0;
    });
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 3), 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('aColor', new THREE.BufferAttribute(colors, 3));
    g.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1));
    g.setAttribute('aPhase', new THREE.BufferAttribute(phases, 1));
    glow = new THREE.Points(g, glowMat);
    glow.frustumCulled = false;
    system.add(glow);
    updateRocks(0);
    requestRender();
  }

  const tmpM = new THREE.Matrix4(), tmpQ = new THREE.Quaternion(), tmpS = new THREE.Vector3(), tmpV = new THREE.Vector3();
  function updateRocks(dt) {
    const idx = { non: 0, haz: 0 };
    const glowPos = glow?.geometry.attributes.position;
    rocks.forEach((k, i) => {
      k.angle += k.speed * dt;
      k.tumble += k.spin * dt;
      k.local.set(Math.cos(k.angle) * k.radius, 0, Math.sin(k.angle) * k.radius).applyQuaternion(k.orbitQ);
      const s = k.size * (k === hovered ? 1.6 : 1);
      tmpQ.setFromAxisAngle(k.spinAxis, k.tumble);
      tmpS.copy(k.squash).multiplyScalar(s);
      tmpM.compose(k.local, tmpQ, tmpS);
      const type = k.haz ? 'haz' : 'non';
      meshes[type].setMatrixAt(idx[type]++, tmpM);
      glowPos?.setXYZ(i, k.local.x, k.local.y, k.local.z);
    });
    for (const m of Object.values(meshes)) m.instanceMatrix.needsUpdate = true;
    if (glowPos) glowPos.needsUpdate = true;
  }

  // ---------------------------------------------------------- layout, input
  const target = { tiltX: 0, tiltY: 0 };
  const drag = { active: false, moved: 0, lastX: 0, lastY: 0, yaw: 0, pitch: 0.12, vYaw: 0 };
  let scrollF = 0;
  let layoutX = 0, layoutY = 0, layoutS = 1;

  function layout() {
    const w = window.innerWidth, h = window.innerHeight;
    renderer.setPixelRatio(pixelRatio);
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    starMat.uniforms.uPixelRatio.value = pixelRatio;
    glowMat.uniforms.uPixelRatio.value = pixelRatio;
    const aspect = w / h;
    if (aspect > 1.05) {
      // Keep every orbit to the right of the hero text column. Work in world units on the plane
      // of the system (distance D from the camera). The furthest a circular orbit of radius r
      // can project sideways, perspective included, is r / sqrt(1 - (r/D)^2).
      const D = camera.position.z;
      const pxToWorld = (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * D) / h;
      const worldX = (px) => (px - w / 2) * pxToWorld;
      const textRight = (textColumn ? textColumn.getBoundingClientRect().right : w * 0.5) + 28;
      const reach = (s) => { const r = R_MAX * s; return r / Math.sqrt(1 - (r / D) ** 2) + 0.15 * s; };
      const maxX = (s) => worldX(w - 12) - EARTH_R * s * 1.15;   // whole Earth stays on screen
      let s = 0.9;
      while (s > 0.45 && worldX(textRight) + reach(s) > maxX(s)) s -= 0.02;
      layoutS = s;
      layoutX = Math.min(Math.max(worldX(textRight) + reach(s), worldX((textRight + w) / 2)), maxX(s));
      layoutY = -0.05;
    } else {
      layoutX = 0; layoutY = 1.5; layoutS = 0.72;   // phones: Earth above the text
    }
    requestRender();
  }

  window.addEventListener('pointermove', (e) => {
    if (reducedMotion) return;
    target.tiltY = (e.clientX / window.innerWidth - 0.5) * 0.22;
    target.tiltX = (e.clientY / window.innerHeight - 0.5) * 0.14;
  }, { passive: true });
  window.addEventListener('scroll', () => {
    scrollF = Math.min(1.6, window.scrollY / window.innerHeight);
    requestRender();
  }, { passive: true });
  window.addEventListener('resize', layout);
  if (textColumn && 'ResizeObserver' in window) new ResizeObserver(() => layout()).observe(textColumn);

  let hovered = null;
  let onPick = null;
  const projected = new THREE.Vector3();

  function nearestRock(clientX, clientY, maxPx) {
    let best = null, bestD = maxPx;
    for (const k of rocks) {
      const d = Math.hypot(k.screen.x - clientX, k.screen.y - clientY);
      if (d < bestD) { best = k; bestD = d; }
    }
    return best;
  }

  function setHover(k, x, y) {
    if (hovered && hovered !== k) hovered.line.material.opacity = hovered.baseOpacity;
    hovered = k;
    if (k) {
      k.line.material.opacity = 0.75;
      const a = k.data;
      label.replaceChildren(
        Object.assign(document.createElement('strong'), { textContent: a.name }),
        Object.assign(document.createElement('span'), { className: 'muted',
          textContent: ` · ${fmt1(a.miss_distance_lunar)} LD · ${fmtDate(a.approach_date)}${k.haz ? ' · hazardous' : ''}` }));
      label.style.left = `${x}px`;
      label.style.top = `${y}px`;
      label.classList.add('show');
      stage.style.cursor = 'pointer';
    } else {
      label.classList.remove('show');
      stage.style.cursor = '';
    }
    requestRender();
  }

  stage.addEventListener('pointerdown', (e) => {
    drag.active = true; drag.moved = 0; drag.lastX = e.clientX; drag.lastY = e.clientY;
    stage.setPointerCapture(e.pointerId);
    stage.classList.add('dragging');
  });
  stage.addEventListener('pointermove', (e) => {
    if (drag.active) {
      const dx = e.clientX - drag.lastX, dy = e.clientY - drag.lastY;
      drag.lastX = e.clientX; drag.lastY = e.clientY;
      drag.moved += Math.abs(dx) + Math.abs(dy);
      drag.vYaw = dx * 0.006;
      drag.yaw += dx * 0.006;
      drag.pitch = THREE.MathUtils.clamp(drag.pitch + dy * 0.004, -0.6, 0.7);
      requestRender();
      if (drag.moved > 6) { setHover(null); return; }
    }
    if (e.pointerType === 'mouse') setHover(nearestRock(e.clientX, e.clientY, 22), e.clientX, e.clientY);
  });
  const endDrag = (e) => {
    if (!drag.active) return;
    drag.active = false;
    stage.classList.remove('dragging');
    if (drag.moved < 6) {   // a click / tap, not a drag
      const k = nearestRock(e.clientX, e.clientY, e.pointerType === 'mouse' ? 22 : 34);
      if (k && onPick) onPick(k.data.neo_id);
    }
  };
  stage.addEventListener('pointerup', endDrag);
  stage.addEventListener('pointercancel', () => { drag.active = false; stage.classList.remove('dragging'); });
  stage.addEventListener('pointerleave', () => { if (!drag.active) setHover(null); });

  // ---------------------------------------------------------- loop
  const clock = new THREE.Clock();
  let running = false, frame = 0, needsRender = true, slowFrames = 0, firstFrame = true;

  function requestRender() {
    needsRender = true;
    if (reducedMotion && !running) { running = true; requestAnimationFrame(tick); }
  }

  function tick() {
    const dt = Math.min(clock.getDelta(), 0.05);
    const t = clock.elapsedTime;

    // Adaptive resolution: if frames are consistently slow, drop to 1x pixels.
    if (dt > 0.024) slowFrames += 1; else slowFrames = Math.max(0, slowFrames - 1);
    if (slowFrames > 90 && pixelRatio > 1) { pixelRatio = 1; slowFrames = 0; layout(); }

    const motion = reducedMotion ? 0 : 1;
    const ease = 1 - Math.exp(-dt * 3);
    world.rotation.x += (target.tiltX - world.rotation.x) * ease;
    world.rotation.y += (target.tiltY - world.rotation.y) * ease;
    sky.rotation.y = world.rotation.y * 0.25 + t * 0.004 * motion;
    sky.rotation.x = world.rotation.x * 0.25;

    if (!drag.active) { drag.yaw += drag.vYaw; drag.vYaw *= 0.94; }
    system.rotation.set(drag.pitch, drag.yaw, 0);
    // Past the hero, Earth drifts up and out of view; the starfield stays behind the content.
    system.position.set(layoutX, layoutY + scrollF * 2.6, -scrollF * 1.5);
    system.scale.setScalar(layoutS);

    earth.rotation.y += dt * 0.045 * motion;
    moonPivot.rotation.y += dt * 0.08 * motion;
    if (texFade !== null && texFade < 1) { texFade = Math.min(1, texFade + dt / 1.6); earthUniforms.uTexMix.value = texFade * texFade * (3 - 2 * texFade); }
    starMat.uniforms.uTime.value = t;
    updateRocks(dt * motion);

    // Screen positions of rocks for hover/click picking.
    scene.updateMatrixWorld();
    for (const k of rocks) {
      projected.copy(k.local).applyMatrix4(system.matrixWorld).project(camera);
      k.screen.set((projected.x * 0.5 + 0.5) * window.innerWidth, (-projected.y * 0.5 + 0.5) * window.innerHeight);
    }

    // Far down the page the scene is only a backdrop: render every other frame.
    frame += 1;
    if (needsRender || scrollF < 1.2 || frame % 2 === 0) renderer.render(scene, camera);
    needsRender = false;
    if (firstFrame) { firstFrame = false; onReady?.(); }

    const keepGoing = !reducedMotion || drag.active || Math.abs(drag.vYaw) > 1e-4 ||
      Math.abs(target.tiltX - world.rotation.x) > 1e-3 || (texFade !== null && texFade < 1);
    if (keepGoing && !document.hidden) requestAnimationFrame(tick);
    else running = false;
  }

  function start() {
    if (running) return;
    running = true;
    clock.getDelta();   // don't jump after a pause
    requestAnimationFrame(tick);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) start(); });

  layout();
  start();

  return {
    setAsteroids(list, pick) { onPick = pick; setAsteroids(list); start(); },
  };
}
