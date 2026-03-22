import React, { Suspense, useEffect, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, useGLTF, Stage } from "@react-three/drei";

import * as THREE from "three";

function AIModel({ url }) {
  const { scene } = useGLTF(url);

  // Clone the scene and fix materials for community models
  const clonedScene = scene.clone();
  clonedScene.traverse((child) => {
    if (child.isMesh) {
      // Disable shadows which sometimes bug out poorly constructed models
      child.castShadow = false;
      child.receiveShadow = false;
      if (child.material) {
        // Force DoubleSide and turn off transparency which can cause z-sorting bugs
        child.material.side = THREE.DoubleSide;
        child.material.transparent = false;
        child.material.depthWrite = true;
        child.material.needsUpdate = true;
      }
    }
  });

  return <primitive object={clonedScene} />;
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

function SafeAIModel({ url, fallback }) {
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
          <AIModel url={url} />
        </Stage>
        <OrbitControls autoRotate autoRotateSpeed={2} enableDamping dampingFactor={0.05} />
      </Suspense>
    </GLBErrorBoundary>
  );
}

export default function ModelViewer({ data, fallbackShapes }) {
  const hasModelUrl = data?.viewer;
  
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
          <SafeAIModel url={data.viewer} fallback={fallbackMesh} />
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
