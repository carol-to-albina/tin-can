// Photoreal finale: the string leaves Carol's building as one city light on the real Earth,
// spreads city to city, then a Starship carries it to Mars: launch, orbital refueling,
// Trans-Mars injection, aerobrake-flip-land.
// Imagery (all NASA, public domain): Blue Marble NG (July), Black Marble 2016 city lights,
// Blue Marble clouds, NASA 3D Resources Mars, NASA/Goddard SVS Deep Star Maps 2020.
import React, { useEffect, useLayoutEffect, useMemo } from "react";
import { useLoader, useThree } from "@react-three/fiber";
import { ThreeCanvas } from "@remotion/three";
import { staticFile } from "remotion";
import * as THREE from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { FONT, ramp } from "./lib";

// ---------- timeline (seconds) ----------

export const SPACE = {
  in: 23.15, // Earth starts to show through the shrinking buildings
  arcs: 23.8, // first string leaves Prague
  launch: 24.9, // 1. Super Heavy + Starship lift off from Starbase
  staging: 26.6, //    hot staging; the booster heads home
  orbit: 28.0, //    Starship reaches low Earth orbit
  dock: 29.6, // 2. first tanker docks tail to tail
  undock: 31.8, //    tanks full, tanker backs away
  tmi: 33.1, // 3. Trans-Mars injection burn
  entry: 36.6, // 4. belly-first aerobraking at Mars
  flip: 37.9, //    flip ...
  land: 39.3, //    ... and burn to land upright
  end: 39.8, // end card
};

// ---------- geometry helpers ----------

type V = THREE.Vector3;
const v3 = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
const RAD = Math.PI / 180;

// Unit vector for (lat, lon) in the Earth mesh's local frame (matches SphereGeometry's UVs).
const geo = (lat: number, lon: number): V => {
  const phi = (lon + 180) * RAD;
  return v3(-Math.cos(phi) * Math.cos(lat * RAD), Math.sin(lat * RAD), Math.sin(phi) * Math.cos(lat * RAD));
};

const CITY: Record<string, [number, number]> = {
  prague: [50.08, 14.42],
  nyc: [40.71, -74.0],
  sf: [37.77, -122.42],
  starbase: [25.99, -97.16],
  saoPaulo: [-23.55, -46.63],
  lagos: [6.52, 3.38],
  nairobi: [-1.29, 36.82],
  capeTown: [-33.92, 18.42],
  mumbai: [19.08, 72.88],
  moscow: [55.76, 37.62],
  reykjavik: [64.15, -21.94],
  tokyo: [35.68, 139.69],
  singapore: [1.35, 103.82],
};
// [from, to, start offset after SPACE.arcs]
const ARCS: [string, string, number][] = [
  ["prague", "nyc", 0.0],
  ["prague", "lagos", 0.12],
  ["prague", "mumbai", 0.22],
  ["prague", "moscow", 0.3],
  ["prague", "saoPaulo", 0.4],
  ["prague", "nairobi", 0.5],
  ["prague", "starbase", 0.58],
  ["prague", "reykjavik", 0.66],
  ["nyc", "sf", 0.78],
  ["nyc", "saoPaulo", 0.86],
  ["lagos", "capeTown", 0.92],
  ["mumbai", "singapore", 0.98],
  ["mumbai", "tokyo", 1.06],
  ["nairobi", "capeTown", 1.12],
];
const ARC_DRAW = 0.5; // seconds to draw one string

const EARTH_YAW = -(90 + CITY.prague[1]) * RAD; // Prague faces +Z at t = SPACE.in
const earthYaw = (t: number) => EARTH_YAW + (t - SPACE.in) * 1.2 * RAD;
const SUN = v3(-1, 0.22, 0.1).normalize(); // Europe at dusk: Americas in daylight, Asia lit up
const MARS = v3(7.6, 1.3, -4.2);
const MARS_R = 0.72;

const toWorld = (local: V, t: number) => local.clone().applyAxisAngle(v3(0, 1, 0), earthYaw(t));

const STRING = new THREE.Color("#ffc46b");

// ---------- camera ----------

type Pose = { t: number; target: V; dir: V; dist: number; up?: V };
const PRAGUE_UP = toWorld(geo(...CITY.prague), SPACE.in);
// eased per leg but never fully stops at a key (same shape as the 2D zoom)
const legEase = (x: number) => 0.3 * x + 0.7 * x * x * (3 - 2 * x);
const Y = v3(0, 1, 0);
let POSES: Pose[] = []; // filled in once the flight path is known (below)
const cameraAt = (t: number) => {
  const k = POSES.findIndex((p) => p.t >= t);
  if (k <= 0) return POSES[k === 0 ? 0 : POSES.length - 1];
  const a = POSES[k - 1];
  const b = POSES[k];
  const e = legEase((t - a.t) / (b.t - a.t));
  const q = new THREE.Quaternion().setFromUnitVectors(a.dir, b.dir);
  const dir = a.dir.clone().applyQuaternion(new THREE.Quaternion().slerp(q, e));
  const up = (a.up ?? Y).clone().lerp(b.up ?? Y, e).normalize();
  return { t, target: a.target.clone().lerp(b.target, e), dir, dist: a.dist * Math.pow(b.dist / a.dist, e), up };
};

const Camera: React.FC<{ t: number }> = ({ t }) => {
  const camera = useThree((s) => s.camera);
  useLayoutEffect(() => {
    const c = cameraAt(t);
    camera.position.copy(c.target).addScaledVector(c.dir, c.dist);
    camera.up.copy(c.up ?? Y);
    camera.lookAt(c.target);
    camera.updateMatrixWorld();
  }, [t, camera]);
  return null;
};

// ---------- textures ----------

// useLoader suspends, and <ThreeCanvas> holds the frame (delayRender) until the image is in
const useTex = (file: string, srgb = true) => {
  const tex = useLoader(THREE.TextureLoader, staticFile(file));
  tex.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  tex.anisotropy = 8;
  return tex;
};

