import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-SE', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-SE', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatCost(usd: number): string {
  if (usd < 0.01) return `$${(usd * 100).toFixed(3)}¢`
  return `$${usd.toFixed(4)}`
}

export function formatDuration(startIso: string, endIso: string | null): string {
  if (!endIso) return '—'
  const ms = new Date(endIso).getTime() - new Date(startIso).getTime()
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

export function confidenceColor(score: number): string {
  if (score >= 0.8) return 'text-green-400'
  if (score >= 0.6) return 'text-brand-gold'
  return 'text-brand-muted'
}

export function statusColor(status: string): string {
  switch (status.toUpperCase()) {
    case 'COMPLETED': return 'bg-green-500/20 text-green-400 border-green-500/30'
    case 'RUNNING':   return 'bg-brand-gold/20 text-brand-gold border-brand-gold/30'
    case 'FAILED':    return 'bg-red-500/20 text-red-400 border-red-500/30'
    case 'STOPPED':   return 'bg-brand-muted/20 text-brand-muted border-brand-muted/30'
    case 'NEW':       return 'bg-brand-gold/20 text-brand-gold border-brand-gold/30'
    case 'REVIEWED':  return 'bg-blue-500/20 text-blue-400 border-blue-500/30'
    case 'MESSAGED':  return 'bg-green-500/20 text-green-400 border-green-500/30'
    case 'SKIP':      return 'bg-brand-muted/20 text-brand-muted border-brand-muted/30'
    default:          return 'bg-brand-walnut/40 text-brand-white border-brand-walnut'
  }
}
