/** Task-scoped business tools and final monotonic denial for the bid profile. */
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-tools'
import { HarnessError } from '@deepseek-ai/dsh-llm'
import { randomUUID } from 'node:crypto'

export const name = 'bid-business-tools'
export const inject = ['tools', 'llm']

class BidDenied extends HarnessError {
  constructor(message: string) { super(message, 'BID_DENIED') }
}

/** Register only server-generated schemas; identities stay in this closure.
 * @param ctx - injected Harness plugin context.
 */
export async function apply(ctx: Context): Promise<void> {
  const api = process.env.BID_API_URL
  const token = process.env.BID_TASK_TOKEN
  if (!api || new URL(api).hostname !== '127.0.0.1' || !token) throw new BidDenied('Local task binding missing')
  const headers = { authorization: `Bearer ${token}`, 'content-type': 'application/json' }
  async function read(path: string, signal?: AbortSignal) {
    const response = await fetch(`${api}${path}`, { headers, signal: signal ?? null, redirect: 'error' })
    if (!response.ok) throw new BidDenied(await response.text())
    return response.json()
  }
  const manifest = await read('/internal/manifest')
  const schemas = await read('/internal/schemas')
  const allowed = new Set<string>(manifest.contract.allowed_tools)
  let finished = false
  ctx.tools.guard(exec => !allowed.has(exec.name) || finished
    ? { reason: 'This task only permits the assigned business tools.', info: {name: 'BidDenied', code: 'BID_DENIED'} }
    : undefined)
  ctx.on('llm/stream', async function* (options, next) {
    await read('/internal/manifest', options.signal)
    yield* next()
  })
  for (const tool of allowed) {
    ctx.tools.register({
      name: tool,
      description: tool === 'read_sources' ? '按来源编号读取本任务原文和完整条件。'
        : tool === 'save_candidate' ? '保存工程测试候选，不代表内容已验收。'
          : '固定本次候选文件哈希并结束提交。',
      parameters: schemas[tool],
      output: { schema: { type: 'object', additionalProperties: true },
        render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }] },
      async execute(args, exec) {
        const response = await fetch(`${api}/internal/tools`, {
          method: 'POST', headers, signal: exec.signal, redirect: 'error',
          body: JSON.stringify({ request_id: randomUUID(), tool, arguments: args }),
        })
        if (!response.ok) throw new BidDenied(await response.text())
        const value = await response.json()
        if (tool === 'finish_candidate') finished = true
        return value
      },
    })
  }
}
