import { useEffect, useState, useRef } from 'react'
import type { SSEUpdate } from '@/lib/api'

export function useSSE(enabled = true) {
  const [update, setUpdate] = useState<SSEUpdate | null>(null)
  const [connected, setConnected] = useState(false)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!enabled) {
      esRef.current?.close()
      setConnected(false)
      setUpdate(null)
      return
    }

    const es = new EventSource('/api/runs/live')
    esRef.current = es

    es.onopen = () => setConnected(true)

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as SSEUpdate
        setUpdate(data)
        // Stop listening when run reaches terminal state
        if (['COMPLETED', 'FAILED', 'STOPPED'].includes(data.status)) {
          es.close()
          setConnected(false)
        }
      } catch {
        // ignore parse errors
      }
    }

    es.onerror = () => {
      setConnected(false)
      es.close()
    }

    return () => {
      es.close()
      setConnected(false)
    }
  }, [enabled])

  return { update, connected }
}
