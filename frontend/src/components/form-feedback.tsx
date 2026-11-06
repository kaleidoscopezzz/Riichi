import { ApiError } from '@/services/api'
import { formatFieldErrors } from '@/lib/field-errors'

export function FormFeedback({ error, success }: { error?: Error | null; success?: string }) {
  if (error)
    return (
      <div className="form-feedback error" role="alert">
        <p>{error.message}</p>
        {error instanceof ApiError &&
          formatFieldErrors(error.fields).map((line, index) => <p key={index}>{line}</p>)}
      </div>
    )
  return success ? (
    <div className="form-feedback success" role="status">
      {success}
    </div>
  ) : null
}
