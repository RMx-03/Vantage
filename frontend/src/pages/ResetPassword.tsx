import { useState } from 'react';
import type { FormEvent } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { Link, useSearchParams } from 'react-router-dom';
import { resetPassword } from '../lib/authClient';

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const prefersReducedMotion = useReducedMotion();

  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setError(null);
    setLoading(true);

    try {
      await resetPassword(token, password);
      setSuccess(true);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : 'This link is invalid or has expired.'
      );
    } finally {
      setLoading(false);
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
              Reset Security Credential
            </p>
          </div>

          <div className="space-y-6 relative z-10">
            {!token ? (
              <div className="p-4 border border-error bg-error/10 text-error text-xs font-label uppercase tracking-wider">
                This reset link is incomplete. Please check the URL in your email.
              </div>
            ) : success ? (
              <div className="space-y-6">
                <div className="p-4 border border-primary bg-primary/10 text-primary text-xs font-label uppercase tracking-wider">
                  Your password has been changed. Sign in again with your new credential.
                </div>
                <Link
                  to="/auth"
                  className="w-full flex justify-center py-4 px-4 border border-transparent text-sm font-headline font-bold text-on-primary bg-primary hover:bg-surface-bright hover:text-primary transition-all duration-150 uppercase tracking-widest text-center"
                >
                  Sign in
                </Link>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-6">
                {error && (
                  <div className="p-4 border border-error bg-error/10 text-error text-xs font-label uppercase tracking-wider">
                    {error}
                  </div>
                )}

                <div className="space-y-1">
                  <label
                    className="block font-label text-xs uppercase tracking-widest text-on-surface-variant mb-2"
                    htmlFor="new-password"
                  >
                    New Security Credential
                  </label>
                  <div className="relative">
                    <span className="absolute left-0 top-1/2 -translate-y-1/2 text-on-surface-variant material-symbols-outlined text-[18px]">
                      key
                    </span>
                    <input
                      id="new-password"
                      type="password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••••••"
                      className="w-full bg-[#131313] border-0 border-b border-[#484848] text-[#c6c6c7] focus:ring-0 focus:border-primary px-4 pl-10 py-4 text-sm font-body transition-all duration-200 placeholder:text-[#484848] outline-none"
                    />
                  </div>
                  <p className="font-label text-[10px] uppercase tracking-wider text-on-surface-variant mt-2 opacity-70">
                    At least 12 characters. Avoid common passwords and your own address.
                  </p>
                </div>

                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full flex justify-center py-4 px-4 border border-transparent text-sm font-headline font-bold text-on-primary bg-primary hover:bg-surface-bright hover:text-primary transition-all duration-150 uppercase tracking-widest disabled:opacity-50"
                  >
                    {loading ? 'Updating...' : 'Update Credential'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>

        <div className="absolute -bottom-6 right-0 font-label text-[10px] text-surface-variant tracking-widest select-none pointer-events-none">
          SYS.AUTH.RESET // 0x0003
        </div>
      </div>
    </motion.div>
  );
}
