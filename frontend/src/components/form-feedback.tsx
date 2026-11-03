import { ApiError } from '@/services/api'

export function FormFeedback({ error, success }: { error?: Error | null; success?: string }) {
  if (error)
    return (
      <div className="form-feedback error" role="alert">
        <p>{error.message}</p>
        {error instanceof ApiError &&
          Object.entries(error.fields).map(([field, messages]) => (
            <p key={field}>
              {(
                {
                  username: '用户名',
                  nickname: '选手昵称',
                  password: '密码',
                  password_confirm: '确认密码',
                  machine_no: '设备编号',
                  name: '名称',
                  location: '设备位置',
                  description: '备注',
                  status: '状态',
                  round_count: '总轮数',
                  starting_points: '开局点数',
                  return_points: '返还原点',
                  uma: 'Uma',
                  participant_ids: '参赛名单',
                  round_number: '轮次',
                  machine_id: '物理设备',
                  reason: '释放说明',
                } as Record<string, string>
              )[field] || field}
              ：{Array.isArray(messages) ? messages.join(' ') : String(messages)}
            </p>
          ))}
      </div>
    )
  return success ? (
    <div className="form-feedback success" role="status">
      {success}
    </div>
  ) : null
}
