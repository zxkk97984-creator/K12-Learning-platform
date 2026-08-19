/** 模拟网络延迟（150~300ms），方便后续 loading 态验证 */
export function delay<T>(data: T, ms = 200): Promise<T> {
  return new Promise((resolve) => {
    setTimeout(() => resolve(data), ms)
  })
}
