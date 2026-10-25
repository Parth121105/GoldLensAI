import { MotionConfig, motion } from 'motion/react'

function App() {
  return (
    <MotionConfig reducedMotion="user">
      <main className="grid min-h-dvh place-items-center bg-neutral-50 text-neutral-900">
        <motion.h1
          className="text-4xl font-semibold tracking-tight"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', duration: 0.5, bounce: 0 }}
        >
          GoldLensAI
        </motion.h1>
      </main>
    </MotionConfig>
  )
}

export default App