const glowTexture = (() => {
  let tex: THREE.Texture | null = null;
  return () => {
    if (tex) return tex;
    const c = document.createElement("canvas");
    c.width = c.height = 128;
    const g = c.getContext("2d")!;
    const r = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    r.addColorStop(0, "rgba(255,255,255,1)");
    r.addColorStop(0.18, "rgba(255,255,255,0.55)");
    r.addColorStop(0.45, "rgba(255,255,255,0.12)");
    r.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = r;
    g.fillRect(0, 0, 128, 128);
    tex = new THREE.CanvasTexture(c);
    return tex;
  };
})();

const Glow: React.FC<{ position: V; size: number; color: THREE.Color | string; opacity: number }> = ({ position, size, color, opacity }) =>
  opacity <= 0.001 ? null : (
    <sprite position={position} scale={[size, size, 1]}>
      <spriteMaterial map={glowTexture()} color={color} transparent opacity={opacity} blending={THREE.AdditiveBlending} depthWrite={false} />
    </sprite>
  );

// ---------- Earth ----------

const VERT = /* glsl */ `
varying vec2 vUv; varying vec3 vN; varying vec3 vP;
void main() {
  vUv = uv;
  vN = normalize(mat3(modelMatrix) * normal);
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vP = wp.xyz;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;

const EARTH_FRAG = /* glsl */ `
uniform sampler2D dayMap; uniform sampler2D nightMap; uniform sampler2D cloudMap;
uniform vec3 sunDir; uniform float cloudShift; uniform float fade;
varying vec2 vUv; varying vec3 vN; varying vec3 vP;
void main() {
  vec3 n = normalize(vN);
  vec3 v = normalize(cameraPosition - vP);
  float ndl = dot(n, sunDir);
  vec3 day = texture2D(dayMap, vUv).rgb;
  float cl = texture2D(cloudMap, vUv + vec2(cloudShift, 0.0)).r;
  float water = smoothstep(0.004, 0.03, day.b - day.r);
  vec3 surf = mix(day, vec3(0.92), cl * 0.92);
  float dayAmt = smoothstep(-0.10, 0.20, ndl);
  vec3 col = surf * (max(ndl, 0.0) * 1.5 + 0.004);
  vec3 h = normalize(sunDir + v);
  col += vec3(1.0, 0.9, 0.75) * pow(max(dot(n, h), 0.0), 70.0) * water * (1.0 - cl) * 0.55 * dayAmt;
  vec3 night = texture2D(nightMap, vUv).rgb;
  float lum = max(night.r, night.g);
  vec3 city = vec3(1.0, 0.72, 0.38) * smoothstep(0.03, 0.5, lum) * 3.2;
  col += (city + night * 0.12) * (1.0 - dayAmt) * (1.0 - cl * 0.7);
  float term = exp(-pow(ndl / 0.14, 2.0));
  col *= mix(vec3(1.0), vec3(1.35, 0.72, 0.5), term * 0.55);
  float fr = pow(1.0 - max(dot(n, v), 0.0), 2.4);
  col += vec3(0.25, 0.5, 1.0) * fr * smoothstep(-0.3, 0.45, ndl) * 0.9;
  gl_FragColor = vec4(col * fade, 1.0);
  #include <colorspace_fragment>
}`;

// back-face shell: soft glow hugging the limb, brightest on the sunlit side
const ATMOS_FRAG = /* glsl */ `
uniform vec3 sunDir; uniform vec3 tint; uniform float strength; uniform float edge;
varying vec2 vUv; varying vec3 vN; varying vec3 vP;
void main() {
  vec3 n = normalize(vN);
  vec3 v = normalize(cameraPosition - vP);
  float i = pow(clamp(-dot(n, v) / edge, 0.0, 1.0), 3.0);
  float lit = smoothstep(-0.35, 0.5, dot(n, sunDir));
  gl_FragColor = vec4(tint * i * (0.15 + 0.85 * lit) * strength, 1.0);
  #include <colorspace_fragment>
}`;

const Earth: React.FC<{ t: number; fade: number }> = ({ t, fade }) => {
  const day = useTex("space/earth_day.jpg");
  const night = useTex("space/earth_night.jpg");
  const clouds = useTex("space/earth_clouds.jpg", false);
  const mat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: VERT,
        fragmentShader: EARTH_FRAG,
        uniforms: {
          dayMap: { value: day },
          nightMap: { value: night },
          cloudMap: { value: clouds },
          sunDir: { value: SUN },
          cloudShift: { value: 0 },
          fade: { value: 1 },
        },
      }),
    [day, night, clouds],
  );
  mat.uniforms.cloudShift.value = (t - SPACE.in) * 0.0015;
  mat.uniforms.fade.value = fade;
  const atmos = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: VERT,
        fragmentShader: ATMOS_FRAG,
        uniforms: { sunDir: { value: SUN }, tint: { value: new THREE.Color(0.35, 0.62, 1.0) }, strength: { value: 1 }, edge: { value: 0.3 } },
        side: THREE.BackSide,
        blending: THREE.AdditiveBlending,
        transparent: true,
        depthWrite: false,
      }),
    [],
  );
  atmos.uniforms.strength.value = 0.9 * fade;
  return (
    <group>
      <mesh rotation={[0, earthYaw(t), 0]} material={mat}>
        <sphereGeometry args={[1, 160, 120]} />
      </mesh>
      <mesh material={atmos}>
        <sphereGeometry args={[1.05, 96, 72]} />
      </mesh>
    </group>
  );
};

// ---------- strings ----------

const STRING_FRAG = /* glsl */ `
uniform float progress; uniform float time; uniform vec3 color; uniform float opacity; uniform float back; uniform float amp;
varying vec2 vUv; varying vec3 vN; varying vec3 vP;
void main() {
  if (vUv.x > progress) discard;
  float head = smoothstep(progress - 0.06, progress, vUv.x) * (1.0 - step(0.999, progress));
  float leg = mod(time, 2.0);
  float p = back > 0.5 ? 1.0 - fract(time) : (leg < 1.0 ? leg : 2.0 - leg);
  float pulse = exp(-pow((vUv.x - p) / 0.035, 2.0));
  vec3 c = color * (0.55 + 2.2 * head + 2.4 * pulse * amp);
  gl_FragColor = vec4(c * opacity, 1.0);
  #include <colorspace_fragment>
}`;

const stringMaterial = () =>
  new THREE.ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: STRING_FRAG,
    uniforms: { progress: { value: 0 }, time: { value: 0 }, color: { value: STRING }, opacity: { value: 1 }, back: { value: 0 }, amp: { value: 1 } },
    blending: THREE.AdditiveBlending,
    transparent: true,
    depthWrite: false,
  });

// Great-circle arc lifted off the surface, in Earth-local coordinates.
const arcCurve = (a: V, b: V) => {
  const angle = a.angleTo(b);
  const lift = 0.04 + 0.22 * (angle / Math.PI);
  const q = new THREE.Quaternion();
  const pts = Array.from({ length: 49 }, (_, i) => {
    const s = i / 48;
    const qs = q.clone().setFromUnitVectors(a, b);
    const p = a.clone().applyQuaternion(new THREE.Quaternion().slerp(qs, s));
    return p.multiplyScalar(1.004 + lift * Math.sin(Math.PI * s));
  });
  return new THREE.CatmullRomCurve3(pts);
};

const Arc: React.FC<{ from: string; to: string; start: number; t: number; dim: number }> = ({ from, to, start, t, dim }) => {
  const { geom, mat, end } = useMemo(() => {
    const a = geo(...CITY[from]);
    const b = geo(...CITY[to]);
    const curve = arcCurve(a, b);
    return { geom: new THREE.TubeGeometry(curve, 96, 0.003, 6, false), mat: stringMaterial(), end: b.multiplyScalar(1.006) };
  }, [from, to]);
  const p = ramp(t, start, start + ARC_DRAW);
  if (p <= 0) return null;
  mat.uniforms.progress.value = p;
  mat.uniforms.time.value = (t - start) / 1.4 + start;
  mat.uniforms.opacity.value = dim;
  const hit = ramp(t, start + ARC_DRAW - 0.05, start + ARC_DRAW + 0.1);
  const flash = hit * (1 - ramp(t, start + ARC_DRAW + 0.1, start + ARC_DRAW + 0.7));
  return (
    <>
      <mesh geometry={geom} material={mat} />
      <Glow position={end} size={0.07 + 0.22 * flash} color={STRING} opacity={(0.6 * hit + 0.6 * flash) * dim} />
    </>
  );
};

// ---------- Starship ----------

// Unit-length Starship pointing +Y, engines at y = 0. Stainless body, black heat-shield tiles
// on the belly (-Z half), four flaps, six Raptors.
const Starship: React.FC<{ env: THREE.Texture | null; burn: number; t: number }> = ({ env, burn, t }) => {
  const parts = useMemo(() => {
    const steel = new THREE.MeshStandardMaterial({ color: "#d2d5da", metalness: 0.9, roughness: 0.3, envMapIntensity: 1.3 });
    const tiles = new THREE.MeshStandardMaterial({ color: "#16171a", metalness: 0.1, roughness: 0.85 });
    const raptor = new THREE.MeshStandardMaterial({ color: "#3a3b3f", metalness: 0.8, roughness: 0.45, side: THREE.DoubleSide });
    const R = 0.09;
    const noseProfile = Array.from({ length: 24 }, (_, i) => {
      const s = i / 23;
      return new THREE.Vector2(R * Math.pow(Math.max(1 - Math.pow(s, 2.3), 0), 0.62), 0.62 + 0.38 * s);
    });
    const plume = new THREE.ShaderMaterial({
      vertexShader: /* glsl */ `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: /* glsl */ `
        uniform float burn; uniform float flicker; varying vec2 vUv;
        void main() {
          float along = vUv.y;                // 1 at the nozzle, 0 at the tail
          float core = pow(along, 2.2);
          float edge = 1.0 - abs(fract(vUv.x * 2.0) - 0.5) * 2.0;
          vec3 c = mix(vec3(0.35, 0.55, 1.0), vec3(1.0, 0.85, 0.6), core);
          gl_FragColor = vec4(c * core * (0.4 + 0.6 * edge) * burn * flicker * 1.6, 1.0);
          #include <colorspace_fragment>
        }`,
      uniforms: { burn: { value: 0 }, flicker: { value: 1 } },
      blending: THREE.AdditiveBlending,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    return { steel, tiles, raptor, R, noseProfile, plume };
  }, []);
  const { steel, tiles, raptor, R, noseProfile, plume } = parts;
  steel.envMap = env;
  plume.uniforms.burn.value = burn;
  plume.uniforms.flicker.value = 0.85 + 0.15 * Math.sin(t * 91) * Math.sin(t * 37);
  const flap = (y: number, h: number, w: number, side: 1 | -1) => (
    <mesh position={[side * (R + w / 2 - 0.004), y, -0.02]} material={tiles}>
      <boxGeometry args={[w, h, 0.012]} />
    </mesh>
  );
  const raptors = [0, 1, 2, 3, 4, 5].map((i) => {
    const inner = i < 3;
    const a = (i * 120 + (inner ? 0 : 60)) * RAD;
    const r = inner ? 0.028 : 0.062;
    return (
      <mesh key={i} position={[Math.cos(a) * r, -0.018, Math.sin(a) * r]} material={raptor}>
        <cylinderGeometry args={[0.009, inner ? 0.018 : 0.024, 0.04, 20, 1, true]} />
      </mesh>
    );
  });
  return (
    <group>
      <mesh position={[0, 0.31, 0]} material={steel}>
        <cylinderGeometry args={[R, R, 0.62, 48]} />
      </mesh>
      <mesh position={[0, 0.31, 0]} material={tiles}>
        <cylinderGeometry args={[R * 1.004, R * 1.004, 0.62, 48, 1, true, Math.PI / 2, Math.PI]} />
      </mesh>
      <mesh material={steel}>
        <latheGeometry args={[noseProfile, 48]} />
      </mesh>
      <mesh material={tiles} scale={[1.006, 1, 1.006]}>
        <latheGeometry args={[noseProfile, 48, Math.PI / 2, Math.PI]} />
      </mesh>
      {flap(0.8, 0.12, 0.05, 1)}
      {flap(0.8, 0.12, 0.05, -1)}
      {flap(0.1, 0.17, 0.075, 1)}
      {flap(0.1, 0.17, 0.075, -1)}
      <mesh position={[0, 0.001, 0]} rotation={[Math.PI / 2, 0, 0]} material={raptor}>
        <circleGeometry args={[R, 48]} />
      </mesh>
      {raptors}
      {burn > 0.01 && (
        <mesh position={[0, -0.36, 0]} material={plume}>
          <cylinderGeometry args={[0.07, 0.3, 0.64, 32, 1, true]} />
        </mesh>
      )}
    </group>
  );
};

