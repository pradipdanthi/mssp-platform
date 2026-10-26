/**
 * Clean Jarvis-style 3D globe (canvas projection).
 * Sphere spins; satellites orbit around it (pass in front and behind).
 */
import { useEffect, useRef } from "react";

type Props = {
  live?: boolean;
  version?: string;
};

type Vec3 = { x: number; y: number; z: number };

function rotX(p: Vec3, a: number): Vec3 {
  const c = Math.cos(a);
  const s = Math.sin(a);
  return { x: p.x, y: p.y * c - p.z * s, z: p.y * s + p.z * c };
}

function project(p: Vec3, cx: number, cy: number, scale: number) {
  // slight perspective so the sphere reads as volume
  const depth = 1 + p.z * 0.18;
  return { x: cx + p.x * scale * depth, y: cy + p.y * scale * depth, z: p.z };
}

const SATS = [
  { r: 1.38, speed: 0.55, phase: 0, tilt: 1.15, color: "#67e8f9", size: 3.2 },
  { r: 1.55, speed: -0.38, phase: 2.1, tilt: 0.95, color: "#22d3ee", size: 2.6 },
  { r: 1.72, speed: 0.28, phase: 4.0, tilt: 1.35, color: "#a5f3fc", size: 2.2 },
];

export default function TiaGlobe({ live = true, version = "v1.0" }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let running = true;
    let lastFrame = 0;
    const start = performance.now();

    const resize = () => {
      const parent = canvas.parentElement;
      const cssW = parent?.clientWidth || 280;
      const cssH = parent?.clientHeight || 280;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(cssW * dpr);
      canvas.height = Math.floor(cssH * dpr);
      canvas.style.width = `${cssW}px`;
      canvas.style.height = `${cssH}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    if (canvas.parentElement) ro.observe(canvas.parentElement);

    const draw = (now: number) => {
      if (!running) return;
      // Pause when tab hidden; ~30fps otherwise so mic STT isn't starved.
      if (document.hidden) {
        raf = requestAnimationFrame(draw);
        return;
      }
      if (now - lastFrame < 32) {
        raf = requestAnimationFrame(draw);
        return;
      }
      lastFrame = now;
      const t = (now - start) / 1000;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      const cx = w / 2;
      const cy = h / 2 - h * 0.02;
      const R = Math.min(w, h) * 0.28;
      const spin = t * 0.35;

      ctx.clearRect(0, 0, w, h);

      // Soft floor glow
      const floor = ctx.createRadialGradient(cx, h * 0.88, 4, cx, h * 0.88, w * 0.32);
      floor.addColorStop(0, "rgba(34, 211, 238, 0.22)");
      floor.addColorStop(0.55, "rgba(34, 211, 238, 0.06)");
      floor.addColorStop(1, "rgba(34, 211, 238, 0)");
      ctx.fillStyle = floor;
      ctx.beginPath();
      ctx.ellipse(cx, h * 0.88, w * 0.28, h * 0.04, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "rgba(34, 211, 238, 0.28)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.ellipse(cx, h * 0.88, w * 0.26, h * 0.035, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.beginPath();
      ctx.ellipse(cx, h * 0.88, w * 0.18, h * 0.022, 0, 0, Math.PI * 2);
      ctx.stroke();

      const drawSat = (
        s: { x: number; y: number; z: number; sat: (typeof SATS)[number] },
        front: boolean,
      ) => {
        const alpha = front ? 1 : 0.4;
        const size = s.sat.size * (front ? 1.15 : 0.8);
        const g = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, size * 4.5);
        g.addColorStop(0, `rgba(103, 232, 249, ${0.6 * alpha})`);
        g.addColorStop(1, "rgba(103, 232, 249, 0)");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(s.x, s.y, size * 4.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(s.x, s.y, size, 0, Math.PI * 2);
        ctx.globalAlpha = alpha;
        ctx.fillStyle = s.sat.color;
        ctx.fill();
        ctx.globalAlpha = 1;
      };

      const satPts = SATS.map((sat) => {
        const a = t * sat.speed + sat.phase;
        let p: Vec3 = { x: Math.cos(a) * sat.r, y: 0, z: Math.sin(a) * sat.r };
        p = rotX(p, sat.tilt);
        const q = project(p, cx, cy, R);
        return { ...q, sat };
      });

      // Orbit rings (full ellipse, under globe)
      for (const sat of SATS) {
        ctx.beginPath();
        for (let i = 0; i <= 72; i++) {
          const a = (i / 72) * Math.PI * 2;
          let p: Vec3 = { x: Math.cos(a) * sat.r, y: 0, z: Math.sin(a) * sat.r };
          p = rotX(p, sat.tilt);
          const q = project(p, cx, cy, R);
          if (i === 0) ctx.moveTo(q.x, q.y);
          else ctx.lineTo(q.x, q.y);
        }
        ctx.closePath();
        ctx.strokeStyle = "rgba(34, 211, 238, 0.2)";
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // Satellites BEHIND the globe (drawn under the opaque sphere)
      for (const s of satPts.filter((p) => p.z < 0).sort((a, b) => a.z - b.z)) {
        drawSat(s, false);
      }

      // Sphere body
      const body = ctx.createRadialGradient(
        cx - R * 0.35,
        cy - R * 0.4,
        R * 0.1,
        cx,
        cy,
        R * 1.05,
      );
      body.addColorStop(0, "#2a6a8a");
      body.addColorStop(0.35, "#12384f");
      body.addColorStop(0.72, "#071822");
      body.addColorStop(1, "#02080e");
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.fillStyle = body;
      ctx.fill();

      // Wireframe latitudes (front hemisphere)
      const latCount = 5;
      for (let i = 1; i < latCount; i++) {
        const lat = -Math.PI / 2 + (i / latCount) * Math.PI;
        const y = Math.sin(lat);
        const rr = Math.cos(lat);
        ctx.beginPath();
        let first = true;
        for (let j = 0; j <= 48; j++) {
          const lon = (j / 48) * Math.PI * 2 + spin;
          let p: Vec3 = { x: Math.cos(lon) * rr, y, z: Math.sin(lon) * rr };
          p = rotX(p, 0.18);
          if (p.z < -0.05) {
            first = true;
            continue;
          }
          const q = project(p, cx, cy, R);
          if (first) {
            ctx.moveTo(q.x, q.y);
            first = false;
          } else ctx.lineTo(q.x, q.y);
        }
        ctx.strokeStyle = i === 3 ? "rgba(103, 232, 249, 0.5)" : "rgba(103, 232, 249, 0.22)";
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // Wireframe meridians (front hemisphere)
      const merCount = 8;
      for (let i = 0; i < merCount; i++) {
        const lon0 = (i / merCount) * Math.PI * 2 + spin;
        ctx.beginPath();
        let first = true;
        for (let j = 0; j <= 32; j++) {
          const lat = -Math.PI / 2 + (j / 32) * Math.PI;
          let p: Vec3 = {
            x: Math.cos(lon0) * Math.cos(lat),
            y: Math.sin(lat),
            z: Math.sin(lon0) * Math.cos(lat),
          };
          p = rotX(p, 0.18);
          if (p.z < -0.02) {
            first = true;
            continue;
          }
          const q = project(p, cx, cy, R);
          if (first) {
            ctx.moveTo(q.x, q.y);
            first = false;
          } else ctx.lineTo(q.x, q.y);
        }
        ctx.strokeStyle = "rgba(103, 232, 249, 0.3)";
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // Terminator shade
      const shade = ctx.createLinearGradient(cx - R, cy, cx + R, cy);
      shade.addColorStop(0, "rgba(0,0,0,0)");
      shade.addColorStop(0.45, "rgba(0,0,0,0)");
      shade.addColorStop(0.7, "rgba(0,0,0,0.28)");
      shade.addColorStop(1, "rgba(0,0,0,0.62)");
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.fillStyle = shade;
      ctx.fill();

      // Specular highlight
      const shine = ctx.createRadialGradient(
        cx - R * 0.38,
        cy - R * 0.42,
        0,
        cx - R * 0.2,
        cy - R * 0.25,
        R * 0.7,
      );
      shine.addColorStop(0, "rgba(255,255,255,0.28)");
      shine.addColorStop(0.35, "rgba(165,243,252,0.1)");
      shine.addColorStop(1, "rgba(255,255,255,0)");
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.fillStyle = shine;
      ctx.fill();

      // Rim
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.strokeStyle = live ? "rgba(103, 232, 249, 0.8)" : "rgba(103, 232, 249, 0.45)";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      if (live) {
        ctx.beginPath();
        ctx.arc(cx, cy, R + 3, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(34, 211, 238, 0.28)";
        ctx.lineWidth = 6;
        ctx.stroke();
      }

      // Label
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "#22d3ee";
      ctx.font = `600 ${Math.max(16, R * 0.32)}px Orbitron, sans-serif`;
      ctx.shadowColor = "rgba(34, 211, 238, 0.7)";
      ctx.shadowBlur = 12;
      ctx.fillText("TIA", cx, cy - R * 0.12);
      ctx.shadowBlur = 0;
      ctx.fillStyle = "#b6dceb";
      ctx.font = `500 ${Math.max(9, R * 0.12)}px Inter, sans-serif`;
      ctx.fillText("AI CORE", cx, cy + R * 0.12);
      ctx.fillStyle = "#67e8f9";
      ctx.font = `${Math.max(8, R * 0.1)}px Inter, sans-serif`;
      ctx.fillText(version, cx, cy + R * 0.28);

      // Satellites IN FRONT of the globe
      for (const s of satPts.filter((p) => p.z >= 0).sort((a, b) => a.z - b.z)) {
        drawSat(s, true);
      }

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => {
      running = false;
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [live, version]);

  return (
    <div className={`tia-globe ${live ? "live" : ""}`} aria-hidden>
      <div className="tia-globe-stage">
        <canvas ref={canvasRef} className="tia-globe-canvas" />
      </div>
    </div>
  );
}
