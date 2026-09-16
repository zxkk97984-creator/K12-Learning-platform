import { useEffect, useRef } from 'react'

/**
 * Python 代码编辑器（CodeMirror 6）。
 *
 * 库选型与配置沿用 dai-experiment-platform 的 `CodeCell.vue`：同一套
 * `@codemirror/*` 包、同一组扩展（行号、活动行高亮、括号匹配、Python 语法、
 * `indentWithTab`）。CodeMirror 本身与框架无关，这里只是把它包成 React 组件。
 *
 * 相对 dai 实现**有意修正的两点**（见 .audit/dai-frontend-and-api.md）：
 * 1. dai 在外部 source 变化时做整篇 replace，会清空撤销栈。这里只在内容真的
 *    不同才 dispatch，且用 `EditorView.updateListener` 区分「用户编辑」与
 *    「外部同步」，避免外部同步把学生的编辑状态冲掉。
 * 2. dai 在 readonly 切换时销毁重建编辑器（会丢失滚动位置与撤销历史）。
 *    这里通过 `Compartment` 动态重配，不重建实例。
 *
 * 另外补了 dai 没有的 **Ctrl/Cmd + Enter 运行** 快捷键。
 */

interface CodeEditorProps {
  value: string
  onChange: (value: string) => void
  /** 触发行内运行（Ctrl/Cmd + Enter） */
  onRun?: () => void
  readOnly?: boolean
  minHeight?: string
  ariaLabel?: string
}

export function CodeEditor({
  value,
  onChange,
  onRun,
  readOnly = false,
  minHeight = '320px',
  ariaLabel = '代码编辑器',
}: CodeEditorProps) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const viewRef = useRef<import('@codemirror/view').EditorView | null>(null)
  const readOnlyCompartmentRef = useRef<{
    compartment: import('@codemirror/state').Compartment
    view: import('@codemirror/view').EditorView
  } | null>(null)
  // 保持在 ref 里，避免因回调变化重建编辑器
  const onChangeRef = useRef(onChange)
  const onRunRef = useRef(onRun)
  const syncingRef = useRef(false)

  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  useEffect(() => {
    onRunRef.current = onRun
  }, [onRun])

  useEffect(() => {
    let disposed = false
    let view: import('@codemirror/view').EditorView | null = null

    const setup = async () => {
      // 动态 import：编辑器只在 CodeLab 页面加载，不进入主 bundle
      const [
        { EditorView, keymap, lineNumbers, highlightActiveLine, drawSelection, placeholder },
        { EditorState, Compartment },
        { python },
        { defaultKeymap, history, historyKeymap, indentWithTab },
        { bracketMatching, indentOnInput, syntaxHighlighting, defaultHighlightStyle },
      ] = await Promise.all([
        import('@codemirror/view'),
        import('@codemirror/state'),
        import('@codemirror/lang-python'),
        import('@codemirror/commands'),
        import('@codemirror/language'),
      ])
      if (disposed || !hostRef.current) return

      const readOnlyCompartment = new Compartment()

      const runKeymap = keymap.of([
        {
          key: 'Mod-Enter',
          preventDefault: true,
          run: () => {
            onRunRef.current?.()
            return true
          },
        },
        indentWithTab,
      ])

      const state = EditorState.create({
        doc: value,
        extensions: [
          lineNumbers(),
          highlightActiveLine(),
          drawSelection(),
          history(),
          bracketMatching(),
          indentOnInput(),
          syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
          // 先于 Python 语言扩展加载也不影响：这里只提供语言支持
          python(),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          runKeymap,
          placeholder('在这里编写你的 Python 代码…'),
          readOnlyCompartment.of(EditorState.readOnly.of(readOnly)),
          EditorView.updateListener.of((update) => {
            if (!update.docChanged) return
            if (syncingRef.current) return // 外部同步不算学生编辑
            onChangeRef.current(update.state.doc.toString())
          }),
          // 无障碍：把名称挂到 CodeMirror 自己的 contenteditable 上。
          EditorView.contentAttributes.of({ 'aria-label': ariaLabel }),
          EditorView.theme({
            '&': { fontSize: '13px', minHeight },
            '.cm-content': { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' },
            '.cm-scroller': { minHeight },
          }),
        ],
      })

      view = new EditorView({ state, parent: hostRef.current })
      viewRef.current = view
      readOnlyCompartmentRef.current = { compartment: readOnlyCompartment, view }
    }

    void setup()
    return () => {
      disposed = true
      view?.destroy()
      viewRef.current = null
      readOnlyCompartmentRef.current = null
    }
    // 仅在挂载时创建；value/readOnly 由下面的 effect 增量同步
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 外部 value 变化 → 同步进编辑器（不重建、不污染撤销栈标记）
  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    const current = view.state.doc.toString()
    if (current === value) return
    syncingRef.current = true
    try {
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: value },
      })
    } finally {
      syncingRef.current = false
    }
  }, [value])

  // readOnly 变化 → 动态重配，不销毁实例
  useEffect(() => {
    const entry = readOnlyCompartmentRef.current
    if (!entry) return
    void import('@codemirror/state').then(({ EditorState }) => {
      entry.view.dispatch({
        effects: entry.compartment.reconfigure(EditorState.readOnly.of(readOnly)),
      })
    })
  }, [readOnly])

  return (
    <div
      ref={hostRef}
      data-testid="codelab-editor"
      className="overflow-hidden rounded-[10px] border border-border bg-surface"
    />
  )
}
