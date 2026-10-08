import { useEffect, useState } from 'react'
import Duplicates from './pages/Duplicates'
import Library from './pages/Library'
import People from './pages/People'
import PersonPage from './pages/PersonPage'
import Settings from './pages/Settings'
import Unsorted from './pages/Unsorted'

type Route =
  | { name: 'library' }
  | { name: 'people' }
  | { name: 'person'; id: number }
  | { name: 'unsorted' }
  | { name: 'duplicates' }
  | { name: 'settings' }

function readRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, '')
  if (hash === 'settings') return { name: 'settings' }
  if (hash === 'duplicates') return { name: 'duplicates' }
  if (hash === 'people') return { name: 'people' }
  if (hash === 'people/unsorted') return { name: 'unsorted' }
  const m = hash.match(/^people\/(\d+)$/)
  if (m) return { name: 'person', id: Number(m[1]) }
  return { name: 'library' }
}

const NAV: [string, string, Route['name'][]][] = [
  ['#/', 'Library', ['library']],
  ['#/people', 'People', ['people', 'person', 'unsorted']],
  ['#/duplicates', 'Duplicates', ['duplicates']],
  ['#/settings', 'Settings', ['settings']],
]

function App() {
  const [route, setRoute] = useState<Route>(readRoute)

  useEffect(() => {
    const onHash = () => {
      setRoute(readRoute())
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  let page
  switch (route.name) {
    case 'settings':
      page = <Settings />
      break
    case 'duplicates':
      page = <Duplicates />
      break
    case 'people':
      page = <People />
      break
    case 'unsorted':
      page = <Unsorted />
      break
    case 'person':
      page = <PersonPage key={route.id} id={route.id} />
      break
    default:
      page = <Library />
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 bg-stone-50/85 backdrop-blur border-b border-stone-200">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          <a href="#/" className="font-serif text-2xl tracking-tight text-stone-900 whitespace-nowrap">
            Family Memories
          </a>
          <nav className="flex gap-1 overflow-x-auto">
            {NAV.map(([href, label, names]) => (
              <a
                key={href}
                href={href}
                className={`px-3 py-1.5 rounded-full text-sm whitespace-nowrap transition-colors ${
                  names.includes(route.name) ? 'bg-stone-800 text-stone-50' : 'text-stone-600 hover:bg-stone-200'
                }`}
              >
                {label}
              </a>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 sm:px-6 py-8">{page}</main>
    </div>
  )
}

export default App
