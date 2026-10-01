import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { resendVerification, verifyEmail } from '../lib/authClient';

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const { refreshUser } = useAuth();
  const prefersReducedMotion = useReducedMotion();

  const [status, setStatus] = useState<'verifying' | 'success' | 'error' | 'incomplete'>(
    token ? 'verifying' : 'incomplete'
  );
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [showResendForm, setShowResendForm] = useState(false);
  const [resendEmail, setResendEmail] = useState('');
  const [resendStatus, setResendStatus] = useState<string | null>(null);
  const [resending, setResending] = useState(false);

  useEffect(() => {
    if (!token) return;

    let active = true;
    verifyEmail(token)
      .then(() => {
        if (!active) return;
        setStatus('success');
        void refreshUser();
      })
      .catch((err: unknown) => {
        if (!active) return;
        setStatus('error');
        setErrorMessage(
          err instanceof Error ? err.message : 'This link is invalid or has expired.'
        );
      });

    return () => {
      active = false;
    };
  }, [token, refreshUser]);

  const handleResend = async (e: FormEvent) => {
    e.preventDefault();
    if (!resendEmail.trim()) return;
    setResending(true);
    try {
      await resendVerification(resendEmail.trim());
      setResendStatus('If that address can receive mail, a message is on its way.');
    } catch {
      setResendStatus('If that address can receive mail, a message is on its way.');
    } finally {
      setResending(false);
    }
  };

  return (
    <motion.div
      initial={prefersReducedMotion ? false : { opacity: 0, x: 8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className="dark font-body antialiased min-h-screen flex items-center justify-center p-6 bg-background text-on-surface selection:bg-primary selection:text-on-primary"
    >
      <div className="w-full max-w-md relative z-10">
        <Link
          to="/"
          className="group/home mb-5 inline-flex items-center gap-2 font-label text-xs text-on-surface-variant transition-colors duration-150 hover:text-on-surface focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary focus-visible:ring-offset-4 focus-visible:ring-offset-background"
        >
          <span
            aria-hidden="true"
            className={`material-symbols-outlined text-[16px] ${
              prefersReducedMotion
                ? ''
                : 'transition-transform duration-150 group-hover/home:-translate-x-1'
            }`}
          >
            arrow_back
          </span>
          <span>Return to overview</span>
        </Link>

        <div className="bg-surface-container border border-surface-variant p-8 md:p-12 relative overflow-hidden group">
          <div className="text-center mb-10 relative z-10">
            <h1 className="font-headline font-bold text-3xl tracking-tighter text-on-surface mb-2 uppercase">
              Vantage
            </h1>
            <p className="font-label text-sm text-on-surface-variant tracking-wider uppercase opacity-80">
              Email Verification
            </p>
          </div>

          <div className="space-y-6 relative z-10">
            {status === 'incomplete' && (
              <div className="p-4 border border-error bg-error/10 text-error text-xs font-label uppercase tracking-wider">
                This verification link is incomplete. Please check the URL in your email.
              </div>
            )}

            {status === 'verifying' && (
              <div className="p-4 border border-outline-variant bg-surface-container-low text-on-surface text-xs font-label uppercase tracking-wider text-center">
                Verifying address...
              </div>
            )}

            {status === 'success' && (
              <div className="space-y-6">
                <div className="p-4 border border-primary bg-primary/10 text-primary text-xs font-label uppercase tracking-wider">
                  Your address is confirmed. You now have full access to research tools.
                </div>
                <Link
                  to="/app"
                  className="w-full flex justify-center py-4 px-4 border border-transparent text-sm font-headline font-bold text-on-primary bg-primary hover:bg-surface-bright hover:text-primary hover:border-outline-variant transition-all duration-150 uppercase tracking-widest text-center"
                >
                  Enter Terminal
                </Link>
              </div>
            )}

            {status === 'error' && (
              <div className="space-y-6">
                <div className="p-4 border border-error bg-error/10 text-error text-xs font-label uppercase tracking-wider">
                  {errorMessage || 'This link is invalid or has expired.'}
                </div>

                {!showResendForm ? (
                  <button
                    type="button"
                    onClick={() => setShowResendForm(true)}
                    className="w-full flex justify-center py-4 px-4 border border-surface-variant text-sm font-headline font-bold text-on-surface bg-surface-container-high hover:bg-surface-bright hover:text-primary transition-all duration-150 uppercase tracking-widest"
                  >
                    Send a new link
                  </button>
                ) : (
                  <form onSubmit={handleResend} className="space-y-4">
                    {resendStatus && (
                      <div className="p-4 border border-primary bg-primary/10 text-primary text-xs font-label uppercase tracking-wider">
                        {resendStatus}
                      </div>
                    )}
                    <div className="space-y-1">
                      <label
                        className="block font-label text-xs uppercase tracking-widest text-on-surface-variant mb-2"
                        htmlFor="resend-email"
                      >
                        Email Address
                      </label>
                      <input
                        id="resend-email"
                        type="email"
                        required
                        value={resendEmail}
                        onChange={(e) => setResendEmail(e.target.value)}
                        placeholder="OPERATOR@VANTAGE.QUANT"
                        className="w-full bg-[#131313] border-0 border-b border-[#484848] text-[#c6c6c7] focus:ring-0 focus:border-primary px-4 py-3 text-sm font-body transition-all duration-200 placeholder:text-[#484848] outline-none"
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={resending}
                      className="w-full flex justify-center py-4 px-4 border border-transparent text-sm font-headline font-bold text-on-primary bg-primary hover:bg-surface-bright hover:text-primary transition-all duration-150 uppercase tracking-widest disabled:opacity-50"
                    >
                      {resending ? 'Sending...' : 'Request Link'}
                    </button>
                  </form>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="absolute -bottom-6 right-0 font-label text-[10px] text-surface-variant tracking-widest select-none pointer-events-none">
          SYS.AUTH.VERIFY // 0x0002
        </div>
      </div>
    </motion.div>
  );
}
