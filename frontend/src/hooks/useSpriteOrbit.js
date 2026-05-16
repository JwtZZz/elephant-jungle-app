import { useEffect, useRef, useState } from 'react'

const SPRITE_SIZE = 64
const CRUISE_SPEED = 0.85
const TYPING_SPEED = 2.2
const JUMP_SPEED = 1.15
const CRUISE_MODES = ['typing', 'dash', 'hop']

function getTrackMetrics(track) {
  const width = Math.max(0, track.clientWidth - SPRITE_SIZE)
  const height = Math.max(0, track.clientHeight - SPRITE_SIZE)
  const perimeter = Math.max(1, 2 * (width + height))
  return { width, height, perimeter }
}

function getOrbitPosition(track, progress, direction) {
  const { width, height, perimeter } = getTrackMetrics(track)
  let next = progress % perimeter
  if (next < 0) next += perimeter

  if (next <= width) {
    return { x: next, y: 0, facing: direction > 0 ? 'right' : 'left', perimeter }
  }
  if (next <= width + height) {
    return { x: width, y: next - width, facing: direction > 0 ? 'right' : 'left', perimeter }
  }
  if (next <= (2 * width) + height) {
    return { x: width - (next - width - height), y: height, facing: direction > 0 ? 'left' : 'right', perimeter }
  }
  return { x: 0, y: height - (next - (2 * width) - height), facing: direction > 0 ? 'left' : 'right', perimeter }
}

export function useSpriteOrbit(spriteSpecs) {
  const [mode, setMode] = useState('typing')
  const speedRef = useRef(CRUISE_SPEED)
  const frameRef = useRef(0)
  const timerRef = useRef(0)
  const randomModeTimerRef = useRef(0)
  const lastTimeRef = useRef(0)
  const progressRef = useRef(spriteSpecs.map((_, index) => (index === 1 ? 9999 : 0)))
  const pausedRef = useRef(spriteSpecs.map(() => false))

  useEffect(() => {
    const tick = (timestamp) => {
      const delta = lastTimeRef.current ? Math.min(32, timestamp - lastTimeRef.current) : 16
      lastTimeRef.current = timestamp

      spriteSpecs.forEach((sprite, index) => {
        if (!sprite.trackRef.current || !sprite.shellRef.current) {
          return
        }
        if (pausedRef.current[index]) return
        const track = sprite.trackRef.current
        const direction = sprite.direction
        progressRef.current[index] += direction * speedRef.current * (delta / 16)
        const { x, y, facing, perimeter } = getOrbitPosition(track, progressRef.current[index], direction)
        if (index === 1 && progressRef.current[index] === 9999) {
          progressRef.current[index] = perimeter / 2
        }
        sprite.shellRef.current.style.left = `${x}px`
        sprite.shellRef.current.style.top = `${y}px`
        sprite.shellRef.current.classList.toggle('facing-left', facing === 'left')
        sprite.shellRef.current.classList.toggle('facing-right', facing === 'right')
      })

      frameRef.current = window.requestAnimationFrame(tick)
    }

    frameRef.current = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(frameRef.current)
  }, [spriteSpecs])

  useEffect(() => {
    const scheduleNextMode = () => {
      const delay = 1800 + Math.random() * 2600
      randomModeTimerRef.current = window.setTimeout(() => {
        const nextMode = CRUISE_MODES[Math.floor(Math.random() * CRUISE_MODES.length)]
        setMode(nextMode)
        if (nextMode === 'dash') {
          speedRef.current = TYPING_SPEED
        } else if (nextMode === 'hop') {
          speedRef.current = JUMP_SPEED
        } else {
          speedRef.current = CRUISE_SPEED
        }
        scheduleNextMode()
      }, delay)
    }

    scheduleNextMode()
    return () => window.clearTimeout(randomModeTimerRef.current)
  }, [])

  const boost = () => {
    speedRef.current = TYPING_SPEED
    setMode('dash')
    window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(() => {
      speedRef.current = CRUISE_SPEED
      setMode('typing')
    }, 900)
  }

  const cruise = () => {
    speedRef.current = CRUISE_SPEED
    window.clearTimeout(timerRef.current)
  }

  const pauseSprite = (index) => { pausedRef.current[index] = true }
  const resumeSprite = (index) => { pausedRef.current[index] = false }

  return { spriteMode: mode, boost, cruise, pauseSprite, resumeSprite }
}