// Soft space-like reflection environment for the steel: black sky, blue Earth-glow below, the Sun.
const useSpaceEnv = () => {
  const gl = useThree((s) => s.gl);
  return useMemo(() => {
    const scene = new THREE.Scene();
    const sky = new THREE.Mesh(
      new THREE.SphereGeometry(10, 32, 16),
      new THREE.ShaderMaterial({
        side: THREE.BackSide,
        uniforms: { sun: { value: SUN } },
        vertexShader: /* glsl */ `varying vec3 vD; void main(){ vD = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
        fragmentShader: /* glsl */ `
          uniform vec3 sun; varying vec3 vD;
          void main() {
            vec3 d = normalize(vD);
            vec3 c = vec3(0.02, 0.025, 0.035) + vec3(0.12, 0.22, 0.4) * smoothstep(0.1, -0.7, d.y);
            c += vec3(1.0, 0.95, 0.88) * pow(max(dot(d, sun), 0.0), 60.0) * 14.0;
            c += vec3(0.5, 0.45, 0.4) * pow(max(dot(d, sun), 0.0), 4.0) * 0.5;
            gl_FragColor = vec4(c, 1.0);
          }`,
      }),
    );
    scene.add(sky);
    const pmrem = new THREE.PMREMGenerator(gl);
    const rt = pmrem.fromScene(scene, 0.02);
    pmrem.dispose();
    return rt.texture;
  }, [gl]);
};

// Super Heavy booster, unit = one Starship length. Engines at y = 0, hot-staging ring on top.
const BOOSTER_LEN = 1.47;
const Booster: React.FC<{ env: THREE.Texture | null; burn: number; t: number }> = ({ env, burn, t }) => {
  const m = useMemo(() => {
    const steel = new THREE.MeshStandardMaterial({ color: "#cfd2d7", metalness: 0.9, roughness: 0.34, envMapIntensity: 1.3 });
    const dark = new THREE.MeshStandardMaterial({ color: "#2a2b2f", metalness: 0.5, roughness: 0.6 });
    const plume = new THREE.ShaderMaterial({
      vertexShader: /* glsl */ `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: /* glsl */ `
        uniform float burn; uniform float flicker; varying vec2 vUv;
        void main() {
          float core = pow(vUv.y, 1.8);
          vec3 c = mix(vec3(1.0, 0.45, 0.15), vec3(1.0, 0.9, 0.7), core);
          gl_FragColor = vec4(c * core * burn * flicker * 1.5, 1.0);
          #include <colorspace_fragment>
        }`,
      uniforms: { burn: { value: 0 }, flicker: { value: 1 } },
      blending: THREE.AdditiveBlending,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    return { steel, dark, plume };
  }, []);
  m.steel.envMap = env;
  m.plume.uniforms.burn.value = burn;
  m.plume.uniforms.flicker.value = 0.85 + 0.15 * Math.sin(t * 83) * Math.sin(t * 29);
  const R = 0.09;
  return (
    <group>
      <mesh position={[0, 0.71, 0]} material={m.steel}>
        <cylinderGeometry args={[R, R, 1.42, 48]} />
      </mesh>
      <mesh position={[0, 1.445, 0]} material={m.dark}>
        <cylinderGeometry args={[R * 0.98, R * 0.98, 0.05, 48]} />
      </mesh>
      {[0, 1, 2, 3].map((i) => {
        const a = (i * 90 + 45) * RAD;
        return (
          <mesh key={i} position={[Math.cos(a) * (R + 0.03), 1.34, Math.sin(a) * (R + 0.03)]} rotation={[0, -a, 0]} material={m.dark}>
            <boxGeometry args={[0.06, 0.07, 0.008]} />
          </mesh>
        );
      })}
      <mesh position={[0, -0.01, 0]} material={m.dark}>
        <cylinderGeometry args={[R * 0.96, R * 0.9, 0.03, 48]} />
      </mesh>
      {burn > 0.01 && (
        <mesh position={[0, -0.5, 0]} material={m.plume}>
          <cylinderGeometry args={[0.1, 0.34, 0.95, 32, 1, true]} />
        </mesh>
      )}
    </group>
  );
};

// ---------- the flight: Starbase -> low Earth orbit -> refuel -> Trans-Mars injection -> Mars ----------

const across = (u: V, v: V) => v.clone().addScaledVector(u, -v.dot(u)).normalize(); // v flattened onto the plane normal to u
// Orientation with the nose along `nose` and the black heat shield (local -Z) facing `belly`.
const basis = (nose: V, belly: V) => {
  const y = nose.clone().normalize();
  const z = across(y, belly.clone().negate());
  const x = new THREE.Vector3().crossVectors(y, z);
  return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, z));
};

const F = (() => {
  const upB = toWorld(geo(...CITY.starbase), SPACE.launch);
  const eastB = across(upB, toWorld(geo(CITY.starbase[0], CITY.starbase[1] + 1), SPACE.launch).sub(upB));
  const sideB = new THREE.Vector3().crossVectors(eastB, upB);
  const stageAt = upB.clone().addScaledVector(eastB, 0.22).normalize().multiplyScalar(1.12);
  const uO = upB.clone().addScaledVector(eastB, 0.75).normalize();
  const orbit = uO.clone().multiplyScalar(1.16);
  const tanO = across(uO, eastB);
  const s = Math.sign(new THREE.Vector3().crossVectors(tanO, uO).dot(SUN)) || 1;
  const sideO = new THREE.Vector3().crossVectors(tanO, uO).multiplyScalar(s); // across the orbit, towards the Sun
  const ascent = new THREE.CubicBezierCurve3(upB.clone(), upB.clone().multiplyScalar(1.07), stageAt.clone().addScaledVector(eastB, -0.06), stageAt.clone());
  const dirS = ascent.getTangentAt(1);
  const toOrbit = new THREE.CubicBezierCurve3(stageAt.clone(), stageAt.clone().addScaledVector(dirS, 0.08), orbit.clone().addScaledVector(tanO, -0.12), orbit.clone());
  const boostback = new THREE.CubicBezierCurve3(stageAt.clone(), stageAt.clone().addScaledVector(upB, 0.03), upB.clone().multiplyScalar(1.06), upB.clone());
  const site = v3(-1, 0.55, 0.75).normalize();
  const land = MARS.clone().addScaledVector(site, MARS_R);
  const entryDir = v3(-0.35, 1, 0.35).normalize();
  const entry = MARS.clone().addScaledVector(entryDir, MARS_R * 1.9);
  const above = MARS.clone().addScaledVector(site, MARS_R * 1.4);
  const aero = new THREE.QuadraticBezierCurve3(entry, MARS.clone().addScaledVector(entryDir.clone().add(site).normalize(), MARS_R * 1.02), above);
  const tmi = new THREE.CubicBezierCurve3(orbit.clone(), orbit.clone().addScaledVector(tanO, 2.2), entry.clone().addScaledVector(entryDir, 2.2).add(v3(-1.2, 0, 0.6)), entry.clone());
  return { upB, eastB, sideB, stageAt, uO, orbit, tanO, sideO, ascent, toOrbit, boostback, site, land, entry, above, aero, tmi };
})();

// side-on to the ascent, from the sunlit side, a little above the horizon
const LAUNCH_DIR = F.sideB.clone().multiplyScalar(Math.sign(F.sideB.dot(SUN)) || 1).addScaledVector(F.upB, 0.3).normalize();
const ORBIT_DIR = F.uO.clone().multiplyScalar(0.34).add(F.sideO).addScaledVector(F.tanO, 0.25).normalize();
POSES = [
  { t: SPACE.in - 0.2, target: v3(0, 0, 0), dir: PRAGUE_UP.clone(), dist: 1.3 },
  { t: SPACE.in + 0.35, target: v3(0, 0, 0), dir: PRAGUE_UP.clone(), dist: 1.55 },
  { t: 24.6, target: v3(-0.15, 0.1, 0), dir: v3(-0.3, 0.52, 0.8).normalize(), dist: 4.3 },
  { t: 25.5, target: F.upB.clone().multiplyScalar(1.05), dir: LAUNCH_DIR, dist: 1.25, up: F.upB },
  { t: 26.5, target: F.upB.clone().multiplyScalar(1.09).addScaledVector(F.eastB, 0.05), dir: LAUNCH_DIR, dist: 1.35, up: F.upB },
  { t: 27.7, target: F.orbit.clone(), dir: F.uO.clone().multiplyScalar(0.6).add(F.sideO).normalize(), dist: 1.0, up: F.uO },
  { t: SPACE.dock - 0.7, target: F.orbit.clone().addScaledVector(F.tanO, -0.07), dir: F.uO.clone().multiplyScalar(0.3).add(F.sideO).normalize(), dist: 0.52, up: F.uO },
  { t: SPACE.tmi - 0.4, target: F.orbit.clone().addScaledVector(F.tanO, -0.06), dir: ORBIT_DIR, dist: 0.6, up: F.uO },
  // watch the burn start, then back away along the same side so the camera stays clear of Earth
  { t: SPACE.tmi + 0.5, target: F.orbit.clone().addScaledVector(F.tanO, 0.1), dir: ORBIT_DIR, dist: 1.0, up: F.uO },
  { t: SPACE.tmi + 1.3, target: F.orbit.clone().addScaledVector(F.tanO, 0.6), dir: ORBIT_DIR, dist: 3.4, up: F.uO },
  { t: 35.2, target: v3(2.4, 0.45, -1.3), dir: v3(0.05, 0.26, 1).normalize(), dist: 11.0 },
  { t: SPACE.entry - 0.1, target: MARS.clone().addScaledVector(F.site, 0.35), dir: F.site.clone().multiplyScalar(0.5).add(v3(0.15, 0.3, 1)).normalize(), dist: 4.6 },
  { t: SPACE.land, target: MARS.clone().addScaledVector(F.site, 0.5), dir: F.site.clone().multiplyScalar(0.5).add(v3(0.25, 0.2, 1)).normalize(), dist: 3.6 },
  { t: 41, target: MARS.clone().addScaledVector(F.site, 0.5), dir: F.site.clone().multiplyScalar(0.5).add(v3(0.3, 0.2, 1)).normalize(), dist: 3.9 },
];
const camPos = (t: number) => {
  const c = cameraAt(t);
  return c.target.clone().addScaledVector(c.dir, c.dist);
};

type Craft = { pos: V; q: THREE.Quaternion; burn: number; size: number };
const TANKER_SIZE = 0.072;
const STACK_SIZE = 0.055;

// Where the Mars-bound ship is at time t. pos is the engine end of the ship.
const shipAt = (t: number): Craft => {
  const L = SPACE;
  const screen = (k: number, p: V) => k * camPos(t).distanceTo(p);
  if (t < L.staging) {
    const x = Math.max(0, (t - L.launch) / (L.staging - L.launch));
    const p = 0.3 * x + 0.7 * x * x;
    const base = F.ascent.getPointAt(p);
    const nose = F.ascent.getTangentAt(Math.max(p, 0.001));
    const size = STACK_SIZE;
    return { pos: base.clone().addScaledVector(nose, BOOSTER_LEN * size), q: basis(nose, F.sideB), burn: 0, size };
  }
  if (t < L.orbit) {
    const x = (t - L.staging) / (L.orbit - L.staging);
    const p = legEase(x);
    const pos = F.toOrbit.getPointAt(p);
    const nose = F.toOrbit.getTangentAt(Math.min(p, 0.999));
    const size = STACK_SIZE + (TANKER_SIZE - STACK_SIZE) * ramp(t, L.orbit - 0.6, L.orbit);
    const q = basis(nose, F.sideB).slerp(basis(F.tanO, F.uO.clone().negate()), ramp(t, L.orbit - 0.8, L.orbit));
    return { pos: pos.clone().addScaledVector(nose, 0.001), q, burn: 1 - ramp(t, L.orbit - 0.25, L.orbit), size };
  }
  if (t < L.tmi) {
    const pos = F.orbit.clone().addScaledVector(F.tanO, 0.004 * (t - L.orbit));
    return { pos, q: basis(F.tanO, F.uO.clone().negate()), burn: 0, size: TANKER_SIZE };
  }
  if (t < L.entry) {
    const x = (t - L.tmi) / (L.entry - L.tmi);
    const p = x < 0.2 ? 0.1 * (x / 0.2) ** 2 : 0.1 + 0.9 * legEase((x - 0.2) / 0.8);
    const start = F.orbit.clone().addScaledVector(F.tanO, 0.004 * (L.tmi - L.orbit));
    const pos = F.tmi.getPointAt(p).add(start.clone().sub(F.orbit).multiplyScalar(1 - p));
    const nose = F.tmi.getTangentAt(Math.max(p, 0.001));
    const size = TANKER_SIZE * (1 - ramp(t, L.tmi + 0.3, L.tmi + 1.4)) + screen(0.05, pos) * ramp(t, L.tmi + 0.3, L.tmi + 1.4);
    const q = basis(F.tanO, F.uO.clone().negate()).slerp(basis(nose, F.sideO), ramp(t, L.tmi + 0.2, L.tmi + 0.9));
    return { pos, q, burn: Math.max(1 - ramp(t, L.tmi + 1.2, L.tmi + 1.6) * 0.85, 0), size };
  }
  const size0 = (p: V) => screen(0.065, p) * (1 - 0.25 * ramp(t, L.flip, L.land));
  if (t < L.flip) {
    const x = (t - L.entry) / (L.flip - L.entry);
    const p = 1 - (1 - x) ** 2;
    const pos = F.aero.getPointAt(p);
    const vel = F.aero.getTangentAt(Math.min(p, 0.999));
    const radial = pos.clone().sub(MARS).normalize();
    return { pos, q: basis(across(vel, radial), vel), burn: 0, size: size0(pos) };
  }
  // flip, then burn down to the pad
  const velEnd = F.aero.getTangentAt(0.999);
  const bellyFirst = basis(across(velEnd, F.site), velEnd);
  const upright = basis(F.site, velEnd);
  const q = bellyFirst.slerp(upright, ramp(t, L.flip, L.flip + 0.55));
  const d = ramp(t, L.flip + 0.15, L.land, (x) => 1 - (1 - x) ** 2.4);
  const pos = F.above.clone().lerp(F.land, d);
  return { pos, q, burn: t < L.land ? ramp(t, L.flip + 0.3, L.flip + 0.45) : 0, size: size0(pos) };
};

const Crafts: React.FC<{ t: number; env: THREE.Texture | null }> = ({ t, env }) => {
  const L = SPACE;
  if (t < L.launch - 0.4) return null;
  const ship = shipAt(t);
  const pop = ramp(t, L.launch - 0.4, L.launch - 0.1);
  const nozzle = (c: Craft, k = 0.08) => c.pos.clone().add(v3(0, -1, 0).applyQuaternion(c.q).multiplyScalar(c.size * k));
  const out: React.ReactNode[] = [];

  // Super Heavy: under the ship until hot staging, then back towards Starbase
  if (t < L.staging) {
    const baseQ = ship.q;
    const bpos = ship.pos.clone().addScaledVector(v3(0, 1, 0).applyQuaternion(baseQ), -BOOSTER_LEN * ship.size);
    const burn = t >= L.launch ? 1 : 0;
    out.push(
      <group key="booster" position={bpos} quaternion={baseQ} scale={ship.size * pop}>
        <Booster env={env} burn={burn} t={t} />
      </group>,
      <Glow key="bglow" position={bpos} size={ship.size * 1.6} color="#ffb070" opacity={0.9 * burn} />,
    );
  } else if (t < L.orbit + 0.3) {
    const x = ramp(t, L.staging, L.orbit + 0.2);
    const bpos = F.boostback.getPointAt(x);
    const size = STACK_SIZE;
    const flipQ = basis(F.upB, F.sideB);
    const q = shipAt(L.staging - 0.001).q.slerp(flipQ, ramp(t, L.staging + 0.1, L.staging + 0.6));
    const burn = Math.max(ramp(t, L.staging + 0.35, L.staging + 0.5) * (1 - ramp(t, L.staging + 0.9, L.staging + 1.1)), 0);
    out.push(
      <group key="booster" position={bpos} quaternion={q} scale={size * (1 - ramp(t, L.orbit, L.orbit + 0.3))}>
        <Booster env={env} burn={burn} t={t} />
      </group>,
    );
  }
  // hot-staging flash
  const hs = ramp(t, L.staging - 0.05, L.staging + 0.05) * (1 - ramp(t, L.staging + 0.1, L.staging + 0.5));
  if (hs > 0) out.push(<Glow key="hs" position={F.stageAt} size={ship.size * 2.2} color="#ffc38a" opacity={hs} />);

  // tankers: one docks tail to tail and transfers propellant, the next waits its turn
  if (t > L.orbit - 0.3 && t < L.tmi + 0.9) {
    const s = TANKER_SIZE;
    const docked = ship.pos.clone().addScaledVector(F.tanO, -0.015 * s);
    const tq = basis(F.tanO.clone().negate(), F.uO.clone().negate());
    const approach = F.tanO.clone().multiplyScalar(-1.7).addScaledVector(F.uO, -0.3).addScaledVector(F.sideO, -0.5).multiplyScalar(s);
    const leave = F.tanO.clone().multiplyScalar(-1.4).addScaledVector(F.uO, -0.9).addScaledVector(F.sideO, -0.4).multiplyScalar(s);
    const inE = ramp(t, L.orbit, L.dock, (x) => 1 - (1 - x) ** 3);
    const outE = ramp(t, L.undock, L.undock + 1.3, (x) => x * x);
    const p1 = docked.clone().addScaledVector(approach, 1 - inE).addScaledVector(leave, outE);
    const waiting = ship.pos.clone().add(F.tanO.clone().multiplyScalar(-4.2).addScaledVector(F.uO, -0.15).addScaledVector(F.sideO, -1.8).multiplyScalar(s));
    const next = ship.pos.clone().add(F.tanO.clone().multiplyScalar(-2.4).addScaledVector(F.sideO, -0.8).multiplyScalar(s));
    const p2 = waiting.lerp(next, ramp(t, L.undock + 0.4, L.tmi + 0.6));
    const flow = ramp(t, L.dock, L.dock + 0.2) * (1 - ramp(t, L.undock - 0.2, L.undock));
    out.push(
      <group key="t1" position={p1} quaternion={tq} scale={s}>
        <Starship env={env} burn={0} t={t} />
      </group>,
      <group key="t2" position={p2} quaternion={tq} scale={s}>
        <Starship env={env} burn={0} t={t} />
      </group>,
      <Glow key="flow" position={docked} size={s * (0.35 + 0.08 * Math.sin(t * 12))} color="#bfe3ff" opacity={0.8 * flow} />,
      <Glow key="dockflash" position={docked} size={s * 0.9} color="#ffffff" opacity={ramp(t, L.dock - 0.05, L.dock) * (1 - ramp(t, L.dock, L.dock + 0.35))} />,
    );
  }

  // aerobraking plasma on the belly
  const plasma = ramp(t, L.entry + 0.05, L.entry + 0.35) * (1 - ramp(t, L.flip - 0.35, L.flip + 0.05));
  if (plasma > 0) {
    const vel = F.aero.getTangentAt(Math.min(Math.max(1 - (1 - (t - L.entry) / (L.flip - L.entry)) ** 2, 0), 0.999));
    const mid = ship.pos.clone().add(v3(0, 0.5, 0).applyQuaternion(ship.q).multiplyScalar(ship.size)).addScaledVector(vel, ship.size * 0.14);
    const flick = 0.85 + 0.15 * Math.sin(t * 67);
    out.push(
      <Glow key="plasma" position={mid} size={ship.size * 1.5} color="#ff7a3d" opacity={plasma * flick} />,
      <Glow key="plasma2" position={mid.clone().addScaledVector(vel, ship.size * 0.1)} size={ship.size * 0.9} color="#ffd0f0" opacity={0.7 * plasma * flick} />,
    );
  }

  const shipBurnGlow = ship.burn * (t > L.staging - 0.05 ? 1 : 0);
  out.push(
    <group key="ship" position={ship.pos} quaternion={ship.q} scale={ship.size * pop}>
      <Starship env={env} burn={t > L.staging - 0.05 ? ship.burn : 0} t={t} />
    </group>,
    <Glow key="sglow" position={nozzle(ship)} size={ship.size * 0.9} color="#ffd9a8" opacity={0.85 * shipBurnGlow} />,
  );
  return <>{out}</>;
};

// The string follows the ship all the way: sampled flight path from Starbase to now, drawn
// at a constant width on screen. After landing, a reply runs back down it from Mars to Earth.
const Trail: React.FC<{ t: number }> = ({ t }) => {
  const mat = useMemo(
    () => new LineMaterial({ color: STRING.clone().multiplyScalar(1.15).getHex(), linewidth: 3.2, transparent: true, opacity: 0.95, depthWrite: false }),
    [],
  );
  mat.resolution.set(1920, 1080);
  const { line, pts } = useMemo(() => {
    if (t < SPACE.launch + 0.05) return { line: null, pts: [] as V[] };
    const end = Math.min(t, SPACE.land);
    const pts: V[] = [F.upB.clone()];
    for (let s = SPACE.launch; s < end; s += 1 / 30) pts.push(shipAt(s).pos);
    pts.push(shipAt(end).pos);
    const g = new LineGeometry();
    g.setPositions(pts.flatMap((p) => [p.x, p.y, p.z]));
    return { line: new Line2(g, mat), pts };
  }, [t, mat]);
  useEffect(() => () => line?.geometry.dispose(), [line]);
  if (!line) return null;
  const k = ramp(t, SPACE.land + 0.05, SPACE.end - 0.05, (x) => x);
  const head = pts[Math.max(0, Math.round((1 - k) * (pts.length - 1)))];
  const camera = cameraAt(t);
  const d = camera.target.clone().addScaledVector(camera.dir, camera.dist).distanceTo(head);
  return (
    <>
      <primitive object={line} />
      {k > 0 && k < 1 && <Glow position={head} size={0.05 * d} color="#fff3d6" opacity={1} />}
    </>
  );
};

const Flight: React.FC<{ t: number; env: THREE.Texture | null }> = ({ t, env }) => (
  <>
    <Trail t={t} />
    <Crafts t={t} env={env} />
  </>
);

// ---------- step captions (HTML, over the canvas) ----------

const STEPS: [number, number, string, string][] = [
  [SPACE.launch, SPACE.dock - 1.6, "Launch to orbit", "Super Heavy lifts Starship to low Earth orbit, then flies home"],
  [SPACE.dock - 1.6, SPACE.tmi, "Orbital refueling", "Tankers dock one after another and top off the tanks"],
  [SPACE.tmi, SPACE.entry, "Trans-Mars injection", "One long burn leaves Earth on a course for Mars"],
  [SPACE.entry, SPACE.end - 0.15, "Aerobrake, flip, land", "Belly-first through the air, then a flip and a burn to land upright"],
];

export const StepCaption: React.FC<{ t: number }> = ({ t }) => {
  const i = STEPS.findIndex(([a, b]) => t >= a && t < b);
  if (i < 0) return null;
  const [a, b, title, detail] = STEPS[i];
  const o = ramp(t, a, a + 0.3) * (1 - ramp(t, b - 0.25, b));
  const fuel = ramp(t, SPACE.dock, SPACE.undock - 0.2);
  return (
    <div style={{ position: "absolute", left: 96, bottom: 84, color: "#fff", fontFamily: FONT, opacity: o, transform: `translateY(${(1 - o) * 10}px)`, textShadow: "0 2px 16px rgba(0,0,0,0.7)" }}>
      <div style={{ fontSize: 24, fontWeight: 600, letterSpacing: 3, color: "#ffc46b" }}>STEP {i + 1} OF 4</div>
      <div style={{ fontSize: 56, fontWeight: 700, marginTop: 6 }}>{title}</div>
      <div style={{ fontSize: 30, fontWeight: 400, marginTop: 6, color: "rgba(255,255,255,0.85)" }}>{detail}</div>
      {i === 1 && (
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 18, fontSize: 24, color: "rgba(255,255,255,0.85)" }}>
          <span>Methane + oxygen</span>
          <div style={{ width: 320, height: 10, borderRadius: 5, background: "rgba(255,255,255,0.18)" }}>
            <div style={{ width: `${(0.18 + 0.82 * fuel) * 100}%`, height: "100%", borderRadius: 5, background: "#bfe3ff" }} />
          </div>
          <span style={{ fontVariantNumeric: "tabular-nums" }}>{Math.round((0.18 + 0.82 * fuel) * 100)}%</span>
        </div>
      )}
    </div>
  );
};

