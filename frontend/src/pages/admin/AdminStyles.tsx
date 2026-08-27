import { useEffect, useState } from 'react'

import type { AdminTeacherRole } from '@/shared/api/admin-service'
import { adminService } from '@/shared/api/admin-service'

/** 教师风格管理（Phase 4）：真实 CRUD，刷新后保持。 */
export function AdminStyles() {
  const [roles, setRoles] = useState<AdminTeacherRole[]>([])
  const [name, setName] = useState('')
  const [tone, setTone] = useState('耐心鼓励')
  const [style, setStyle] = useState('温暖清晰')
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      setRoles(await adminService.getTeacherRoles())
    } catch {
      setError('加载失败')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const create = async () => {
    if (!name.trim()) {
      setError('名称不能为空')
      return
    }
    try {
      await adminService.createTeacherRole({ name: name.trim(), tone, teaching_style: style })
      setName('')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建失败（名称可能重复）')
    }
  }

  const toggle = async (role: AdminTeacherRole) => {
    await adminService.patchTeacherRole(role.role_id, { is_enabled: !role.enabled })
    await load()
  }

  return (
    <section className="space-y-4">
      <h1 className="font-display text-2xl text-fg">教师风格管理</h1>
      <div className="rounded-[12px] border border-border bg-surface p-4">
        <div className="flex flex-wrap gap-2">
          <input
            aria-label="风格名称"
            placeholder="名称"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="rounded-lg border border-border bg-bg px-2.5 py-2 text-sm text-fg"
          />
          <input
            aria-label="语气"
            value={tone}
            onChange={(event) => setTone(event.target.value)}
            className="rounded-lg border border-border bg-bg px-2.5 py-2 text-sm text-fg"
          />
          <input
            aria-label="教学风格"
            value={style}
            onChange={(event) => setStyle(event.target.value)}
            className="rounded-lg border border-border bg-bg px-2.5 py-2 text-sm text-fg"
          />
          <button
            type="button"
            onClick={() => void create()}
            className="rounded-lg border border-fg bg-fg px-3 py-2 text-sm text-surface hover:bg-fg/85"
          >
            新增风格
          </button>
        </div>
        {error ? (
          <p role="alert" className="mt-2 text-xs text-red-400">
            {error}
          </p>
        ) : null}
      </div>

      <table data-testid="admin-styles-table" className="w-full text-left text-sm">
        <thead className="text-muted">
          <tr>
            <th className="py-2">名称</th>
            <th>语气</th>
            <th>风格</th>
            <th>状态</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {roles.map((role) => (
            <tr key={role.role_id} className="border-t border-border">
              <td className="py-2 text-fg">{role.name}</td>
              <td>{role.tone}</td>
              <td>{role.teaching_style}</td>
              <td>{role.enabled ? '启用' : '停用'}</td>
              <td>
                <button
                  type="button"
                  className="text-xs text-muted hover:text-fg hover:underline"
                  onClick={() => void toggle(role)}
                >
                  {role.enabled ? '停用' : '启用'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
