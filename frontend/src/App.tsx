import { AnimatePresence, MotionConfig, motion } from 'motion/react'
import type { JSX } from 'react'
import { Shell } from './components/Shell'
import { useRoute } from './lib/router'
import type { RoutePath } from './lib/router'
import { SessionProvider } from './state/session'
import { Alerts } from './views/Alerts'
import { Contracts } from './views/Contracts'
import { DataImport } from './views/DataImport'
import { Methodology } from './views/Methodology'
import { Overview } from './views/Overview'
import { Research } from './views/Research'

const VIEWS: Record<RoutePath, () => JSX.Element> = {
  '/': Overview,
  '/contracts': Contracts,
  '/data': DataImport,
  '/research': Research,
  '/alerts': Alerts,
  '/methodology': Methodology,
}

function Routed() {
  const route = useRoute()
  const View = VIEWS[route]
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={route}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.16, ease: [0.2, 0, 0, 1] }}
      >
        <View />
      </motion.div>
    </AnimatePresence>
  )
}

function App() {
  return (
    <MotionConfig reducedMotion="user">
      <SessionProvider>
        <Shell>
          <Routed />
        </Shell>
      </SessionProvider>
    </MotionConfig>
  )
}

export default App
