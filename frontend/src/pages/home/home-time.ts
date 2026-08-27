/** 首页问候时间格式化（纯函数，可测）：周二 14:05 */
export function formatNow(date: Date): string {
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  const weekday = weekdays[date.getDay()]
  const hh = String(date.getHours()).padStart(2, '0')
  const mm = String(date.getMinutes()).padStart(2, '0')
  return `${weekday} ${hh}:${mm}`
}
