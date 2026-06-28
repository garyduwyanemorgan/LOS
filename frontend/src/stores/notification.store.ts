import { create } from 'zustand'

export type ToastVariant = 'default' | 'success' | 'warning' | 'error' | 'info'

export interface Toast {
  id: string
  title: string
  description?: string
  variant: ToastVariant
  duration?: number
}

interface NotificationState {
  toasts: Toast[]
}

interface NotificationActions {
  addToast: (toast: Omit<Toast, 'id'>) => string
  removeToast: (id: string) => void
  clearAll: () => void
  success: (title: string, description?: string) => void
  error: (title: string, description?: string) => void
  warning: (title: string, description?: string) => void
  info: (title: string, description?: string) => void
}

let toastCounter = 0

export const useNotificationStore = create<NotificationState & NotificationActions>()(
  (set, get) => ({
    toasts: [],

    addToast: (toast) => {
      const id = `toast-${++toastCounter}`
      const duration = toast.duration ?? 5000
      set((state) => ({
        toasts: [...state.toasts, { ...toast, id }],
      }))
      if (duration > 0) {
        setTimeout(() => get().removeToast(id), duration)
      }
      return id
    },

    removeToast: (id) => {
      set((state) => ({
        toasts: state.toasts.filter((t) => t.id !== id),
      }))
    },

    clearAll: () => set({ toasts: [] }),

    success: (title, description) => {
      get().addToast({ title, description, variant: 'success' })
    },

    error: (title, description) => {
      get().addToast({ title, description, variant: 'error', duration: 8000 })
    },

    warning: (title, description) => {
      get().addToast({ title, description, variant: 'warning' })
    },

    info: (title, description) => {
      get().addToast({ title, description, variant: 'info' })
    },
  })
)
