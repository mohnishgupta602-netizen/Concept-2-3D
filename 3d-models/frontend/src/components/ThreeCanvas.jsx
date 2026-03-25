import { useMemo, Suspense, useState, useRef, useEffect, Component } from 'react';
import * as THREE from 'three';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Html, Environment, Center, useGLTF, Image, Line } from '@react-three/drei';
import { triggerVisionOptimization } from '../utils/visionLabeling';
import { Sparkles } from 'lucide-react';

function formatPartName(name, fallbackIndex = 0) {
  if (!name || typeof name !== 'string') return `Part ${fallbackIndex + 1}`;
  return name
    .replace(/_/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

function buildPartDescription(part, fallbackIndex = 0, total = 0) {
  const name = formatPartName(part?.name, fallbackIndex);
  const primitive = (part?.primitive || 'shape').toLowerCase();
  const base = (part?.description || '').trim() || `${name} is a key structural element in this model.`;

  const pos = part?.position || {};
  const x = getNumeric(pos?.x, 0);
  const y = getNumeric(pos?.y, 0);
  const z = getNumeric(pos?.z, 0);

  const horizontal = x < -0.12 ? 'left side' : x > 0.12 ? 'right side' : 'center';
  const vertical = y > 0.16 ? 'upper region' : y < -0.16 ? 'lower region' : 'mid region';
  const depth = z > 0.12 ? 'front-facing area' : z < -0.12 ? 'rear area' : 'central depth';

  const primitiveHint =
    primitive === 'cube' || primitive === 'box'
      ? 'It is represented with a box-like form to indicate planar or block structure.'
      : primitive === 'sphere'
      ? 'It is represented as a rounded volume to indicate organic or central mass.'
      : primitive === 'cylinder' || primitive === 'tube'
      ? 'It is represented as a cylindrical form to indicate support, connection, or flow.'
      : primitive === 'cone'
      ? 'It is represented as a tapered form to indicate directional geometry.'
      : 'Its geometric proxy highlights this part clearly in the fallback model.';

  const indexHint = total > 0 ? `This is part ${fallbackIndex + 1} of ${total} in the current fallback breakdown.` : '';

  return `${base} Located near the ${horizontal}, ${vertical}, and ${depth}. ${primitiveHint} ${indexHint}`.trim();
}

function getNumeric(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function resolveAnchorPosition(positionObj, bounds, idx, total) {
  const rawX = getNumeric(positionObj?.x, NaN);
  const rawY = getNumeric(positionObj?.y, NaN);
  const rawZ = getNumeric(positionObj?.z, NaN);

  const hasAllCoords = Number.isFinite(rawX) && Number.isFinite(rawY) && Number.isFinite(rawZ);

  const center = [
    bounds.min.x + bounds.size.x * 0.5,
    bounds.min.y + bounds.size.y * 0.5,
    bounds.min.z + bounds.size.z * 0.5,
  ];

  // Fallback ring if metadata is missing.
  if (!hasAllCoords) {
    const angle = (idx / Math.max(total, 1)) * Math.PI * 2;
    return [
      center[0] + Math.cos(angle) * bounds.size.x * 0.25,
      center[1] + (idx % 2 === 0 ? 1 : -1) * bounds.size.y * 0.08,
      center[2] + Math.sin(angle) * bounds.size.z * 0.25,
    ];
  }

  // Case 1: Semantic range [0, 1].
  if (rawX >= 0 && rawX <= 1 && rawY >= 0 && rawY <= 1 && rawZ >= 0 && rawZ <= 1) {
    return [
      bounds.min.x + rawX * bounds.size.x,
      bounds.min.y + rawY * bounds.size.y,
      bounds.min.z + rawZ * bounds.size.z,
    ];
  }

  // Case 2: Semantic range [-0.5, 0.5] or [-1, 1]-like normalized values.
  if (Math.abs(rawX) <= 0.55 && Math.abs(rawY) <= 0.55 && Math.abs(rawZ) <= 0.55) {
    return [
      bounds.min.x + (rawX + 0.5) * bounds.size.x,
      bounds.min.y + (rawY + 0.5) * bounds.size.y,
      bounds.min.z + (rawZ + 0.5) * bounds.size.z,
    ];
  }

  // Case 3: Semantic range [-1, 1].
  if (Math.abs(rawX) <= 1.25 && Math.abs(rawY) <= 1.25 && Math.abs(rawZ) <= 1.25) {
    return [
      bounds.min.x + ((rawX + 1) * 0.5) * bounds.size.x,
      bounds.min.y + ((rawY + 1) * 0.5) * bounds.size.y,
      bounds.min.z + ((rawZ + 1) * 0.5) * bounds.size.z,
    ];
  }

  // Case 4: Already world coordinates. Clamp to avoid far-away labels.
  return [
    clamp(rawX, bounds.min.x, bounds.max.x),
    clamp(rawY, bounds.min.y, bounds.max.y),
    clamp(rawZ, bounds.min.z, bounds.max.z),
  ];
}

function buildLabelPosition(anchor, bounds, idx, total) {
  const center = [
    bounds.min.x + bounds.size.x * 0.5,
    bounds.min.y + bounds.size.y * 0.5,
    bounds.min.z + bounds.size.z * 0.5,
  ];

  // Push labels away from model center to reduce overlap.
  let dirX = anchor[0] - center[0];
  let dirZ = anchor[2] - center[2];
  const planarLen = Math.hypot(dirX, dirZ);

  if (planarLen < 1e-4) {
    const angle = (idx / Math.max(total, 1)) * Math.PI * 2;
    dirX = Math.cos(angle);
    dirZ = Math.sin(angle);
  } else {
    dirX /= planarLen;
    dirZ /= planarLen;
  }

  const radialOffset = clamp(Math.max(bounds.size.x, bounds.size.z) * 0.04, 0.02, 0.2);
  const verticalOffset = clamp(bounds.size.y * 0.05 + (idx % 3) * (bounds.size.y * 0.012), 0.02, 0.16);

  return [
    anchor[0] + dirX * radialOffset,
    clamp(anchor[1] + verticalOffset, bounds.min.y - bounds.size.y * 0.1, bounds.max.y + bounds.size.y * 0.45),
    anchor[2] + dirZ * radialOffset,
  ];
}

function toProxyAxis(value, span) {
  const raw = getNumeric(value, 0);
  if (raw >= 0 && raw <= 1) {
    return (raw - 0.5) * 2 * span;
  }
  if (Math.abs(raw) <= 1) {
    return raw * span;
  }
  return clamp(raw, -span, span);
}

function toOverlayPercent(value) {
  const raw = getNumeric(value, 0);
  if (raw >= 0 && raw <= 1) return raw;
  if (Math.abs(raw) <= 1) return (raw + 1) / 2;
  return 0.5;
}

class ModelRenderErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error) {
    if (this.props.onError) {
      this.props.onError(error);
    }
  }

  componentDidUpdate(prevProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || null;
    }
    return this.props.children;
  }
}


