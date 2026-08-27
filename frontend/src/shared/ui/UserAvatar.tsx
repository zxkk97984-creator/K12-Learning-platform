interface UserAvatarProps {
  nickname?: string | null
  /** 图片 URL（http/data）或表情字符；空值回退昵称首字 */
  avatarUrl?: string | null
  size?: 'sm' | 'md' | 'lg'
}

const SIZE_CLASS = {
  sm: 'h-[30px] w-[30px] text-sm',
  md: 'h-12 w-12 text-xl',
  lg: 'h-16 w-16 text-3xl',
} as const

export function UserAvatar({ nickname, avatarUrl, size = 'sm' }: UserAvatarProps) {
  const url = avatarUrl?.trim() ?? ''
  const isImage = /^(https?:|data:image|\/)/i.test(url)
  const isEmoji = !isImage && url.length > 0 && url.length <= 8
  return (
    <span
      className={`inline-grid shrink-0 place-items-center overflow-hidden rounded-full bg-fg-soft font-display leading-none text-fg ${SIZE_CLASS[size]}`}
      title={nickname ?? undefined}
    >
      {isImage ? (
        <img src={url} alt="" className="h-full w-full object-cover" />
      ) : isEmoji ? (
        <span aria-hidden="true" className="not-italic">{url}</span>
      ) : (
        <span aria-hidden="true">{(nickname ?? '').trim().slice(0, 1) || '学'}</span>
      )}
    </span>
  )
}
