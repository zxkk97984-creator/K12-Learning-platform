import { useToastStore } from './store'

export function ToastHost() {
  const toasts = useToastStore((state) => state.toasts)
  return (
    <div className="pointer-events-none fixed bottom-6 left-1/2 z-90 flex -translate-x-1/2 flex-col items-center gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="rounded-[9px] bg-fg px-3.5 py-2.5 text-xs text-surface shadow-soft"
          role="status"
        >
          {toast.message}
        </div>
      ))}
    </div>
  )
}
