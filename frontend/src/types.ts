export type Mode = 'parallax' | 'mocap' | 'scene'
export type Plan = 'free' | 'pro' | 'studio' | 'owner'

export interface User {
  id: number
  email: string
  full_name: string
  plan: Plan
  is_owner: boolean
  created_at: string
}

export interface PlanInfo {
  plan: Plan
  label: string
  price_monthly: number
  max_duration_seconds: number
  max_resolution: number
  modes: Mode[]
  priority: number
  watermark: boolean
  exports: string[]
  batch: boolean
  api_access: boolean
  commercial: boolean
  billing_enabled: boolean
  personal_mode: boolean
}

export interface PlanOption {
  id: string
  label: string
  price_monthly: number
  max_duration_seconds: number
  max_resolution: number
  modes: Mode[]
  watermark: boolean
  exports: string[]
  batch: boolean
  api_access: boolean
  commercial: boolean
}

export interface Job {
  id: string
  mode: Mode
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  message: string
  input_filename: string
  output_filename: string | null
  duration_seconds: number
  result: Record<string, any> | null
  error: string | null
  created_at: string
  updated_at: string
}
