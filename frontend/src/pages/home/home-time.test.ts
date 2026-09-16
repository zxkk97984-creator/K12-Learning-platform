import { describe, expect, it } from 'vitest'

import { formatNow, greetingForHour } from './home-time'

describe('greetingForHour 时段问候', () => {
  it('05–10 返回早上好', () => {
    expect(greetingForHour(5)).toBe('早上好')
    expect(greetingForHour(10)).toBe('早上好')
  })
  it('11–13 返回中午好', () => {
    expect(greetingForHour(11)).toBe('中午好')
    expect(greetingForHour(13)).toBe('中午好')
  })
  it('14–17 返回下午好', () => {
    expect(greetingForHour(14)).toBe('下午好')
    expect(greetingForHour(17)).toBe('下午好')
  })
  it('18–04 返回晚上好', () => {
    expect(greetingForHour(18)).toBe('晚上好')
    expect(greetingForHour(23)).toBe('晚上好')
    expect(greetingForHour(0)).toBe('晚上好')
    expect(greetingForHour(4)).toBe('晚上好')
  })
})

describe('formatNow', () => {
  it('格式化为 周X HH:mm（固定时间可测）', () => {
    expect(formatNow(new Date(2026, 7, 24, 14, 5))).toBe('周一 14:05')
  })
})
