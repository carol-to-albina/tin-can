// "Powers of ten" finale: bots -> people -> buildings, every level joined by its own
// tin-can string, then the buildings shrink into one city light on the real Earth (space.tsx).
// Each level is drawn on its own 1920x1080 canvas; level j sits inside level j+1 at
// offset A[j+1] and scale S[j+1].
import React from "react";
import { AbsoluteFill, Img, interpolate, interpolateColors, staticFile } from "remotion";
import { ramp } from "./lib";
import { Space, SPACE, StepCaption } from "./space";

type P = [number, number];

// ---------- shared drawing bits ----------

const STRING = "#8d6e44";

// Tin can: open end ("mouth") at (x, y), body runs along `angle` towards the string.
export const Can: React.FC<{ x: number; y: number; angle: number; len: number; dia: number }> = ({ x, y, angle, len, dia }) => {
  const sw = Math.max(dia * 0.035, 0.6);
  return (
    <g transform={`translate(${x} ${y}) rotate(${angle})`}>
      <rect x={0} y={-dia / 2} width={len} height={dia} fill="url(#canBody)" stroke="#1d1d1d" strokeWidth={sw} />
      {[0.14, 0.26, 0.38, 0.5, 0.62, 0.74, 0.86].map((r) => (
        <line key={r} x1={len * r} x2={len * r} y1={-dia / 2 + sw} y2={dia / 2 - sw} stroke="#8e8e8e" strokeWidth={sw * 0.8} />
      ))}
      <ellipse cx={len} cy={0} rx={dia * 0.13} ry={dia / 2} fill="#e6e6e6" stroke="#1d1d1d" strokeWidth={sw} />
      <circle cx={len} cy={0} r={dia * 0.05} fill="#1d1d1d" />
      <ellipse cx={0} cy={0} rx={dia * 0.16} ry={dia / 2} fill="#9c9c9c" stroke="#1d1d1d" strokeWidth={sw} />
    </g>
  );
};
const canEnd = (x: number, y: number, angle: number, len: number): P => [
  x + len * Math.cos((angle * Math.PI) / 180),
  y + len * Math.sin((angle * Math.PI) / 180),
];

const bez = (p0: P, c: P, p1: P, u: number): P => [
  (1 - u) * (1 - u) * p0[0] + 2 * (1 - u) * u * c[0] + u * u * p1[0],
  (1 - u) * (1 - u) * p0[1] + 2 * (1 - u) * u * c[1] + u * u * p1[1],
];

// String between two points with a signal pulse bouncing along it.
export const Line: React.FC<{ a: P; b: P; sag: number; w: number; t: number; period?: number; glow?: boolean; control?: P }> = ({
  a,
  b,
  sag,
  w,
  t,
  period = 1.3,
  glow,
  control,
}) => {
  const c: P = control ?? [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + sag];
  const leg = (t / period) % 2;
  const u = leg < 1 ? leg : 2 - leg;
  const [px, py] = bez(a, c, b, 0.06 + 0.88 * u);
  const ring = glow ? "#e9ddff" : "#8c8c8c";
  return (
    <g>
      <path d={`M${a[0]} ${a[1]} Q${c[0]} ${c[1]} ${b[0]} ${b[1]}`} fill="none" stroke={STRING} strokeWidth={w} strokeLinecap="round" />
      {glow && <circle cx={px} cy={py} r={w * 7} fill="#a78bfa" opacity={0.35} />}
      <circle cx={px} cy={py} r={w * 1.6} fill={glow ? "#ffffff" : "#6f6f6f"} />
      <circle cx={px} cy={py} r={w * 3.6} fill="none" stroke={ring} strokeWidth={w * 0.55} />
      <circle cx={px} cy={py} r={w * 6} fill="none" stroke={ring} strokeWidth={w * 0.45} opacity={0.6} />
    </g>
  );
};