function GLTFModelWithLabels({ url, parts, hoveredPart, onHoverStart, onHoverEnd }) {
  const gltf = useGLTF(url);
  const scene = gltf?.scene;

  const bounds = useMemo(() => {
    if (!scene) {
      return {
        min: new THREE.Vector3(-1, -1, -1),
        max: new THREE.Vector3(1, 1, 1),
        size: { x: 2, y: 2, z: 2 },
      };
    }

    try {
      const box = new THREE.Box3().setFromObject(scene);
      const min = box.min.clone();
      const max = box.max.clone();
      const size = max.clone().sub(min);

      return {
        min,
        max,
        size: {
          x: Math.max(size.x, 1),
          y: Math.max(size.y, 1),
          z: Math.max(size.z, 1),
        },
      };
    } catch (err) {
      console.error('Bounds calculation error:', err);
      return {
        min: new THREE.Vector3(-1, -1, -1),
        max: new THREE.Vector3(1, 1, 1),
        size: { x: 1, y: 1, z: 1 },
      };
    }
  }, [scene]);

  if (!scene) {
    console.warn('Scene not available from GLTF:', url);
    return null;
  }

  return (
    <>
      <primitive object={scene} />
      {Array.isArray(parts) && parts.length > 0 &&
        parts.slice(0, 8).map((part, idx) => {
          const positionObj = part?.position || {};
          const anchorPos = resolveAnchorPosition(positionObj, bounds, idx, parts.length);
          const labelPos = buildLabelPosition(anchorPos, bounds, idx, parts.length);

          return (
            <LabelMarker
              key={`${part?.name || 'marker'}-${idx}`}
              part={part}
              index={idx}
              markerPosition={anchorPos}
              labelPosition={labelPos}
              isHovered={hoveredPart?.index === idx}
              onHoverStart={onHoverStart}
              onHoverEnd={onHoverEnd}
            />
          );
        })}
    </>
  );
}

