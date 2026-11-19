import { useEffect, useMemo, useState } from 'react'
import { Canvas, useFrame, useLoader } from '@react-three/fiber'
import { OrbitControls, Line } from '@react-three/drei'
import * as THREE from 'three'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import type { Job } from '../types'
import { X, Download, Video, Box, PersonStanding, Loader2 } from 'lucide-react'
import AdSlot from './AdSlot'

export default function ResultViewer({ job, onClose }: { job: Job; onClose: () => void }) {
  const r = job.result || {}
  const [tab, setTab] = useState<'3d' | 'video'>('3d')
  const [pose, setPose] = useState<any>(null)
  const [cameraPath, setCameraPath] = useState<any>(null)

  useEffect(() => {
    if (job.mode === 'mocap' && r.pose) fetch(r.pose).then(x => x.json()).then(setPose).catch(() => {})
    if (r.camera_path) fetch(r.camera_path).then(x => x.json()).then(setCameraPath).catch(() => {})
  }, [job.id])

  const downloads: { label: string; url: string }[] = []
  if (r.videos) {
    Object.entries(r.videos).forEach(([ext, url]) => downloads.push({ label: ext.toUpperCase(), url: url as string }))
  } else if (r.video) downloads.push({ label: 'Video', url: r.video })
  if (r.formats) {
    Object.entries(r.formats).forEach(([ext, url]) => downloads.push({ label: ext.toUpperCase(), url: url as string }))
  }
  if (r.point_cloud && !r.formats) downloads.push({ label: 'PLY', url: r.point_cloud })
  if (r.glb) downloads.push({ label: 'GLB', url: r.glb })
  if (r.bvh) downloads.push({ label: 'BVH', url: r.bvh })
  if (r.pose) downloads.push({ label: 'JSON', url: r.pose })

  return (
    <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal">
        <header className="modal-head">
          <div>
            <h2><span className={`mode-badge ${job.mode}`}>{job.mode}</span> {job.input_filename}</h2>
            <p className="muted small">Completed · {job.duration_seconds}s · {new Date(job.created_at).toLocaleString()}</p>
          </div>
          <div className="modal-actions">
            {downloads.map(d => (
              <a key={d.label} className="btn ghost small" href={d.url}
                 download={d.url.split('/').pop()?.split('?')[0]}>
                <Download size={14} /> {d.label}
              </a>
            ))}
            <button className="icon-btn" onClick={onClose}><X size={18} /></button>
          </div>
        </header>

        {job.status === 'failed' ? (
          <div className="alert error modal-alert">{job.error}</div>
        ) : job.status !== 'completed' ? (
          <div className="empty"><Loader2 className="spin" size={30} /><p>Still processing…</p></div>
        ) : (
          <>
            {job.mode === 'parallax' && (
              <div className="viewer-tabs">
                <button className={tab === '3d' ? 'active' : ''} onClick={() => setTab('3d')}>Interactive 3D</button>
                <button className={tab === 'video' ? 'active' : ''} onClick={() => setTab('video')}>Rendered video</button>
              </div>
            )}

            <div className="viewer-body">
              {job.mode === 'parallax' && (tab === '3d' ? (
                r.keyframe && r.depth ? <ParallaxView keyframe={r.keyframe} depth={r.depth} />
                  : <p className="muted">Preview assets unavailable.</p>
              ) : (
                <video className="result-video" src={r.video} controls autoPlay loop playsInline />
              ))}

              {job.mode === 'scene' && (
                r.point_cloud ? <PointCloudView url={r.point_cloud} points={r.points} />
                  : <p className="muted">Point cloud unavailable.</p>
              )}

              {job.mode === 'mocap' && (
                pose ? <PoseView pose={pose} /> : <p className="muted">Pose data unavailable.</p>
              )}
            </div>

            <footer className="viewer-foot">
              <span className="muted small">
                {job.mode === 'parallax' && <><Video size={13} /> {r.frames} frames · depth via {r.depth_backend || 'heuristic'}</>}
                {job.mode === 'scene' && <><Box size={13} /> {r.points?.toLocaleString()} points · PLY export</>}
                {job.mode === 'mocap' && <><PersonStanding size={13} /> {r.frames} poses · {r.demo ? 'demo animation' : 'MediaPipe pose'}</>}
              </span>
              {r.keyframe && <a href={r.keyframe} target="_blank" rel="noreferrer" className="muted small">Source frame ↗</a>}
              <AdSlot slot="viewer-footer" compact />
            </footer>
          </>
        )}
      </div>
    </div>
  )
}