// Round black bot from the TinCan GIF. face = 1 looks right, -1 looks left.
export const BlobBot: React.FC<{ x: number; y: number; r: number; face: 1 | -1 }> = ({ x, y, r, face }) => (
  <g>
    <circle cx={x} cy={y} r={r} fill="#0b0b0b" />
    {[
      [0.16, -0.4],
      [0.56, -0.5],
    ].map(([dx, dy], i) => (
      <rect
        key={i}
        x={x + face * dx * r - r * 0.085}
        y={y + dy * r - r * 0.16}
        width={r * 0.17}
        height={r * 0.32}
        rx={r * 0.085}
        fill="#fff"
        transform={`rotate(${face * 18} ${x + face * dx * r} ${y + dy * r})`}
      />
    ))}
  </g>
);

export const Defs = () => (
  <defs>
    <linearGradient id="canBody" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stopColor="#f4f4f4" />
      <stop offset="0.55" stopColor="#d2d2d2" />
      <stop offset="1" stopColor="#a9a9a9" />
    </linearGradient>
  </defs>
);

// ---------- level 0: two bots ----------

export const Level0: React.FC<{ t: number }> = ({ t }) => {
  const L = { x: 380, y: 560, r: 112 };
  const R = { x: 1540, y: 560, r: 112 };
  const mouthL: P = [L.x + L.r * 0.9, L.y];
  const mouthR: P = [R.x - R.r * 0.9, R.y];
  return (
    <svg width={1920} height={1080} viewBox="0 0 1920 1080" style={{ overflow: "visible" }}>
      <Defs />
      <Line a={canEnd(...mouthL, 0, 104)} b={canEnd(...mouthR, 180, 104)} sag={46} w={4} t={t} />
      <BlobBot {...L} face={1} />
      <BlobBot {...R} face={-1} />
      <Can x={mouthL[0]} y={mouthL[1]} angle={0} len={104} dia={84} />
      <Can x={mouthR[0]} y={mouthR[1]} angle={180} len={104} dia={84} />
    </svg>
  );
};

// ---------- level 1: Carol & Albina ----------

type Look = { skin: string; skinShade: string; top: string; topShade: string; legs: string; hair: string; shoe: string; long?: boolean };

