import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { FaceItem, Person } from '../api'
import FaceGrid from '../components/FaceGrid'

export default function Unsorted() {
  const [faces, setFaces] = useState<FaceItem[]>([])
  const [total, setTotal] = useState(0)
  const [people, setPeople] = useState<Person[]>([])

  const load = useCallback(() => {
    api.unassignedFaces().then((r) => {
      setFaces(r.faces)
      setTotal(r.total)
    })
    api.people(true).then((d) => setPeople(d.people))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="pb-24">
      <a href="#/people" className="text-sm text-stone-500 hover:text-stone-800">
        ← People
      </a>
      <h1 className="mt-4 font-serif text-3xl text-stone-900">Faces not recognised yet</h1>
      <p className="mt-2 max-w-2xl text-stone-600">
        People seen only once, very small or blurry faces, statues and strangers. Select faces to put them with someone,
        or leave them. They never appear as a person on their own.
      </p>
      <p className="mt-1 mb-6 text-sm text-stone-500">{total} faces</p>
      <FaceGrid faces={faces} people={people} onChanged={load} />
    </div>
  )
}