// ---------- Mars ----------

const Mars: React.FC<{ t: number }> = ({ t }) => {
  const map = useTex("space/mars.jpg");
  const atmos = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: VERT,
        fragmentShader: ATMOS_FRAG,
        uniforms: { sunDir: { value: SUN }, tint: { value: new THREE.Color(1.0, 0.55, 0.35) }, strength: { value: 0.6 }, edge: { value: 0.3 } },
        side: THREE.BackSide,
        blending: THREE.AdditiveBlending,
        transparent: true,
        depthWrite: false,
      }),
    [],
  );
  const landed = ramp(t, SPACE.land, SPACE.land + 0.2);
  const ring = ramp(t, SPACE.land, SPACE.land + 0.6);
  const site = F.land.clone().addScaledVector(F.site, 0.01);
  return (
    <group>
      <mesh position={MARS} rotation={[0.12, -1.9 + (t - 24) * 0.02, 0]}>
        <sphereGeometry args={[MARS_R, 128, 96]} />
        <meshStandardMaterial map={map} roughness={1} metalness={0} />
      </mesh>
      <mesh position={MARS} material={atmos}>
        <sphereGeometry args={[MARS_R * 1.05, 64, 48]} />
      </mesh>
      <Glow position={site} size={0.2 + 1.6 * ring} color={STRING} opacity={landed * (1 - ring) * 1.4} />
      <Glow position={site} size={0.3} color={STRING} opacity={landed} />
    </group>
  );
};

