import { AnimatePresence, motion } from 'framer-motion'
import { Undo2 } from 'lucide-react'

export interface ToastData {
  id: number
  message: string
  undoable: boolean
}

export function Toast({ toast, onUndo }: { toast: ToastData | null; onUndo: () => void }) {
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-5 z-[95] flex justify-center px-4">
      <AnimatePresence mode="wait">
        {toast && (
          <motion.div
            key={toast.id}
            initial={{ opacity: 0, y: 16, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="pointer-events-auto flex items-center gap-3 rounded-xl bg-fg py-2 pl-4 pr-2 text-[13px] text-bg shadow-[0_12px_32px_-8px_rgba(0,0,0,0.4)]"
          >
            <span>{toast.message}</span>
            {toast.undoable && (
              <button
                onClick={onUndo}
                className="flex items-center gap-1.5 rounded-lg bg-bg/15 px-2.5 py-1 text-[12px] font-medium transition-colors hover:bg-bg/25"
              >
                <Undo2 size={13} />
                Undo
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
