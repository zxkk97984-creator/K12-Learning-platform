import { expect, test } from '@playwright/test'

test('桌宠使用真实精灵图、支持拖动动画并可持久切换', async ({ page, request }, testInfo) => {
  const consoleIssues: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') {
      consoleIssues.push(`${message.type()}: ${message.text()}`)
    }
  })

  const accessToken = [
    'header',
    Buffer.from(JSON.stringify({ sub: 'student-1', username: 'xiaoming', user_type: 'STUDENT' })).toString(
      'base64url',
    ),
    'signature',
  ].join('.')

  const assetResponse = await request.get('/spritesheet-extended.webp')
  expect(assetResponse.ok()).toBeTruthy()
  expect(assetResponse.headers()['content-type']).toContain('image/webp')
  for (const petId of ['anya', 'doraemon', 'kun-like', 'lulu-capybara', 'shinchan']) {
    const petAssetResponse = await request.get(`/pets/${petId}/spritesheet.webp`)
    expect(petAssetResponse.ok()).toBeTruthy()
    expect(petAssetResponse.headers()['content-type']).toContain('image/webp')
  }

  await page.addInitScript((token) => {
    window.localStorage.setItem('shuangling-access-token', token)
  }, accessToken)
  await page.route('**/api/v1/**', async (route) => {
    const requestUrl = route.request().url()
    const isMeRequest = requestUrl.endsWith('/me')
    const isPreferencesRequest = requestUrl.endsWith('/me/preferences')
    const data = isMeRequest
      ? {
          student_id: 'student-1',
          nickname: '小明',
          avatar_url: null,
          grade: 8,
          stage: 'JUNIOR',
          language: 'zh-CN',
          learning_goal: null,
        }
      : isPreferencesRequest
        ? {
            voice_preference: {
              input_enabled: true,
              tts_enabled: true,
              volume: 0.8,
              speed: 1,
            },
          }
        : []
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data, meta: {} }),
    })
  })
  await page.goto('/home')

  const dock = page.getByRole('button', { name: '打开霜铃 AI 教师' })
  const sprite = dock.getByRole('img')
  await expect(sprite).toBeVisible()
  await expect(sprite).toHaveAttribute('data-sprite-state', 'idle')
  await page.screenshot({ path: testInfo.outputPath('companion-sprite.png'), fullPage: true })

  const box = await dock.boundingBox()
  expect(box).not.toBeNull()
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2)
  await page.mouse.down()
  await page.mouse.move(box!.x + box!.width / 2 + 40, box!.y + box!.height / 2, { steps: 2 })
  await expect(sprite).toHaveAttribute('data-sprite-state', 'running-right')
  await page.mouse.up()
  await expect(sprite).toHaveAttribute('data-sprite-state', 'idle')

  await dock.click()
  await expect(page.getByRole('complementary', { name: '霜铃对话面板' })).toBeVisible()
  await expect(page.getByRole('img', { name: '霜铃待机中' })).toHaveCount(2)

  await page.goto('/settings')
  const anyaOption = page.getByRole('button', { name: '选择阿尼亚形象' })
  await expect(anyaOption).toBeVisible()
  await anyaOption.click()
  await expect(anyaOption).toHaveAttribute('aria-pressed', 'true')

  // 切换桌宠后，dock 可访问名跟随新形象（useTeacherName 返回形象名）
  const selectedSprite = page.getByRole('button', { name: '打开阿尼亚 AI 教师' }).getByRole('img')
  await expect(selectedSprite).toHaveAttribute('data-pet-id', 'anya')
  await expect(selectedSprite).toHaveCSS(
    'background-image',
    /\/pets\/anya\/spritesheet\.webp/,
  )
  await page.screenshot({ path: testInfo.outputPath('companion-picker.png'), fullPage: true })

  await page.reload()
  await expect(page.getByRole('button', { name: '选择阿尼亚形象' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect(page.getByRole('button', { name: '打开阿尼亚 AI 教师' }).getByRole('img')).toHaveAttribute(
    'data-pet-id',
    'anya',
  )
  expect(consoleIssues).toEqual([])
})