// ---------- scene ----------

const Scene: React.FC<{ t: number }> = ({ t }) => {
  const env = useSpaceEnv();
  const fade = ramp(t, SPACE.in, SPACE.in + 0.45);
  const hub = toWorld(geo(...CITY.prague), t).multiplyScalar(1.006);
  const hubGlow = ramp(t, SPACE.in, SPACE.in + 0.3);
  const marsIn = ramp(t, SPACE.tmi + 0.6, SPACE.tmi + 1.4);
  // the city strings step back while the camera follows the ship from the pad to orbit
  const dim = 1 - 0.85 * ramp(t, SPACE.launch - 0.3, SPACE.launch + 0.4) * (1 - ramp(t, SPACE.tmi + 0.3, SPACE.tmi + 1.3));
  return (
    <>
      <Camera t={t} />
      <ambientLight intensity={0.03} />
      <directionalLight position={SUN.clone().multiplyScalar(50)} intensity={3.2} />
      <Earth t={t} fade={fade} />
      <group rotation={[0, earthYaw(t), 0]}>
        {ARCS.map(([a, b, dt]) => (
          <Arc key={a + b} from={a} to={b} start={SPACE.arcs + dt} t={t} dim={dim} />
        ))}
      </group>
      <Glow position={hub} size={0.12 + 0.1 * (1 - hubGlow)} color={STRING} opacity={hubGlow * dim} />
      {marsIn > 0 && <Mars t={t} />}
      <Flight t={t} env={env} />
    </>
  );
};

export const Space: React.FC<{ t: number }> = ({ t }) => (
  <ThreeCanvas
    width={1920}
    height={1080}
    style={{ position: "absolute", inset: 0 }}
    camera={{ fov: 35, near: 0.01, far: 400, position: [0, 0, 5] }}
    gl={{ antialias: true, alpha: true, preserveDrawingBuffer: true }}
    flat
  >
    <Scene t={t} />
  </ThreeCanvas>
);