function BillboardImage({ url }) {
  return (
    <Image url={url} scale={[3, 3]} transparent opacity={1} />
  );
}

const ProceduralShape = ({ part, index, explodedOffset, isHovered, onHoverStart, onHoverEnd }) => {
  const primitive = (part?.primitive || 'cube').toLowerCase();
  const params = part?.parameters || {};
  const positionObj = part?.position || {};
  const basePos = [positionObj.x || 0, positionObj.y || 0, positionObj.z || 0];
  const finalPos = [basePos[0] + explodedOffset * (index % 2 === 0 ? -0.5 : 0.5), basePos[1], basePos[2]];

  const color = ['#ef4444', '#3b82f6', '#10b981', '#f59e0b', '#a855f7'][index % 5];

  let geometry;
  if (primitive === 'sphere') {
    geometry = <sphereGeometry args={[params.radius || 0.7, params.widthSegments || 24, params.heightSegments || 24]} />;
  } else if (primitive === 'cylinder' || primitive === 'tube') {
    geometry = <cylinderGeometry args={[params.radiusTop || 0.5, params.radiusBottom || 0.5, params.height || 1.5, params.radialSegments || 24]} />;
  } else if (primitive === 'cone') {
    geometry = <coneGeometry args={[params.radius || 0.6, params.height || 1.5, params.radialSegments || 24]} />;
  } else {
    geometry = <boxGeometry args={[params.width || 1, params.height || 1, params.depth || 1]} />;
  }

  return (
    <mesh
      position={finalPos}
      castShadow
      receiveShadow
      onPointerOver={(e) => {
        e.stopPropagation();
        onHoverStart?.(part, index);
      }}
      onPointerOut={(e) => {
        e.stopPropagation();
        onHoverEnd?.();
      }}
    >
      {geometry}
      <meshStandardMaterial
        color={color}
        roughness={0.35}
        metalness={0.15}
        emissive={isHovered ? '#ffffff' : '#000000'}
        emissiveIntensity={isHovered ? 0.18 : 0}
      />
      <Html transform distanceFactor={7} position={[0, 0.7, 0]} pointerEvents="auto">
        <div
          className="relative bg-slate-900/72 backdrop-blur text-white w-4 h-4 rounded text-[8px] leading-none border border-slate-700/70 flex items-center justify-center cursor-pointer select-none"
          style={{ pointerEvents: 'auto' }}
          onMouseEnter={(e) => {
            e.stopPropagation();
            onHoverStart?.(part, index);
          }}
          onMouseLeave={(e) => {
            e.stopPropagation();
            onHoverEnd?.();
          }}
          title={formatPartName(part?.name, index)}
        >
          {index + 1}
          {isHovered && (
            <div className="pointer-events-none absolute left-1/2 -translate-x-1/2 -top-2 -translate-y-full w-44 rounded-md border border-cyan-500/50 bg-slate-950/95 px-2 py-1 text-[10px] leading-snug text-left text-slate-100 shadow-lg">
              <div className="font-semibold text-cyan-300 mb-0.5">{formatPartName(part?.name, index)}</div>
              <div className="text-slate-200">{buildPartDescription(part, index)}</div>
            </div>
          )}
        </div>
      </Html>
    </mesh>
  );
};

