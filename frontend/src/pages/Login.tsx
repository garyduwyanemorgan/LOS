import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Waves, Mail, Lock, AlertCircle } from 'lucide-react'
import { useAuthStore } from '@/stores/auth.store'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const { login, isLoading, error, isAuthenticated, clearError } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    if (isAuthenticated) navigate('/')
  }, [isAuthenticated, navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    clearError()
    try {
      await login(email, password)
      navigate('/')
    } catch {
      // error is already set in store
    }
  }

  return (
    <div className="min-h-screen bg-[#0D2137] flex">
      {/* Left branding panel */}
      <div className="hidden lg:flex lg:flex-col lg:w-1/2 bg-gradient-to-br from-[#0D2137] via-[#1A3A5C] to-[#0891B2] p-12 justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center">
            <Waves className="h-6 w-6 text-white" />
          </div>
          <div>
            <div className="text-white font-bold text-lg leading-none">LOS</div>
            <div className="text-white/50 text-xs">Lagoons Operating System</div>
          </div>
        </div>

        <div className="space-y-6">
          <h1 className="text-4xl font-bold text-white leading-tight">
            Environmental Intelligence Platform
          </h1>
          <p className="text-white/70 text-lg leading-relaxed">
            Real-time lagoon monitoring with scientific loop analysis, predictive bloom
            detection, and evidence-based management recommendations.
          </p>

          <div className="grid grid-cols-2 gap-4">
            {[
              { label: 'Hydrological', color: '#0891B2', icon: '💧' },
              { label: 'Chemical', color: '#7C3AED', icon: '⚗' },
              { label: 'Ecological', color: '#16A34A', icon: '🌿' },
              { label: 'Infrastructure', color: '#D97706', icon: '⚙' },
            ].map((loop) => (
              <div
                key={loop.label}
                className="flex items-center gap-2 bg-white/10 rounded-lg px-3 py-2"
              >
                <span className="text-lg">{loop.icon}</span>
                <span className="text-white/80 text-sm font-medium">{loop.label}</span>
              </div>
            ))}
          </div>
        </div>

        <p className="text-white/30 text-xs">
          v1.0 — Built for GCC environmental forensics
        </p>
      </div>

      {/* Right login form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-[#F8FAFC]">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <div className="w-10 h-10 bg-[#0D2137] rounded-xl flex items-center justify-center">
              <Waves className="h-6 w-6 text-white" />
            </div>
            <div>
              <div className="text-[#0D2137] font-bold text-lg leading-none">LOS</div>
              <div className="text-slate-400 text-xs">Lagoons Operating System</div>
            </div>
          </div>

          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8">
            <h2 className="text-2xl font-bold text-[#0D2137] mb-1">Sign in</h2>
            <p className="text-slate-500 text-sm mb-8">Access your environmental dashboard</p>

            {error && (
              <Alert variant="destructive" className="mb-6">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <form onSubmit={(e) => { void handleSubmit(e) }} className="space-y-5">
              <div className="space-y-1.5">
                <Label htmlFor="email">Email address</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <Input
                    id="email"
                    type="email"
                    placeholder="operator@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="pl-9"
                    required
                    autoComplete="email"
                    autoFocus
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <Input
                    id="password"
                    type="password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="pl-9"
                    required
                    autoComplete="current-password"
                  />
                </div>
              </div>

              <Button
                type="submit"
                className="w-full"
                loading={isLoading}
                disabled={!email || !password}
              >
                Sign in
              </Button>
            </form>

            <p className="mt-6 text-center text-xs text-slate-400">
              Contact your administrator for access credentials
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