function ParallaxView({ keyframe, depth }: { keyframe: string; depth: string }) {
  const [tex, depthTex] = useLoader(THREE.TextureLoader, [keyframe, depth])
  useMemo(() => { depthTex.colorSpace = THREE.NoColorSpace }, [depthTex])
  return (
    <Canvas camera={{ position: [0, 0, 2.6], fov: 50 }} dpr={[1, 1.5]}>
      <color attach="background" args={['#080b14']} />
      <group rotation={[0.05, -0.1, 0]}>
        <DepthPlane texture={tex} depth={depthTex} />
      </group>
      <OrbitControls enablePan={false} minDistance={1.6} maxDistance={5} />
    </Canvas>
  )
}

function DepthPlane({ texture, depth }: { texture: THREE.Texture; depth: THREE.Texture }) {
  const mat = useMemo(() => new THREE.ShaderMaterial({
    uniforms: { uTex: { value: texture }, uDepth: { value: depth }, uTime: { value: 0 } },
    vertexShader: `
      uniform sampler2D uDepth;
      uniform float uTime;
      varying vec2 vUv;
      void main() {
        vUv = uv;
        float d = texture2D(uDepth, uv).r;
        vec3 p = position;
        p.z += (d - 0.45) * 0.9;
        p.x += sin(uTime * 0.6) * d * 0.10;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
      }`,
    fragmentShader: `
      uniform sampler2D uTex;
      varying vec2 vUv;
      void main() { gl_FragColor = texture2D(uTex, vUv); }`,
  }), [texture, depth])
  useFrame((state) => { mat.uniforms.uTime.value = state.clock.elapsedTime })
  return <mesh material={mat}><planeGeometry args={[3.2, 1.8, 160, 90]} /></mesh>
}

function PointCloudView({ url, points }: { url: string; points?: number }) {
  const geom = useLoader(PLYLoader, url)
  useMemo(() => { geom.center(); geom.computeVertexNormals() }, [geom])
  return (
    <Canvas camera={{ position: [0, 0, 3.5], fov: 55 }} dpr={[1, 1.5]}>
      <color attach="background" args={['#080b14']} />
      <points geometry={geom}>
        <pointsMaterial size={0.018} vertexColors sizeAttenuation />
      </points>
      <gridHelper args={[6, 12, '#1d2b4a', '#121a2e']} position={[0, -1.4, 0]} />
      <OrbitControls minDistance={0.5} maxDistance={12} />
    </Canvas>
  )
}

function PoseView({ pose }: { pose: any }) {
  const [frame, setFrame] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setFrame(f => (f + 1) % pose.frames.length), 1000 / (pose.fps || 12))
    return () => clearInterval(id)
  }, [pose])
  const pts: [number, number, number][] = (pose.frames[frame] || []).map((p: number[]) =>
    [(p[0] - 0.5) * 3, (0.5 - p[1]) * 3, (p[2] || 0) * 3] as [number, number, number])

  return (
    <Canvas camera={{ position: [0, 0.2, 4], fov: 50 }} dpr={[1, 1.5]}>
      <color attach="background" args={['#080b14']} />
      <ambientLight intensity={0.8} />
      <pointLight position={[3, 3, 3]} intensity={40} />
      {pts.map((p, i) => <mesh key={i} position={p}><sphereGeometry args={[0.045, 12, 12]} /><meshStandardMaterial color="#4cc9f0" /></mesh>)}
      {(pose.connections || []).map(([a, b]: number[], i: number) => pts[a] && pts[b] && (
        <Line key={i} points={[pts[a], pts[b]]} color="#f72585" lineWidth={2} />
      ))}
      <gridHelper args={[6, 12, '#1d2b4a', '#121a2e']} position={[0, -1.6, 0]} />
      <OrbitControls enablePan={false} />
    </Canvas>
  )
}
