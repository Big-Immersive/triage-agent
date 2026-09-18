import { describe, expect, it } from 'vitest'
import { ago, bar, bytes, duration, usd } from '@/utils/format'

describe('format', () => {
  it('ago buckets', () => {
    const now = Date.parse('2026-09-18T12:00:00Z')
    expect(ago('2026-09-18T11:59:58Z', now)).toBe('now')
    expect(ago('2026-09-18T11:59:30Z', now)).toBe('30s ago')
    expect(ago('2026-09-18T11:52:00Z', now)).toBe('8m ago')
    expect(ago('2026-09-18T09:00:00Z', now)).toBe('3h ago')
    expect(ago(null)).toBe('—')
  })
  it('duration mm:ss and h:mm:ss', () => {
    expect(duration(192000)).toBe('03:12')
    expect(duration(3725000)).toBe('1:02:05')
    expect(duration(null)).toBe('—')
  })
  it('progress bar', () => {
    expect(bar(72)).toBe('███████░░░')
    expect(bar(0)).toBe('░░░░░░░░░░')
    expect(bar(100, 4)).toBe('████')
  })
  it('bytes and usd', () => {
    expect(bytes(42 * 1024)).toBe('42 KB')
    expect(usd(0.0037)).toBe('$0.0037')
    expect(usd(1.5)).toBe('$1.50')
  })
})
