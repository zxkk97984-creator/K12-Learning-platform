import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '@/features/auth'
import { ApiError } from '@/shared/api/http'

export default function LoginPage() {
  const { currentUser, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/home'
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (currentUser) {
    return <Navigate to={from} replace />
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(username.trim(), password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === 'INVALID_CREDENTIALS'
          ? '用户名或密码错误'
          : '登录失败，请稍后重试',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-bg px-4 font-body text-fg">
      <form
        onSubmit={(event) => void submit(event)}
        className="w-full max-w-sm rounded-[22px] border border-border bg-surface p-8 shadow-soft"
      >
        <p className="font-mono text-[10px] tracking-widest text-accent">AI teacher · v3</p>
        <h1 className="mt-2 font-display text-3xl">霜铃 K12</h1>
        <p className="mt-1 text-sm text-muted">登录后继续你的学习旅程</p>

        <label className="mt-6 grid gap-1 text-xs text-muted">
          用户名
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            className="h-11 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
          />
        </label>
        <label className="mt-4 grid gap-1 text-xs text-muted">
          密码
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            className="h-11 rounded-[10px] border border-border bg-bg px-3 text-[13px] text-fg outline-none focus:border-fg"
          />
        </label>

        {error ? (
          <p className="mt-3 text-xs text-accent" role="alert">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={submitting || !username.trim() || !password}
          className="mt-6 w-full rounded-[10px] bg-accent py-2.5 text-sm text-surface hover:bg-accent/85 disabled:opacity-50"
        >
          {submitting ? '登录中…' : '登录'}
        </button>
        <p className="mt-4 text-center font-mono text-[10px] text-muted">
          演示账号：xiaoming / demo123（本地 seed）
        </p>
      </form>
    </main>
  )
}