const LabelMarker = ({ part, index, markerPosition, labelPosition, isHovered, onHoverStart, onHoverEnd }) => {
  const positionObj = part?.position || {};
  const markerPos = markerPosition || [positionObj.x || 0, (positionObj.y || 0) + 0.2, positionObj.z || 0];
  const textPos = labelPosition
    ? [
        labelPosition[0] - markerPos[0],
        labelPosition[1] - markerPos[1],
        labelPosition[2] - markerPos[2],
      ]
    : [0, 0.2, 0];
  // Line points are relative to the group position
  const linePoints = [[0, 0, 0], textPos];

  return (
    <group position={markerPos}>
      {/* Marker sphere with enhanced glow */}
      <mesh
        onPointerOver={(e) => {
          e.stopPropagation();
          onHoverStart?.(part, index);
        }}
        onPointerOut={(e) => {
          e.stopPropagation();
          onHoverEnd?.();
        }}
      >
        <sphereGeometry args={[isHovered ? 0.045 : 0.032, 18, 18]} />
        <meshStandardMaterial
          color={isHovered ? '#0ea5e9' : '#06b6d4'}
          emissive={isHovered ? '#0ea5e9' : '#0891b2'}
          emissiveIntensity={isHovered ? 0.8 : 0.3}
          toneMapped={false}
        />
      </mesh>

      {/* Leader line connecting marker to label */}
      <lineSegments>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={2}
            array={new Float32Array(linePoints.flat())}
            itemSize={3}
          />
        </bufferGeometry>
        <lineBasicMaterial color={isHovered ? '#0ea5e9' : '#06b6d4'} linewidth={2} transparent opacity={isHovered ? 0.8 : 0.4} />
      </lineSegments>

      {/* Label badge */}
      <Html transform sprite distanceFactor={1.4} position={textPos} pointerEvents="auto">
        <div
          className={`relative rounded text-white w-4 h-4 flex items-center justify-center cursor-pointer select-none text-[7px] font-semibold border transition-all duration-200 ${
            isHovered
              ? 'bg-cyan-500/92 border-cyan-300/85 shadow-[0_0_4px_rgba(34,211,238,0.45)]'
              : 'bg-cyan-600/80 border-cyan-400/55 shadow-[0_0_3px_rgba(34,211,238,0.28)]'
          }`}
          style={{ pointerEvents: 'auto' }}
          onMouseEnter={(e) => {
            e.stopPropagation();
            onHoverStart?.(part, index);
          }}
          onMouseLeave={(e) => {
            e.stopPropagation();
            onHoverEnd?.();
          }}
          title={formatPartName(part?.name, index)}
        >
          {index + 1}
          {isHovered && (
            <div className="pointer-events-none absolute left-1/2 -translate-x-1/2 -top-2 -translate-y-full w-44 rounded-md border border-cyan-500/50 bg-slate-950/95 px-2 py-1 text-[10px] leading-snug text-left text-slate-100 shadow-lg">
              <div className="font-semibold text-cyan-300 mb-0.5">{formatPartName(part?.name, index)}</div>
              <div className="text-slate-200">{buildPartDescription(part, index)}</div>
            </div>
          )}
        </div>
      </Html>
    </group>
  );
};

