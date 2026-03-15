import React, { Suspense } from "react";
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

export default function ModelViewer({ data, fallbackShapes }) {
  const hasModelUrl = data?.viewer;

  return (
    <div className="viewer-wrapper">
      <Canvas camera={{ position: [0, 2, 5], fov: 45 }}>
        {hasModelUrl ? (
          <Suspense fallback={null}>
            <Stage environment="city" intensity={0.6}>
              <AIModel url={data.viewer} />
            </Stage>
            <OrbitControls autoRotate autoRotateSpeed={2} enableDamping dampingFactor={0.05} />
          </Suspense>
        ) : (
          <>
            <ambientLight intensity={0.5} />
            <directionalLight position={[10, 10, 5]} intensity={1} />
            {fallbackShapes && fallbackShapes.map((shape, idx) => {
              const key = `${shape}-${idx}`;
              const color = ["#00ffcc", "#0071e3", "#ff0080", "#ffcc00"][idx % 4];
              return (
                <mesh key={key} position={[idx * 2 - (fallbackShapes.length - 1), 0, 0]}>
                  {shape === 'cube' && <boxGeometry args={[1, 1, 1]} />}
                  {shape === 'sphere' && <sphereGeometry args={[0.7, 32, 32]} />}
                  {shape === 'cylinder' && <cylinderGeometry args={[0.5, 0.5, 1.5, 32]} />}
                  {shape === 'cone' && <coneGeometry args={[0.5, 1.5, 32]} />}
                  {shape === 'tube' && <tubeGeometry />}
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
