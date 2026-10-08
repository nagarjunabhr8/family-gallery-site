import type { CSSProperties } from 'react'
import { thumbUrl } from '../api'

/** CSS for the user's display-only rotation. Sideways photos are scaled to stay inside their box. */
export function rotationStyle(rotation = 0, fill = true): CSSProperties | undefined {
  if (!rotation) return undefined
  const sideways = rotation === 90 || rotation === 270
  return { transform: `rotate(${rotation}deg)${sideways && fill ? ' scale(1.34)' : ''}` }
}

/** Square-ish thumbnail that fills its parent (object-cover) and honours rotation. */
export default function Thumb({
  id,
  rotation = 0,
  alt = '',
  className = '',
}: {
  id: number
  rotation?: number
  alt?: string
  className?: string
}) {
  return (
    <img
      src={thumbUrl(id)}
      alt={alt}
      loading="lazy"
      draggable={false}
      style={rotationStyle(rotation)}
      className={`h-full w-full object-cover ${className}`}
    />
  )
}
