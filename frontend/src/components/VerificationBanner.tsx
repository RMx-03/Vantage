import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { resendVerification } from '../lib/authClient';

export default function VerificationBanner() {
  const { user } = useAuth();
  const [resending, setResending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!user || user.email_verified) {
    return null;
  }

  const handleResend = async () => {
    setResending(true);
    setError(null);
    try {
      await resendVerification(user.email);
      setSent(true);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : 'Failed to send verification email.'
      );
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="w-full bg-surface-container-high border-b border-primary/40 px-5 py-3 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs font-label">
      <div className="flex items-center gap-2 text-on-surface">
        <span
          aria-hidden="true"
          className="material-symbols-outlined text-[18px] text-primary shrink-0"
        >
          mail
        </span>
        <span>
          Please confirm your email address ({user.email}). Creating and executing research runs requires a verified account.
        </span>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        {sent ? (
          <span className="text-primary uppercase tracking-wider font-semibold">
            Verification email sent. Check your inbox.
          </span>
        ) : error ? (
          <span className="text-error uppercase tracking-wider font-semibold">
            {error}
          </span>
        ) : (
          <button
            type="button"
            onClick={handleResend}
            disabled={resending}
            className="px-3 py-1.5 bg-primary text-on-primary font-bold uppercase tracking-wider hover:bg-surface-bright hover:text-primary transition-colors disabled:opacity-50"
          >
            {resending ? 'Sending...' : 'Resend Verification'}
          </button>
        )}
      </div>
    </div>
  );
}
