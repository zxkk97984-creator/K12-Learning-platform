import { create } from 'zustand'

interface ToastItem {
  id: number
  message: string
}

interface ToastStore {
  toasts: ToastItem[]
  showToast: (message: string) => void
  removeToast: (id: number) => void
}

let toastSeq = 0

export const useToastStore = create<ToastStore>()((set, get) => ({
  toasts: [],
  showToast: (message) => {
    toastSeq += 1
    const id = toastSeq
    set((state) => ({ toasts: [...state.toasts, { id, message }] }))
    window.setTimeout(() => get().removeToast(id), 2200)
  },
  removeToast: (id) => set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) })),
}))
