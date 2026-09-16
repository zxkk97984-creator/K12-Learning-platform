import type {
  CodeLabService,
  CodeReview,
  CodeRun,
  CodeTask,
  CodeTaskListItem,
} from './codelab-service'
import { apiRequest } from './http'

/**
 * CodeLab 客户端。
 *
 * 评审（requestReview）是同步调用：后端把 Docker 判题 + 一次 LLM 调用放在
 * 同一个请求里完成（移出事件循环），因此这里可能等待数十秒 —— 前端在等待期间
 * 必须显示明确的进度状态。刻意不走后台队列，避免依赖霜铃目前不稳的 Worker 启动链路。
 */
export class ApiCodeLabService implements CodeLabService {
  listTasks(): Promise<CodeTaskListItem[]> {
    return apiRequest<CodeTaskListItem[]>('/codelab/tasks')
  }

  getTask(taskId: string): Promise<CodeTask> {
    return apiRequest<CodeTask>(`/codelab/tasks/${encodeURIComponent(taskId)}`)
  }

  runCode(taskId: string, code: string): Promise<CodeRun> {
    return apiRequest<CodeRun>('/codelab/runs', {
      method: 'POST',
      body: { task_id: taskId, code },
    })
  }

  requestReview(runId: string): Promise<CodeReview> {
    return apiRequest<CodeReview>('/codelab/reviews', {
      method: 'POST',
      body: { run_id: runId },
    })
  }

  getReview(reviewId: string): Promise<CodeReview> {
    return apiRequest<CodeReview>(`/codelab/reviews/${encodeURIComponent(reviewId)}`)
  }
}
