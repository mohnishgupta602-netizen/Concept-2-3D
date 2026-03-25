import React, { Suspense, useEffect, useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, useGLTF, Stage, Html, Line } from "@react-three/drei";

import * as THREE from "three";

function inferPartTarget(name, idx, box, center, size) {
  const n = (name || "").toLowerCase();
  const corners = [
    [box.min.x, box.min.y, box.max.z],
    [box.max.x, box.min.y, box.max.z],
    [box.min.x, box.min.y, box.min.z],
    [box.max.x, box.min.y, box.min.z],
  ];

  if (n.includes("backrest") || n.includes("back")) {
    return [center.x, center.y + size.y * 0.25, box.min.z + size.z * 0.08];
  }
  if (n.includes("seat") || n.includes("cushion")) {
    return [center.x, center.y, center.z];
  }
  if (n.includes("leg") || n.includes("foot") || n.includes("wheel") || n.includes("base")) {
    return corners[idx % corners.length];
  }
  if (n.includes("armrest") || n.includes("arm")) {
    const side = idx % 2 === 0 ? -1 : 1;
    return [center.x + side * size.x * 0.42, center.y + size.y * 0.08, center.z];
  }
  if (n.includes("door") || n.includes("gate")) {
    return [center.x, center.y, box.max.z - size.z * 0.06];
  }
  if (n.includes("window")) {
    return [center.x + (idx % 2 === 0 ? -1 : 1) * size.x * 0.28, center.y + size.y * 0.28, box.max.z - size.z * 0.08];
  }
  if (n.includes("roof") || n.includes("top") || n.includes("crown")) {
    return [center.x, box.max.y - size.y * 0.05, center.z];
  }
  if (n.includes("trunk")) {
    return [center.x, center.y - size.y * 0.12, center.z];
  }
  if (n.includes("branch") || n.includes("leaf")) {
    return [center.x + (idx % 2 === 0 ? -1 : 1) * size.x * 0.25, center.y + size.y * 0.3, center.z];
  }

  // Generic distribution for unknown part names.
  const angle = (idx / 10) * Math.PI * 2;
  return [
    center.x + Math.cos(angle) * size.x * 0.22,
    center.y + ((idx % 3) - 1) * size.y * 0.16,
    center.z + Math.sin(angle) * size.z * 0.22,
  ];
}

function buildPartAnnotations(scene, partLabels) {
  if (!scene || !Array.isArray(partLabels) || partLabels.length === 0) return [];

  const box = new THREE.Box3().setFromObject(scene);
  const sizeVec = new THREE.Vector3();
  const centerVec = new THREE.Vector3();
  box.getSize(sizeVec);
  box.getCenter(centerVec);

  if (!isFinite(sizeVec.x) || !isFinite(sizeVec.y) || !isFinite(sizeVec.z)) return [];

  return partLabels.slice(0, 12).map((part, idx) => {
    const target = inferPartTarget(part?.name, idx, box, centerVec, sizeVec);
    const side = idx % 2 === 0 ? -1 : 1;
    const tier = Math.floor(idx / 2);
    const xOffset = Math.max(0.18, sizeVec.x * 0.34);
    const yOffset = Math.max(0.14, sizeVec.y * 0.18);
    const callout = [
      target[0] + side * xOffset,
      target[1] + yOffset - tier * Math.max(0.06, sizeVec.y * 0.05),
      target[2],
    ];

    return {
      serial: idx + 1,
      name: part?.name || `Part ${idx + 1}`,
      description: part?.description || "No description available",
      location: part?.location || "Unknown",
      target,
      callout,
    };
  });
}

function AIModel({ url, partLabels }) {
  const { scene } = useGLTF(url);
  const [hoveredSerial, setHoveredSerial] = useState(null);

  // Clone and normalize once per scene load.
  const clonedScene = useMemo(() => {
    const cloned = scene.clone();
    cloned.traverse((child) => {
      if (child.isMesh) {
        child.castShadow = false;
        child.receiveShadow = false;
        if (child.material) {
          child.material.side = THREE.DoubleSide;
          child.material.transparent = false;
          child.material.depthWrite = true;
          child.material.needsUpdate = true;
        }
      }
    });
    return cloned;
  }, [scene]);

  const annotations = useMemo(() => buildPartAnnotations(clonedScene, partLabels), [clonedScene, partLabels]);

  return (
    <>
      <primitive object={clonedScene} />
      {annotations.map((item) => (
        <group key={`annotation-${item.serial}-${item.name}`}>
          <Line points={[item.target, item.callout]} color="#52d4ff" lineWidth={1} transparent opacity={0.82} />
          <mesh position={item.target}>
            <sphereGeometry args={[0.022, 10, 10]} />
            <meshStandardMaterial color="#52d4ff" emissive="#52d4ff" emissiveIntensity={0.45} />
          </mesh>
          <Html position={item.callout} occlude={false} transform={false}>
            <div
              style={{
                position: "relative",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                pointerEvents: "auto",
              }}
              onMouseEnter={() => setHoveredSerial(item.serial)}
              onMouseLeave={() => setHoveredSerial(null)}
              title={`${item.serial}. ${item.name}`}
            >
              <span
                style={{
                  width: "12px",
                  height: "12px",
                  borderRadius: "50%",
                  background: "rgba(21, 169, 255, 0.95)",
                  color: "#031225",
                  border: "1px solid rgba(82, 212, 255, 0.65)",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "7px",
                  fontWeight: 700,
                  boxShadow: "0 0 5px rgba(0, 0, 0, 0.35)",
                  cursor: "default",
                }}
              >
                {item.serial}
              </span>

              {hoveredSerial === item.serial && (
                <div
                  style={{
                    position: "absolute",
                    left: "50%",
                    bottom: "15px",
                    transform: "translateX(-50%)",
                    minWidth: "140px",
                    maxWidth: "210px",
                    background: "rgba(7, 13, 22, 0.96)",
                    border: "1px solid rgba(82, 212, 255, 0.45)",
                    borderRadius: "8px",
                    padding: "7px 8px",
                    color: "#dff4ff",
                    fontSize: "11px",
                    lineHeight: 1.25,
                    boxShadow: "0 6px 16px rgba(0,0,0,0.45)",
                    whiteSpace: "normal",
                    zIndex: 1000,
                  }}
                >
                  <div style={{ fontWeight: 700, marginBottom: "3px" }}>{`${item.serial}. ${item.name}`}</div>
                  <div style={{ color: "#bfd8eb" }}>{item.description}</div>
                  <div style={{ color: "#6cd2ff", marginTop: "3px", fontSize: "10px" }}>{`Location: ${item.location}`}</div>
                </div>
              )}
            </div>
          </Html>
        </group>
      ))}
    </>
  );
}

