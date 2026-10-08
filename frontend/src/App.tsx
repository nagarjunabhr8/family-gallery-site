import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import BestOfYear from './pages/BestOfYear'
import Duplicates from './pages/Duplicates'
import EventPage from './pages/EventPage'
import Events from './pages/Events'
import Library from './pages/Library'
import Occasions from './pages/Occasions'
import OurStory from './pages/OurStory'
import People from './pages/People'
import PersonPage from './pages/PersonPage'
import Settings from './pages/Settings'
import Unsorted from './pages/Unsorted'
import { useTheme } from './theme'
import type { ThemeChoice } from './theme'

type Route =
  | { name: 'story' }
  | { name: 'best'; year: number | null }
  | { name: 'library' }
  | { name: 'events' }
  | { name: 'event'; id: number }
  | { name: 'occasions' }
  | { name: 'people' }
  | { name: 'person'; id: number }
  | { name: 'unsorted' }
  | { name: 'duplicates' }
  | { name: 'settings' }

function readRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, '')
  const simple: Record<string, Route> = {
    library: { name: 'library' },
    settings: { name: 'settings' },
    duplicates: { name: 'duplicates' },
    people: { name: 'people' },
    'people/unsorted': { name: 'unsorted' },
    events: { name: 'events' },
    occasions: { name: 'occasions' },
    best: { name: 'best', year: null },
  }
  if (simple[hash]) return simple[hash]
  let m = hash.match(/^events\/(\d+)$/)
  if (m) return { name: 'event', id: Number(m[1]) }
  m = hash.match(/^people\/(\d+)$/)
  if (m) return { name: 'person', id: Number(m[1]) }
  m = hash.match(/^best\/(\d{4})$/)
  if (m) return { name: 'best', year: Number(m[1]) }
  return { name: 'story' }
}

const NAV: [string, string, Route['name'][]][] = [
  ['#/', 'Our Story', ['story', 'best']],
  ['#/events', 'Events', ['events', 'event']],
  ['#/people', 'People', ['people', 'person', 'unsorted']],
  ['#/library', 'Library', ['library']],
  ['#/occasions', 'Occasions', ['occasions']],
  ['#/duplicates', 'Duplicates', ['duplicates']],
  ['#/settings', 'Settings', ['settings']],
]

const THEME_ICON: Record<ThemeChoice, string> = { system: '◐', light: '☀', dark: '☾' }
const THEME_NEXT: Record<ThemeChoice, ThemeChoice> = { system: 'light', light: 'dark', dark: 'system' }

function App() {
  const [route, setRoute] = useState<Route>(readRoute)
  const [menuOpen, setMenuOpen] = useState(false)
  const [theme, setTheme] = useTheme()

  useEffect(() => {
    const onHash = () => {
      setRoute(readRoute())
      setMenuOpen(false)
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  let page
  switch (route.name) {
    case 'library':
      page = <Library />
      break
    case 'best':
      page = <BestOfYear year={route.year} />
      break
    case 'settings':
      page = <Settings />
      break
    case 'duplicates':
      page = <Duplicates />
      break
    case 'people':
      page = <People />
      break
    case 'events':
      page = <Events />
      break
    case 'event':
      page = <EventPage key={route.id} id={route.id} />
      break
    case 'occasions':
      page = <Occasions />
      break
    case 'unsorted':
      page = <Unsorted />
      break
    case 'person':
      page = <PersonPage key={route.id} id={route.id} />
      break
    default:
      page = <OurStory />
  }

  const navLink = ([href, label, names]: (typeof NAV)[number], mobile = false) => (
    <a
      key={href}
      href={href}
      className={
        mobile
          ? `block rounded-xl px-4 py-3 text-lg ${names.includes(route.name) ? 'bg-stone-200 text-stone-900' : 'text-stone-700'}`
          : `px-3 py-1.5 rounded-full text-sm whitespace-nowrap transition-colors ${
              names.includes(route.name) ? 'bg-stone-800 text-stone-50' : 'text-stone-600 hover:bg-stone-200'
            }`
      }
    >
      {label}
    </a>
  )

  const themeButton = (
    <button
      onClick={() => setTheme(THEME_NEXT[theme])}
      title={`Theme: ${theme} (click to change)`}
      aria-label={`Theme: ${theme}`}
      className="h-9 w-9 shrink-0 rounded-full text-lg text-stone-600 hover:bg-stone-200"
    >
      {THEME_ICON[theme]}
    </button>
  )

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 bg-stone-50/85 backdrop-blur border-b border-stone-200/70">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          <a href="#/" className="font-serif text-2xl tracking-tight text-stone-900 whitespace-nowrap">
            Family Memories
          </a>
          <nav className="hidden lg:flex items-center gap-1">
            {NAV.map((n) => navLink(n))}
            {themeButton}
          </nav>
          <div className="flex items-center gap-1 lg:hidden">
            {themeButton}
            <button
              onClick={() => setMenuOpen((o) => !o)}
              aria-expanded={menuOpen}
              aria-label="Menu"
              className="h-10 w-10 rounded-full text-xl text-stone-700 hover:bg-stone-200"
            >
              {menuOpen ? '✕' : '☰'}
            </button>
          </div>
        </div>
        <AnimatePresence>
          {menuOpen && (
            <motion.nav
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden border-t border-stone-200 bg-stone-50 lg:hidden"
            >
              <div className="px-4 py-3 space-y-1">{NAV.map((n) => navLink(n, true))}</div>
            </motion.nav>
          )}
        </AnimatePresence>
      </header>
      <AnimatePresence mode="wait">
        <motion.main
          key={window.location.hash.split('/').slice(0, 2).join('/') || 'home'}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          className="mx-auto max-w-7xl px-4 sm:px-6 py-8"
        >
          {page}
        </motion.main>
      </AnimatePresence>
    </div>
  )
}

export default App
