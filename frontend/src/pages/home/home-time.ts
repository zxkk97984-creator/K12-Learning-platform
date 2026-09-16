/** 首页问候时间格式化（纯函数，可测）：周二 14:05 */
export function formatNow(date: Date): string {
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  const weekday = weekdays[date.getDay()]
  const hh = String(date.getHours()).padStart(2, '0')
  const mm = String(date.getMinutes()).padStart(2, '0')
  return `${weekday} ${hh}:${mm}`
}

/** 按本地小时返回时段问候（T08）：05–11 早上好、11–14 中午好、14–18 下午好、18–05 晚上好。 */
export function greetingForHour(hour: number): string {
  if (hour >= 5 && hour < 11) return '早上好'
  if (hour >= 11 && hour < 14) return '中午好'
  if (hour >= 14 && hour < 18) return '下午好'
  return '晚上好'
}
