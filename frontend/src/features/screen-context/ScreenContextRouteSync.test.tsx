// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import {
  createMemoryRouter,
  Outlet,
  RouterProvider,
} from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'

import { ScreenContextProvider, useScreenContext } from './ScreenContextProvider'
import { ScreenContextRouteSync } from './ScreenContextRouteSync'

function ReaderStub() {
  const { setScreenContext } = useScreenContext()
  useEffect(() => {
    setScreenContext({
      route: '/learn/b1/c1',
      pageType: 'chapter_reader',
      bookId: 'b1',
      chapterId: 'c1',
      chapterTitle: '训练数据',
    })
  }, [setScreenContext])
  return null
}

describe('ScreenContextRouteSync（Phase 2-A3 路由清理）', () => {
  afterEach(cleanup)

  it('离开 Reader 进入不声明上下文的页面后，旧 book/chapter 被清空', async () => {
    function LibraryPageStub() {
      const { screenContext } = useScreenContext()
      return (
        <output data-testid="ctx">
          {screenContext.route}|{screenContext.pageType}|{screenContext.bookId ?? 'no-book'}
        </output>
      )
    }
    // 模拟真实 AppLayout：布局路由内挂载 ScreenContextRouteSync
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: (
            <>
              <ScreenContextRouteSync />
              <Outlet />
            </>
          ),
          children: [
            { path: 'learn/:bookId/:chapterId', element: <ReaderStub /> },
            { path: 'library', element: <LibraryPageStub /> },
          ],
        },
      ],
      { initialEntries: ['/learn/b1/c1'] },
    )
    render(
      <ScreenContextProvider>
        <RouterProvider router={router} />
      </ScreenContextProvider>,
    )
    // 等待 Reader 声明上下文生效
    await new Promise((resolve) => setTimeout(resolve, 0))
    router.navigate('/library')
    await screen.findByTestId('ctx')
    await waitFor(() =>
      expect(screen.getByTestId('ctx').textContent).toBe('/library|library|no-book'),
    )
  })

  it('目标页面声明了自己的上下文时不会被同步组件误清', async () => {
    function LibrarySetterStub() {
      const { setScreenContext, screenContext } = useScreenContext()
      useEffect(() => {
        setScreenContext({ route: '/library', pageType: 'library' })
      }, [setScreenContext])
      return (
        <output data-testid="ctx">
          {screenContext.route}|{screenContext.pageType}|{screenContext.bookId ?? 'no-book'}
        </output>
      )
    }
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: (
            <>
              <ScreenContextRouteSync />
              <Outlet />
            </>
          ),
          children: [{ path: 'library', element: <LibrarySetterStub /> }],
        },
      ],
      { initialEntries: ['/library'] },
    )
    render(
      <ScreenContextProvider>
        <RouterProvider router={router} />
      </ScreenContextProvider>,
    )
    expect((await screen.findByTestId('ctx')).textContent).toBe(
      '/library|library|no-book',
    )
  })
})