// Standing figure, three-quarter view, holding a tin can to the mouth. Feet on y = 958.
// Lit warm from the front-left (the sunset), with soft shadow on the far side.
const Person: React.FC<{ id: string; x: number; face: 1 | -1; look: Look }> = ({ id, x, face: f, look: k }) => {
  const X = (dx: number) => x + f * dx;
  const g = (name: string) => `url(#${id}-${name})`;
  return (
    <g>
      <defs>
        <linearGradient id={`${id}-top`} x1={f > 0 ? 0 : 1} x2={f > 0 ? 1 : 0} y1="0" y2="0">
          <stop offset="0" stopColor={k.topShade} />
          <stop offset="0.55" stopColor={k.top} />
          <stop offset="1" stopColor={k.top} />
        </linearGradient>
        <linearGradient id={`${id}-legs`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={k.legs} />
          <stop offset="1" stopColor="#1c2230" />
        </linearGradient>
        <radialGradient id={`${id}-skin`} cx={f > 0 ? 0.62 : 0.38} cy="0.4" r="0.7">
          <stop offset="0" stopColor={k.skin} />
          <stop offset="1" stopColor={k.skinShade} />
        </radialGradient>
        <linearGradient id={`${id}-hair`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={k.hair} />
          <stop offset="1" stopColor="#0d0907" />
        </linearGradient>
      </defs>
      {/* contact shadow */}
      <ellipse cx={x} cy={962} rx={118} ry={13} fill="#000" opacity={0.28} />
      {/* legs: tapered trousers with a crease, far leg darker */}
      <path d={`M${X(-46)} 640 L${X(-6)} 640 L${X(-14)} 930 L${X(-44)} 930 Z`} fill={g("legs")} opacity={0.85} />
      <path d={`M${X(2)} 640 L${X(48)} 640 L${X(40)} 930 L${X(10)} 930 Z`} fill={g("legs")} />
      <path d={`M${X(24)} 660 L${X(25)} 928`} stroke="#000" strokeOpacity={0.18} strokeWidth={2} />
      {/* shoes */}
      {[-30, 24].map((dx, i) => (
        <g key={i}>
          <path d={`M${X(dx - 20)} 928 Q${X(dx - 22)} 954 ${X(dx - 12)} 956 L${X(dx + 40)} 956 Q${X(dx + 46)} 944 ${X(dx + 24)} 932 Z`} fill={k.shoe} />
          <rect x={Math.min(X(dx - 14), X(dx + 44))} y={952} width={58} height={7} rx={3} fill="#f1f1ee" />
        </g>
      ))}
      {/* back arm */}
      <path d={`M${X(-66)} 392 Q${X(-86)} 500 ${X(-84)} 596`} stroke={k.topShade} strokeWidth={36} strokeLinecap="round" fill="none" />
      <ellipse cx={X(-84)} cy={612} rx={17} ry={21} fill={k.skinShade} />
      {k.long && <path d={`M${x - 66} 252 Q${x - 88} 420 ${X(-44)} 468 L${X(30)} 468 Q${x + 76} 420 ${x + 64} 252 Z`} fill={g("hair")} />}
      {/* torso: jacket with collar, zip and hem */}
      <path
        d={`M${x - 92} 404 Q${x - 94} 356 ${x - 46} 350 L${x + 46} 350 Q${x + 94} 356 ${x + 92} 404 L${x + 80} 656 Q${x} 668 ${x - 80} 656 Z`}
        fill={g("top")}
      />
      <path d={`M${X(-30)} 352 L${X(6)} 408 L${X(40)} 352`} fill="none" stroke="#000" strokeOpacity={0.22} strokeWidth={4} />
      <path d={`M${X(6)} 408 L${X(10)} 650`} stroke="#000" strokeOpacity={0.2} strokeWidth={3} />
      <path d={`M${X(-70)} 560 Q${X(-40)} 566 ${X(-20)} 560`} stroke="#000" strokeOpacity={0.15} strokeWidth={3} fill="none" />
      {/* neck */}
      <path d={`M${x - 18} 312 L${x + 18} 312 L${x + 20} 356 L${x - 20} 356 Z`} fill={k.skinShade} />
      {/* head: jaw, ear on the far side */}
      <ellipse cx={X(-40)} cy={270} rx={11} ry={17} fill={k.skinShade} />
      <path d={`M${X(-50)} 250 Q${X(-50)} 196 ${X(6)} 194 Q${X(58)} 198 ${X(58)} 256 Q${X(58)} 300 ${X(30)} 322 Q${X(8)} 334 ${X(-18)} 322 Q${X(-50)} 300 ${X(-50)} 250 Z`} fill={g("skin")} />
      {/* hair */}
      {k.long ? (
        <path d={`M${X(-62)} 290 Q${X(-72)} 180 ${X(4)} 180 Q${X(70)} 182 ${X(64)} 250 Q${X(34)} 214 ${X(-10)} 222 Q${X(-40)} 236 ${X(-44)} 300 Z`} fill={g("hair")} />
      ) : (
        <path d={`M${X(-56)} 282 Q${X(-66)} 186 ${X(6)} 182 Q${X(66)} 184 ${X(62)} 236 Q${X(40)} 214 ${X(8)} 218 Q${X(-24)} 222 ${X(-36)} 250 L${X(-40)} 286 Z`} fill={g("hair")} />
      )}
      {/* face: brows, eyes, nose, mouth */}
      <path d={`M${X(8)} 244 Q${X(18)} 238 ${X(28)} 243`} stroke="#2a1d16" strokeWidth={4} fill="none" strokeLinecap="round" />
      <path d={`M${X(38)} 243 Q${X(46)} 239 ${X(54)} 245`} stroke="#2a1d16" strokeWidth={4} fill="none" strokeLinecap="round" />
      <ellipse cx={X(19)} cy={259} rx={6} ry={4.5} fill="#fff" />
      <ellipse cx={X(46)} cy={259} rx={5} ry={4.5} fill="#fff" />
      <circle cx={X(21)} cy={259} r={3.4} fill="#3b2a20" />
      <circle cx={X(47.5)} cy={259} r={3.1} fill="#3b2a20" />
      <path d={`M${X(40)} 262 Q${X(50)} 284 ${X(40)} 288`} stroke={k.skinShade} strokeWidth={3} fill="none" strokeLinecap="round" />
      <path d={`M${X(22)} 304 Q${X(34)} 309 ${X(44)} 303`} stroke="#9a4f45" strokeWidth={4} fill="none" strokeLinecap="round" />
      <ellipse cx={X(18)} cy={288} rx={10} ry={6} fill="#e8786a" opacity={0.18} />
      {/* front arm: shoulder -> elbow -> hand at the mouth */}
      <path d={`M${X(66)} 394 Q${X(112)} 440 ${X(122)} 470 Q${X(114)} 402 ${X(92)} 326`} stroke={g("top")} strokeWidth={36} strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <ellipse cx={X(88)} cy={314} rx={17} ry={20} fill={g("skin")} />
    </g>
  );
};

const CAROL: Look = { skin: "#e8b995", skinShade: "#b98160", top: "#3f5f86", topShade: "#243a57", legs: "#4a4f5c", hair: "#4b2e20", shoe: "#5a3a26" };
const ALBINA: Look = { skin: "#f4d6c2", skinShade: "#c99c84", top: "#8b5cf6", topShade: "#5a36b0", legs: "#2e3547", hair: "#2a1d18", shoe: "#1d1d22", long: true };

export const Level1: React.FC<{ t: number }> = ({ t }) => {
  const cl: P = [498, 290];
  const ar: P = [1422, 290];
  return (
    <svg width={1920} height={1080} viewBox="0 0 1920 1080" style={{ overflow: "visible" }}>
      <Defs />
      <Line a={canEnd(...cl, 0, 62)} b={canEnd(...ar, 180, 62)} sag={60} w={3.2} t={t + 0.4} />
      <Person id="carol" x={430} face={1} look={CAROL} />
      <Person id="albina" x={1490} face={-1} look={ALBINA} />
      <Can x={cl[0]} y={cl[1]} angle={0} len={62} dia={48} />
      <Can x={ar[0]} y={ar[1]} angle={180} len={62} dia={48} />
    </svg>
  );
};

// ---------- level 2: a Prague street at dusk ----------

// deterministic 0..1 per window, so the same windows stay lit every frame
const hash = (i: number, j: number) => {
  const s = Math.sin(i * 127.1 + j * 311.7) * 43758.5453;
  return s - Math.floor(s);
};

const LitGlass: React.FC<{ x: number; y: number; w: number; h: number; lit: boolean }> = ({ x, y, w, h, lit }) => (
  <rect x={x} y={y} width={w} height={h} fill={lit ? "url(#warm)" : "url(#dusk-glass)"} />
);

// Old-town tenement: rusticated ground floor with a lit shop, four storeys of framed windows
// with pediments and sills, cornices, a wrought-iron balcony, mansard roof with dormers.
const Tenement: React.FC = () => {
  const X0 = 60;
  const X1 = 650;
  const cols = [120, 232, 344, 456, 566];
  const floors = [296, 424, 552, 680];
  return (
    <g>
      {/* mansard roof, dormers, chimneys */}
      <rect x={X0 + 60} y={116} width={26} height={70} fill="#6d4a3c" />
      <rect x={X1 - 120} y={104} width={26} height={82} fill="#6d4a3c" />
      <path d={`M${X0 - 6} 262 L${X0 + 40} 170 L${X1 - 40} 170 L${X1 + 6} 262 Z`} fill="#3c4250" />
      <path d={`M${X0 + 40} 170 L${X1 - 40} 170`} stroke="#5a6070" strokeWidth={6} />
      {[200, 380].map((dx) => (
        <g key={dx}>
          <path d={`M${X0 + dx} 250 L${X0 + dx} 196 L${X0 + dx + 40} 176 L${X0 + dx + 80} 196 L${X0 + dx + 80} 250 Z`} fill="#e9d3a6" />
          <rect x={X0 + dx + 18} y={202} width={44} height={46} fill={dx === 200 ? "url(#warm)" : "url(#dusk-glass)"} />
        </g>
      ))}
      {/* facade */}
      <rect x={X0} y={262} width={X1 - X0} height={945 - 262} fill="url(#ochre)" />
      <rect x={X0} y={262} width={X1 - X0} height={22} fill="#f3dfb2" />
      <rect x={X0} y={284} width={X1 - X0} height={8} fill="#000" opacity={0.12} />
      {floors.slice(1).map((y) => (
        <g key={y}>
          <rect x={X0} y={y - 22} width={X1 - X0} height={10} fill="#f0d9a8" />
          <rect x={X0} y={y - 12} width={X1 - X0} height={5} fill="#000" opacity={0.1} />
        </g>
      ))}
      {/* windows */}
      {floors.map((y, j) =>
        cols.map((x, i) => (
          <g key={`${i}-${j}`}>
            <path d={`M${x - 8} ${y - 4} L${x + 36} ${y - 20} L${x + 80} ${y - 4} Z`} fill="#f3e2bb" />
            <rect x={x - 6} y={y} width={84} height={98} fill="#f6efe0" />
            <LitGlass x={x} y={y + 6} w={72} h={86} lit={(i === 4 && j === 0) || hash(i, j) > 0.55} />
            <rect x={x + 34} y={y + 6} width={4} height={86} fill="#f6efe0" />
            <rect x={x} y={y + 38} width={72} height={4} fill="#f6efe0" />
            <rect x={x - 12} y={y + 98} width={96} height={9} fill="#e6d2a8" />
          </g>
        )),
      )}
      {/* wrought-iron balcony on the second floor */}
      <rect x={220} y={516} width={330} height={8} fill="#2b2b30" />
      <path d={Array.from({ length: 23 }, (_, i) => `M${226 + i * 14.3} 470 L${226 + i * 14.3} 516`).join(" ")} stroke="#2b2b30" strokeWidth={3} />
      <rect x={220} y={466} width={330} height={6} fill="#2b2b30" />
      {/* ground floor: rustication, lit shop, arched door */}
      <rect x={X0} y={810} width={X1 - X0} height={135} fill="#c9a86e" />
      {[832, 858, 884, 910].map((y) => (
        <rect key={y} x={X0} y={y} width={X1 - X0} height={2} fill="#000" opacity={0.12} />
      ))}
      <rect x={100} y={834} width={210} height={111} fill="url(#warm)" />
      <path d="M92 832 L318 832 L330 812 L80 812 Z" fill="#7b2d2b" />
      <path d="M392 945 L392 868 Q432 826 472 868 L472 945 Z" fill="#5a3826" />
      <path d="M402 872 Q432 842 462 872 Z" fill="url(#warm)" />
      <rect x={520} y={850} width={90} height={80} fill="url(#dusk-glass)" />
      {/* shade on the building's right flank */}
      <rect x={X1 - 40} y={262} width={40} height={683} fill="url(#flank)" />
    </g>
  );
};

// Modern apartment block: concrete floor slabs, glass balconies, floor-to-ceiling windows.
const Apartments: React.FC = () => {
  const X0 = 1280;
  const X1 = 1860;
  const slabs = Array.from({ length: 8 }, (_, j) => 200 + j * 92);
  return (
    <g>
      <rect x={X0} y={170} width={X1 - X0} height={775} fill="url(#concrete)" />
      <rect x={X0 - 10} y={160} width={X1 - X0 + 20} height={18} fill="#9aa1ab" />
      {slabs.map((y, j) => (
        <g key={y}>
          {[0, 1, 2, 3].map((i) => {
            const x = X0 + 30 + i * 140;
            return (
              <g key={i}>
                <LitGlass x={x} y={y + 8} w={112} h={72} lit={hash(i + 7, j + 3) > 0.5} />
                <rect x={x + 54} y={y + 8} width={3} height={72} fill="#5b626c" />
              </g>
            );
          })}
          <rect x={X0 - 6} y={y + 80} width={X1 - X0 + 12} height={12} fill="#b9bfc7" />
          <rect x={X0 + 20} y={y + 52} width={X1 - X0 - 40} height={28} fill="#bfe0ff" opacity={0.16} />
          <rect x={X0 + 20} y={y + 50} width={X1 - X0 - 40} height={3} fill="#e8eef5" opacity={0.7} />
        </g>
      ))}
      <rect x={X0} y={170} width={36} height={775} fill="#000" opacity={0.18} />
      <rect x={X0 + 180} y={880} width={120} height={65} fill="url(#warm)" />
    </g>
  );
};

export const Level2: React.FC<{ t: number }> = ({ t }) => {
  const cl: P = [640, 330];
  const cr: P = [1280, 300];
  return (
    <svg width={1920} height={1080} viewBox="0 0 1920 1080" style={{ overflow: "visible" }}>
      <Defs />
      <defs>
        <linearGradient id="ochre" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="#e7c486" />
          <stop offset="1" stopColor="#d4a867" />
        </linearGradient>
        <linearGradient id="flank" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="#000" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.25" />
        </linearGradient>
        <linearGradient id="concrete" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="#aeb4bd" />
          <stop offset="1" stopColor="#c9ced5" />
        </linearGradient>
        <linearGradient id="warm" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#ffe6ae" />
          <stop offset="1" stopColor="#f4a94e" />
        </linearGradient>
        <linearGradient id="dusk-glass" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#7e8fb8" />
          <stop offset="0.6" stopColor="#3c4a6b" />
          <stop offset="1" stopColor="#2a3350" />
        </linearGradient>
        <radialGradient id="lamp" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#ffe2a6" stopOpacity="0.9" />
          <stop offset="1" stopColor="#ffb04d" stopOpacity="0" />
        </radialGradient>
      </defs>
      {/* distant skyline */}
      <path d="M-600 945 L-600 700 L-420 700 L-420 640 L-300 640 L-300 720 L-120 720 L-120 610 L20 610 L20 945 Z" fill="#46506e" opacity={0.7} />
      <path d="M1880 945 L1880 640 L2000 640 L2000 560 L2120 560 L2120 680 L2300 680 L2300 600 L2520 600 L2520 945 Z" fill="#46506e" opacity={0.7} />
      <Tenement />
      <Apartments />
      {/* street: sidewalk, curb, asphalt, lamps */}
      <rect x={-600} y={945} width={3120} height={30} fill="#9da2ad" />
      <rect x={-600} y={975} width={3120} height={8} fill="#c9cdd4" />
      <rect x={-600} y={983} width={3120} height={160} fill="#3b4049" />
      {Array.from({ length: 16 }, (_, i) => (
        <rect key={i} x={-560 + i * 200} y={1056} width={110} height={8} fill="#e8e3cf" opacity={0.75} />
      ))}
      {[740, 1190].map((x) => (
        <g key={x}>
          <circle cx={x} cy={712} r={90} fill="url(#lamp)" />
          <rect x={x - 4} y={712} width={8} height={233} fill="#2b2e35" />
          <path d={`M${x - 22} 712 L${x + 22} 712 L${x + 12} 694 L${x - 12} 694 Z`} fill="#2b2e35" />
          <ellipse cx={x} cy={716} rx={14} ry={5} fill="#fff1c9" />
          <ellipse cx={x} cy={950} rx={80} ry={10} fill="#ffcf85" opacity={0.25} />
        </g>
      ))}
      <Line a={canEnd(...cl, 0, 90)} b={canEnd(...cr, 180, 90)} sag={70} w={4} t={t + 0.8} />
      <Can x={cl[0]} y={cl[1]} angle={0} len={90} dia={68} />
      <Can x={cr[0]} y={cr[1]} angle={180} len={90} dia={68} />
    </svg>
  );
};

// ---------- camera ----------

const LEVELS = [Level0, Level1, Level2];
// Level j-1 sits inside level j at: x_j = A[j] + S[j] * x_{j-1}.
// Level 3 is never drawn: it is screen space, where the middle of the buildings' string
// (960, 380) lands on the frame centre, which is where Prague sits on the 3D Earth.
const S = [1, 0.3, 0.17, 0.02];
const A: P[] = [
  [0, 0],
  [960 - 960 * 0.3, 965 - 672 * 0.3],
  [960 - 960 * 0.17, 945 - 965 * 0.17],
  [960 - 960 * 0.02, 540 - 380 * 0.02],
];

type Tf = { k: number; x: number; y: number };
const apply = (m: Tf, n: Tf): Tf => ({ k: m.k * n.k, x: m.k * n.x + m.x, y: m.k * n.y + m.y });
const up = (j: number): Tf => ({ k: S[j], x: A[j][0], y: A[j][1] }); // level j-1 -> level j
const down = (j: number): Tf => ({ k: 1 / S[j], x: -A[j][0] / S[j], y: -A[j][1] / S[j] }); // level j -> j-1

// u in [0, 3]: 0 = bots fill the frame, 3 = the buildings are a point of light.
const transforms = (u: number): Tf[] => {
  const i = Math.min(Math.floor(u), 2);
  const p = u - i;
  const s = S[i + 1];
  const f: P = [A[i + 1][0] / (1 - s), A[i + 1][1] / (1 - s)];
  const k = Math.pow(s, p);
  const out: Tf[] = [];
  out[i] = { k, x: f[0] * (1 - k), y: f[1] * (1 - k) };
  for (let j = i - 1; j >= 0; j--) out[j] = apply(out[j + 1], up(j + 1));
  for (let j = i + 1; j < LEVELS.length; j++) out[j] = apply(out[j - 1], down(j));
  return out;
};

// fade in when a level gets small enough to read, fade out when it becomes a speck
const IN: [number, number][] = [
  [99, 98],
  [2.3, 1.6],
  [2.4, 1.6],
];
const OUT: [number, number][] = [
  [0.03, 0.012],
  [0.02, 0.008],
  [0.1, 0.045],
];

export const worldU = (t: number, stages: number[]) => {
  // stages = [start, end of L0->L1, ...]; eased per stage but never fully stops
  if (t <= stages[0]) return 0;
  for (let i = 0; i < stages.length - 1; i++) {
    if (t <= stages[i + 1]) {
      const x = (t - stages[i]) / (stages[i + 1] - stages[i]);
      return i + 0.3 * x + 0.7 * x * x * (3 - 2 * x);
    }
  }
  return stages.length - 1;
};

export const World: React.FC<{ t: number; u: number }> = ({ t, u }) => {
  const tf = transforms(u);
  const bg = interpolateColors(u, [0, 2.3, 2.5], ["#ffffff", "#ffffff", "#000000"]);
  // dusk sky behind Carol, Albina and their street; it gives way to space as the street shrinks
  const dusk = ramp(u, 1.15, 1.75) * (1 - ramp(u, 2.4, 2.75));
  const sky = ramp(u, 2.55, 2.95);
  // the shrinking buildings become one warm point of light, which becomes Prague
  const dot = ramp(u, 2.45, 2.75) * (1 - ramp(t, SPACE.in + 0.2, SPACE.in + 0.5));
  return (
    <AbsoluteFill style={{ background: bg, overflow: "hidden" }}>
      {dusk > 0 && (
        <AbsoluteFill style={{ background: "linear-gradient(#1c2645 0%, #3f4a78 38%, #9a7a9a 66%, #f2a66e 88%, #ffc98a 100%)", opacity: dusk }} />
      )}
      {sky > 0 && (
        <Img
          src={staticFile("space/sky.jpg")}
          style={{
            position: "absolute",
            width: 2560,
            height: 1440,
            left: -320 - (t - 23) * 22,
            top: -180 + (t - 23) * 6,
            transform: `scale(${1.08 - (t - 23) * 0.012})`,
            opacity: sky,
          }}
        />
      )}
      {t >= SPACE.in - 0.05 && <Space t={t} />}
      {LEVELS.map((L, j) => {
        const m = tf[j];
        const o = Math.min(
          interpolate(m.k, [IN[j][1], IN[j][0]], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          interpolate(m.k, [OUT[j][1], OUT[j][0]], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        );
        if (o <= 0.001) return null;
        return (
          <div
            key={j}
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              width: 1920,
              height: 1080,
              transformOrigin: "0 0",
              transform: `translate(${m.x}px, ${m.y}px) scale(${m.k})`,
              opacity: o,
            }}
          >
            <L t={t} />
          </div>
        );
      }).reverse()}
      <StepCaption t={t} />
      {dot > 0 && (
        <div
          style={{
            position: "absolute",
            left: 960 - 60,
            top: 540 - 60,
            width: 120,
            height: 120,
            borderRadius: 120,
            background: "radial-gradient(#fff 0%, #ffd79a 18%, rgba(255,196,107,0.35) 40%, rgba(255,196,107,0) 70%)",
            opacity: dot,
          }}
        />
      )}
    </AbsoluteFill>
  );
};