export default function ThreeCanvas({ modelData, explodedValue = 0 }) {
  const [hoveredPart, setHoveredPart] = useState(null);
  const fallbackImageUrl = modelData?.fallback_2d_image_url || modelData?.image_url;
  const [optimizingLabels, setOptimizingLabels] = useState(false);
  const [optimizationError, setOptimizationError] = useState(null);
  const [optimizedParts, setOptimizedParts] = useState(null);
  const [canvasError, setCanvasError] = useState(null);
  const [modelRenderError, setModelRenderError] = useState(null);
  const canvasRef = useRef(null);

  useEffect(() => {
    setCanvasError(null);
    setModelRenderError(null);
    setHoveredPart(null);
    setOptimizedParts(null);
  }, [modelData?.uid, modelData?.model_url, modelData?.embed_url]);

  const handleVisionOptimization = async () => {
    if (!canvasRef.current || !partDefinitions || partDefinitions.length === 0) {
      console.error('Cannot optimize: missing canvas or parts');
      setOptimizationError('Missing canvas or parts to optimize');
      return;
    }
    
    setOptimizationError(null);
    setOptimizingLabels(true);
    try {
      console.log('📍 Canvas ref:', canvasRef.current);
      console.log('📍 Canvas ref type:', canvasRef.current?.constructor?.name);
      
      const result = await triggerVisionOptimization(
        modelData?.uid || modelData?.title,
        modelData?.title || 'model',
        partDefinitions,
        canvasRef.current
      );
      
      if (result.error) {
        console.error('Vision optimization error:', result.error);
        setOptimizationError(result.error);
        return;
      }

      if (result.parts) {
        setOptimizedParts(result.parts);
        console.log('✅ Labels optimized successfully');
      }
    } catch (err) {
      console.error('Vision optimization exception:', err);
      setOptimizationError(err.message || 'Unknown error occurred');
    } finally {
      setOptimizingLabels(false);
    }
  };

  // If we have procedural data from the backend fallback
  const proceduralComponents = useMemo(() => {
    if (!modelData || !modelData.procedural_data) return null;

    const parts = modelData.procedural_data.parts;
    if (Array.isArray(parts) && parts.length > 0) {
      return parts;
    }

    const comps = (modelData.procedural_data.components || []).filter((comp) => typeof comp === 'string' && comp.trim().length > 0);
    return comps.map((comp, idx) => ({
      name: `part_${idx + 1}`,
      primitive: comp,
      parameters: {},
      position: { x: (idx - (comps.length - 1) / 2) * 2, y: 0, z: 0 },
    }));
  }, [modelData]);

  const partDefinitions = useMemo(() => {
    if (Array.isArray(modelData?.part_definitions) && modelData.part_definitions.length > 0) {
      return modelData.part_definitions;
    }

    if (Array.isArray(modelData?.geometry_details?.shapes) && modelData.geometry_details.shapes.length > 0) {
      return modelData.geometry_details.shapes;
    }

    return Array.isArray(proceduralComponents) ? proceduralComponents : [];
  }, [modelData, proceduralComponents]);

  const isOriginalLabeledTest = modelData?.labeling_mode === 'original-3d-test';
  const isFallbackModel =
    Boolean(modelData?.procedural_data) ||
    /fallback/i.test(modelData?.source || '') ||
    /labeled breakdown/i.test(modelData?.source || '') ||
    modelData?.labeling_mode === 'point-based-fallback';
  const builtInAnnotationsCount = Number(modelData?.built_in_annotations_count || 0);
  const shouldUseEmbedForOriginalTest =
    isOriginalLabeledTest &&
    (modelData?.source || '').toLowerCase() === 'original 3d labeling test' &&
    !!modelData?.embed_url &&
    builtInAnnotationsCount > 0;

  return (
    <div className="w-full h-[600px] rounded-2xl overflow-hidden bg-slate-950 border-2 border-slate-700/80 shadow-2xl relative before:absolute before:inset-0 before:rounded-2xl before:shadow-[inset_0_0_20px_rgba(51,65,85,0.3)] before:pointer-events-none">
      {canvasError ? (
        <div className="w-full h-full flex items-center justify-center bg-slate-900/50 border border-slate-800 rounded-2xl p-6">
          <div className="text-center max-w-sm">
            <div className="text-red-400 text-5xl mb-4">⚠️</div>
            <h3 className="text-lg font-bold text-slate-100 mb-3">3D Rendering Error</h3>
            <p className="text-sm text-slate-400 mb-6">{canvasError}</p>
            <button
              onClick={() => {
                setCanvasError(null);
                window.location.reload();
              }}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Try Again
            </button>
          </div>
        </div>
      ) : modelData?.embed_url && (!isOriginalLabeledTest || shouldUseEmbedForOriginalTest) ? (
        <div className="w-full h-full relative group">
          <iframe 
            title="3D Model Viewer"
            src={modelData.embed_url}
            frameBorder="0"
            allow="autoplay; fullscreen; xr-spatial-tracking"
            xr-spatial-tracking="true"
            execution-while-out-of-viewport="true"
            execution-while-not-rendered="true"
            web-share="true"
            className="w-full h-full"
          />
          
          {/* Top Info Mask (Hides Author, Title, Share buttons) */}
          <div className="absolute top-0 left-0 w-full h-[60px] bg-slate-950/90 pointer-events-none z-10" />
          
          {/* Bottom Edge Mask (Hides Sketchfab Watermark and all Bottom Controls) */}
          <div className="absolute bottom-0 left-0 w-full h-[55px] bg-slate-950 pointer-events-none z-10" />

          {/* Label overlay for embed-only models */}
          {isFallbackModel && Array.isArray(partDefinitions) && partDefinitions.length > 0 && (
            <div className="absolute inset-0 z-20 pointer-events-none">
              {partDefinitions.slice(0, 8).map((part, idx) => {
                const pos = part?.position || {};
                const x = clamp(toOverlayPercent(pos.x), 0.08, 0.92) * 100;
                const y = clamp(toOverlayPercent(pos.y), 0.12, 0.82) * 100;
                return (
                  <button
                    key={`${part?.name || 'embed-label'}-${idx}`}
                    type="button"
                    onMouseEnter={() => setHoveredPart({ ...part, index: idx })}
                    onMouseLeave={() => setHoveredPart(null)}
                    className="absolute -translate-x-1/2 -translate-y-1/2 w-4 h-4 rounded text-[8px] font-semibold text-white bg-cyan-600/85 border border-cyan-400/70 shadow-[0_0_4px_rgba(34,211,238,0.35)]"
                    style={{ left: `${x}%`, top: `${y}%`, pointerEvents: 'auto' }}
                    title={formatPartName(part?.name, idx)}
                  >
                    {idx + 1}
                    {hoveredPart?.index === idx && (
                      <span className="pointer-events-none absolute left-1/2 -translate-x-1/2 -top-2 -translate-y-full w-44 rounded-md border border-cyan-500/50 bg-slate-950/95 px-2 py-1 text-[10px] leading-snug text-left text-slate-100 shadow-lg">
                        <span className="block font-semibold text-cyan-300 mb-0.5">{formatPartName(part?.name, idx)}</span>
                        <span className="block text-slate-200">{buildPartDescription(part, idx)}</span>
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {shouldUseEmbedForOriginalTest && (
            <div className="absolute top-3 left-3 z-20 text-[10px] uppercase tracking-wider text-cyan-300 bg-slate-900/80 border border-cyan-600/30 rounded px-2 py-1 pointer-events-none">
              Using Sketchfab built-in annotations ({builtInAnnotationsCount})
            </div>
          )}
        </div>
      ) : (
        <Canvas
          shadows
          camera={{ position: [0, 2, 5], fov: 45 }}
          onCreated={({ gl }) => {
            canvasRef.current = gl.domElement;
          }}
          onError={(error) => {
            console.error('Canvas rendering error:', error);
            setCanvasError('Failed to render 3D model. This model may be incompatible or unavailable.');
          }}
        >
          <color attach="background" args={['#020617']} />
          
          <ambientLight intensity={0.5} />
          <directionalLight position={[10, 10, 5]} intensity={1} castShadow />
          <Environment preset="city" />
          
          <OrbitControls makeDefault autoRotate autoRotateSpeed={0.5} />
          
          <Center>
            {modelData?.model_url ? (
              <ModelRenderErrorBoundary
                resetKey={modelData?.uid || modelData?.model_url}
                onError={(err) => {
                  console.error('Model render error:', err);
                  setModelRenderError('This 3D file failed to load. Showing fallback preview.');
                }}
                fallback={null}
              >
                <Suspense fallback={
                  <Html center>
                    <div className="text-primary-400 font-mono text-sm tracking-widest uppercase mt-32 whitespace-nowrap">
                      Loading 3D Model...
                    </div>
                  </Html>
                }>
                  <GLTFModelWithLabels
                    url={modelData.model_url}
                    parts={isFallbackModel ? (optimizedParts || partDefinitions || []) : []}
                    hoveredPart={hoveredPart}
                    onHoverStart={(p, i) => setHoveredPart({ ...p, index: i })}
                    onHoverEnd={() => setHoveredPart(null)}
                  />
                </Suspense>
              </ModelRenderErrorBoundary>
            ) : proceduralComponents && proceduralComponents.length > 0 ? (
              proceduralComponents.map((part, idx) => (
                <ProceduralShape 
                  key={`${part?.name || part?.primitive || 'part'}-${idx}`}
                  part={part}
                  index={idx}
                  explodedOffset={explodedValue}
                  isHovered={hoveredPart?.index === idx}
                  onHoverStart={(p, i) => setHoveredPart({ ...p, index: i })}
                  onHoverEnd={() => setHoveredPart(null)}
                />
              ))
            ) : fallbackImageUrl ? (
              <Suspense fallback={null}>
                <BillboardImage url={fallbackImageUrl} />
                <Html center position={[0, -2, 0]}>
                  <div className="text-slate-400 font-mono text-sm tracking-widest uppercase whitespace-nowrap bg-slate-900/80 px-4 py-2 rounded-lg backdrop-blur-md">
                    2D Concept Visualization (3D Not Available)
                  </div>
                </Html>
              </Suspense>
            ) : modelData?.thumbnails?.[0]?.url ? (
              <Suspense fallback={null}>
                <BillboardImage url={modelData.thumbnails[0].url} />
                <Html center position={[0, -2, 0]}>
                  <div className="text-slate-400 font-mono text-sm tracking-widest uppercase whitespace-nowrap bg-slate-900/80 px-4 py-2 rounded-lg backdrop-blur-md">
                    3D Model Not Available (Showing Render)
                  </div>
                </Html>
              </Suspense>
            ) : (
              // Placeholder when no model
              <mesh>
                <icosahedronGeometry args={[1, 1]} />
                <meshStandardMaterial color="#64748b" wireframe />
                <Html center>
                  <div className="text-slate-400 font-mono text-sm tracking-widest uppercase mt-32 whitespace-nowrap">
                    Waiting for Input
                  </div>
                </Html>
              </mesh>
            )}
          </Center>

          {!modelData?.model_url && !proceduralComponents && isFallbackModel && Array.isArray(partDefinitions) && partDefinitions.length > 0 &&
            partDefinitions.slice(0, 8).map((part, idx) => {
              const positionObj = part?.position || {};
              const anchor = [
                toProxyAxis(positionObj.x, 1.15),
                toProxyAxis(positionObj.y, 0.9),
                toProxyAxis(positionObj.z, 0.35),
              ];
              const label = [
                anchor[0] + (idx % 2 === 0 ? -0.2 : 0.2),
                anchor[1] + 0.14 + (idx % 3) * 0.04,
                anchor[2],
              ];

              return (
                <LabelMarker
                  key={`${part?.name || 'proxy-marker'}-${idx}`}
                  part={part}
                  index={idx}
                  markerPosition={anchor}
                  labelPosition={label}
                  isHovered={hoveredPart?.index === idx}
                  onHoverStart={(p, i) => setHoveredPart({ ...p, index: i })}
                  onHoverEnd={() => setHoveredPart(null)}
                />
              );
            })}

          {isOriginalLabeledTest && !modelData?.model_url && (
            <Html position={[0, -2.4, 0]} center>
              <div className="text-[10px] uppercase tracking-wider text-cyan-300 bg-slate-900/80 border border-cyan-600/30 rounded px-3 py-1">
                Original source is embedded; showing labeled proxy preview.
              </div>
            </Html>
          )}
        </Canvas>
      )}

      {modelRenderError && (
        <div className="absolute top-4 right-4 z-20 max-w-sm bg-amber-950/85 backdrop-blur border border-amber-500/40 rounded-xl p-3 text-amber-100 text-xs">
          <div className="font-semibold mb-1">Model Fallback Active</div>
          <div className="text-amber-200">{modelRenderError}</div>
          <button
            onClick={() => setModelRenderError(null)}
            className="mt-2 text-[10px] text-amber-300 hover:text-amber-200 underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Error notification */}
      {optimizationError && (
        <div className="absolute bottom-4 right-4 z-20 max-w-sm bg-red-950/85 backdrop-blur border border-red-500/40 rounded-xl p-3 text-red-100 text-xs">
          <div className="font-semibold mb-1">⚠️ Optimization Failed</div>
          <div className="text-red-200">{optimizationError}</div>
          <button
            onClick={() => setOptimizationError(null)}
            className="mt-2 text-[10px] text-red-300 hover:text-red-200 underline"
          >
            Dismiss
          </button>
        </div>
      )}

        {/* Vision-based Label Optimization Button */}
        {isOriginalLabeledTest && modelData?.model_url && Array.isArray(partDefinitions) && partDefinitions.length > 0 && !optimizedParts && (
          <button
            onClick={handleVisionOptimization}
            disabled={optimizingLabels}
            className="absolute top-4 right-4 z-20 inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-semibold transition-all duration-300 shadow-lg"
            title="Use Gemini vision analysis to optimize label positions based on model geometry"
          >
            <Sparkles size={14} />
            {optimizingLabels ? 'Analyzing...' : 'Optimize with AI'}
          </button>
        )}
        {optimizedParts && (
          <div className="absolute top-4 right-4 z-20 px-3 py-2 rounded-lg bg-green-500/20 border border-green-500/50 text-green-300 text-xs font-semibold backdrop-blur">
            ✓ AI-Optimized Labels
          </div>
        )}
    </div>
  );
}