// Simple Error Boundary to catch loader/render errors
class GLBErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.warn("Model render error:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || <mesh />;
    }
    return this.props.children;
  }
}

function SafeAIModel({ url, fallback, partLabels }) {
  const [valid, setValid] = useState(null); // null=checking, true=ok, false=bad
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function probe() {
      try {
        console.log('[ModelViewer] Probing URL:', url);
        // Try a HEAD request first to avoid downloading the whole file
        const headResp = await fetch(url, { method: 'HEAD' });
        console.log('[ModelViewer] HEAD response:', headResp.status, headResp.ok);
        if (!headResp.ok) {
          // Some servers don't support HEAD; try GET but only inspect headers
          console.log('[ModelViewer] HEAD failed, trying GET...');
          const getResp = await fetch(url, { method: 'GET' });
          console.log('[ModelViewer] GET response:', getResp.status, getResp.ok);
          if (!getResp.ok) throw new Error('Not OK');
          const ct = getResp.headers.get('Content-Type') || '';
          console.log('[ModelViewer] Content-Type:', ct);
          if (/gltf|glb|application\/octet-stream/i.test(ct)) {
            if (!cancelled) setValid(true);
            return;
          }
          throw new Error('Content-Type not GLB');
        }

        const ct = headResp.headers.get('Content-Type') || '';
        console.log('[ModelViewer] HEAD Content-Type:', ct);
        if (/gltf|glb|application\/octet-stream/i.test(ct)) {
          if (!cancelled) setValid(true);
          return;
        }
        throw new Error('Content-Type not GLB');
      } catch (e) {
        console.error('[ModelViewer] Probe failed:', e.message);
        if (!cancelled) {
          setValid(false);
          setError(e.message);
        }
      }
    }
    probe();
    return () => { cancelled = true; };
  }, [url]);

  if (valid === null) return null;
  if (valid === false) {
    console.error('[ModelViewer] Model validation failed:', error);
    return fallback || null;
  }
  return (
    <GLBErrorBoundary fallback={fallback}>
      <Suspense fallback={null}>
        <Stage environment="city" intensity={0.6}>
          <AIModel url={url} partLabels={partLabels} />
        </Stage>
        <OrbitControls autoRotate autoRotateSpeed={2} enableDamping dampingFactor={0.05} />
      </Suspense>
    </GLBErrorBoundary>
  );
}

export default function ModelViewer({ data, fallbackShapes }) {
  const hasModelUrl = data?.viewer;
  const partLabels = data?.part_labels?.parts || [];
  
  console.log('[ModelViewer] data:', data, 'fallbackShapes:', fallbackShapes, 'hasModelUrl:', hasModelUrl);

  const fallbackMesh = (
    <>
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1} />
    </>
  );

  return (
    <div className="viewer-wrapper">
      <Canvas camera={{ position: [0, 2, 5], fov: 45 }}>
        {hasModelUrl ? (
          <SafeAIModel url={data.viewer} fallback={fallbackMesh} partLabels={partLabels} />
        ) : (
          <>
            {fallbackShapes && fallbackShapes.map((shape, idx) => {
              const key = `${shape}-${idx}`;
              const color = ["#00ffcc", "#0071e3", "#ff0080", "#ffcc00"][idx % 4];
              return (
                <mesh key={key} position={[idx * 2 - (fallbackShapes.length - 1), 0, 0]}>
                  {shape === 'cube' && <boxGeometry args={[1, 1, 1]} />}
                  {shape === 'sphere' && <sphereGeometry args={[0.7, 32, 32]} />}
                  {shape === 'cylinder' && <cylinderGeometry args={[0.5, 0.5, 1.5, 32]} />}
                  {shape === 'cone' && <coneGeometry args={[0.5, 1.5, 32]} />}
                  {shape === 'tube' && <cylinderGeometry args={[0.3, 0.3, 1.5, 32]} />}
                  <meshStandardMaterial 
                    color={color} 
                    roughness={0.2} 
                    metalness={0.8}
                    emissive={color}
                    emissiveIntensity={0.2}
                  />
                </mesh>
              );
            })}
            <OrbitControls autoRotate autoRotateSpeed={1} enableDamping dampingFactor={0.05} />
          </>
        )}
      </Canvas>
    </div>
  );
}
