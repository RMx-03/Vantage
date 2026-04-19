import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '../lib/supabase';

type Mode = 'login' | 'register';

export default function Auth() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setLoading(true);

    try {
      if (mode === 'login') {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        navigate('/app', { replace: true });
      } else {
        const { error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
        setInfo('Account created. Check your email to confirm before logging in.');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dark font-body antialiased min-h-screen flex items-center justify-center p-6 bg-background text-on-surface selection:bg-primary selection:text-on-primary">
      <div className="w-full max-w-md relative z-10">

        {/* Glassmorphic Card */}
        <div className="bg-surface-container/80 backdrop-blur-2xl border border-surface-variant p-8 md:p-12 shadow-[0_20px_50px_-12px_rgba(0,0,0,0.8)] relative overflow-hidden group">

          {/* Atmospheric glow */}
          <div className="absolute -bottom-24 -left-24 w-64 h-64 bg-primary/5 blur-[100px] pointer-events-none transition-opacity duration-1000 opacity-50 group-hover:opacity-100" />

          {/* Header */}
          <div className="text-center mb-10 relative z-10">
            <h1 className="font-headline font-bold text-3xl tracking-tighter text-on-surface mb-2 uppercase">
              Vantage
            </h1>
            <p className="font-label text-sm text-on-surface-variant tracking-wider uppercase opacity-80">
              Authenticate to initialize terminal.
            </p>
          </div>

          {/* Mode toggle */}
          <div className="flex p-1 bg-surface-container-lowest border border-surface-variant mb-8 relative z-10">
            <button
              type="button"
              onClick={() => { setMode('login'); setError(null); setInfo(null); }}
              className={`flex-1 py-3 text-sm font-headline font-medium transition-colors duration-200 ${
                mode === 'login'
                  ? 'text-on-surface bg-surface-bright'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              Login
            </button>
            <button
              type="button"
              onClick={() => { setMode('register'); setError(null); setInfo(null); }}
              className={`flex-1 py-3 text-sm font-headline font-medium transition-colors duration-200 ${
                mode === 'register'
                  ? 'text-on-surface bg-surface-bright'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              Create Account
            </button>
          </div>

          {/* Feedback messages */}
          {error && (
            <div className="mb-6 px-4 py-3 border border-error bg-error/10 text-error text-xs font-label uppercase tracking-wider relative z-10">
              {error}
            </div>
          )}
          {info && (
            <div className="mb-6 px-4 py-3 border border-primary bg-primary/10 text-primary text-xs font-label uppercase tracking-wider relative z-10">
              {info}
            </div>
          )}

          {/* Form */}
          <form className="space-y-6 relative z-10" onSubmit={handleSubmit}>
            {/* Email */}
            <div className="space-y-1">
              <label
                className="block font-label text-xs uppercase tracking-widest text-on-surface-variant mb-2"
                htmlFor="email"
              >
                Email Address
              </label>
              <div className="relative">
                <span className="absolute left-0 top-1/2 -translate-y-1/2 text-on-surface-variant material-symbols-outlined text-[18px]">
                  mail
                </span>
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="OPERATOR@VANTAGE.QUANT"
                  className="w-full bg-transparent border-0 border-b border-outline-variant text-on-surface focus:ring-0 focus:border-primary px-0 pl-8 py-3 text-sm font-body transition-colors duration-200 placeholder:text-surface-variant outline-none"
                />
              </div>
            </div>

            {/* Password */}
            <div className="space-y-1">
              <label
                className="block font-label text-xs uppercase tracking-widest text-on-surface-variant mb-2"
                htmlFor="password"
              >
                Security Credential
              </label>
              <div className="relative">
                <span className="absolute left-0 top-1/2 -translate-y-1/2 text-on-surface-variant material-symbols-outlined text-[18px]">
                  key
                </span>
                <input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full bg-transparent border-0 border-b border-outline-variant text-on-surface focus:ring-0 focus:border-primary px-0 pl-8 py-3 text-sm font-body transition-colors duration-200 placeholder:text-surface-variant outline-none"
                />
              </div>
            </div>

            {/* Retain session / Forgot (login mode only) */}
            {mode === 'login' && (
              <div className="flex items-center justify-between pt-2">
                <div className="flex items-center">
                  <input
                    id="remember-me"
                    name="remember-me"
                    type="checkbox"
                    className="h-4 w-4 rounded-none border-outline-variant bg-surface-container-lowest text-primary focus:ring-primary focus:ring-offset-background"
                  />
                  <label
                    htmlFor="remember-me"
                    className="ml-2 block text-xs font-label uppercase tracking-wider text-on-surface-variant"
                  >
                    Retain Session
                  </label>
                </div>
                <a
                  href="#"
                  className="font-label text-xs uppercase tracking-wider text-primary hover:text-on-surface transition-colors duration-150"
                >
                  Forgot Credential?
                </a>
              </div>
            )}

            {/* Submit */}
            <div className="pt-6">
              <button
                type="submit"
                disabled={loading}
                className="w-full flex justify-center py-4 px-4 border border-transparent text-sm font-headline font-bold text-on-primary bg-primary hover:bg-surface-bright hover:text-primary hover:border-outline-variant transition-all duration-150 uppercase tracking-widest relative overflow-hidden group/btn disabled:opacity-50"
              >
                <span className="relative z-10 flex items-center gap-2">
                  {loading
                    ? 'Processing...'
                    : mode === 'login'
                    ? 'Access Terminal'
                    : 'Create Account'}
                  {!loading && (
                    <span className="material-symbols-outlined text-[16px] transition-transform duration-200 group-hover/btn:translate-x-1">
                      arrow_forward
                    </span>
                  )}
                </span>
              </button>
            </div>
          </form>
        </div>

        {/* Ambient decorative label */}
        <div className="absolute -bottom-6 right-0 font-label text-[10px] text-surface-variant tracking-widest select-none pointer-events-none">
          SYS.AUTH.REQ // 0x0001
        </div>
      </div>
    </div>
  );
}
