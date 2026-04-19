import { useState } from 'react';
import { supabase } from '../lib/supabase';
import { useAuth } from '../context/AuthContext';
import UserSettingsPanel from '../components/UserSettingsPanel';

interface AnalyzeResponse {
    ticker: string;
    memo: string;
    approved: boolean;
}

export default function Terminal() {
    const [tickerInput, setTickerInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<AnalyzeResponse | null>(null);
    const [showSettings, setShowSettings] = useState(false);
    const { signOut } = useAuth();

    const handleAnalyze = async () => {
        if (!tickerInput.trim()) return;
        setLoading(true);
        setResult(null);

        try {
            // Retrieve the active session to obtain the JWT.
            const { data: { session } } = await supabase.auth.getSession();
            const token = session?.access_token;

            const resp = await fetch('http://localhost:8000/api/v1/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
                },
                body: JSON.stringify({ ticker: tickerInput.trim() })
            });

            if (!resp.ok) {
                console.error("API Error", await resp.text());
                // Handle error state if needed
            } else {
                const data = await resp.json();
                setResult(data);
            }
        } catch (error) {
            console.error("Fetch error", error);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="dark font-body text-on-background selection:bg-primary selection:text-on-primary h-screen overflow-hidden flex flex-col bg-[#0e0e0e]">
            {/* TopAppBar Shell */}
            <header className="bg-[#0e0e0e] text-[#c6c6c7] font-['Inter'] font-normal border-b border-[#191a1a] w-full z-50 shrink-0">
                <div className="w-full max-w-7xl mx-auto px-6 flex items-center justify-between h-16">
                    <div className="flex items-center gap-2">
                        <span className="text-xl font-bold tracking-tighter text-[#c6c6c7]">Vantage</span>
                        <span className="text-[10px] font-label uppercase tracking-widest text-outline hidden sm:block">Quant AI</span>
                    </div>
                    
                    <div className="flex flex-col items-center">
                        <span className="text-[10px] font-label uppercase tracking-[0.3em] text-primary animate-pulse">
                            {showSettings ? 'System Settings' : 'Analytical Terminal'}
                        </span>
                    </div>
                    
                    <button 
                        onClick={() => signOut()}
                        className="flex items-center gap-2 text-[#484848] hover:text-error transition-colors font-label text-[10px] uppercase tracking-widest group"
                    >
                        <span className="hidden sm:block group-hover:pr-1 transition-all">Sign Out</span>
                        <span className="material-symbols-outlined text-sm">logout</span>
                    </button>
                </div>
            </header>

            <div className="flex-1 flex overflow-hidden relative">
                {/* SideNavBar (Hidden on Mobile) */}
                <aside className="hidden lg:flex w-64 bg-[#0e0e0e] flex-col border-r border-[#191a1a] z-40 shrink-0">
                    <div className="p-8 flex flex-col gap-12 h-full">
                        <nav className="flex flex-col gap-4">
                            <button 
                                onClick={() => setShowSettings(false)}
                                className={`flex items-center gap-4 p-3 w-full transition-colors duration-150 font-['Inter'] text-sm tracking-tight ${!showSettings ? 'text-[#c6c6c7] bg-[#191a1a]' : 'text-[#484848] hover:bg-[#131313] hover:text-[#c6c6c7]'}`}
                            >
                                <span className="material-symbols-outlined">terminal</span>
                                Terminal
                            </button>
                            <button className="flex items-center gap-4 p-3 text-[#484848] hover:bg-[#131313] hover:text-[#c6c6c7] transition-colors duration-150 font-['Inter'] text-sm tracking-tight">
                                <span className="material-symbols-outlined">account_balance_wallet</span>
                                Portfolio
                            </button>
                            <button className="flex items-center gap-4 p-3 text-[#484848] hover:bg-[#131313] hover:text-[#c6c6c7] transition-colors duration-150 font-['Inter'] text-sm tracking-tight">
                                <span className="material-symbols-outlined">query_stats</span>
                                Risk
                            </button>
                            <button 
                                onClick={() => setShowSettings(true)}
                                className={`flex items-center gap-4 p-3 w-full transition-colors duration-150 font-['Inter'] text-sm tracking-tight ${showSettings ? 'text-[#c6c6c7] bg-[#191a1a]' : 'text-[#484848] hover:bg-[#131313] hover:text-[#c6c6c7]'}`}
                            >
                                <span className="material-symbols-outlined">settings</span>
                                Settings
                            </button>
                        </nav>
                        <div className="mt-auto border-t border-[#191a1a] pt-6 flex flex-col gap-2">
                            <span className="text-[10px] font-label text-outline uppercase tracking-widest">Active Model</span>
                            <span className="text-xs font-label text-primary">vantage-finance</span>
                        </div>
                    </div>
                </aside>

                {/* Main Content Area */}
                <main className="flex-1 overflow-y-auto w-full transition-all duration-300">
                    <div className="max-w-4xl mx-auto py-12 md:py-24 px-6 flex flex-col gap-12">
                        {showSettings ? (
                            <UserSettingsPanel />
                        ) : (
                            <>
                                {/* Hero Section */}
                                <section className="flex flex-col gap-2">
                                    <h1 className="text-4xl font-extrabold tracking-tighter text-primary">Vantage.</h1>
                                    <p className="text-on-surface-variant font-label tracking-wide uppercase text-sm">Agentic Quant Terminal</p>
                                </section>

                                {/* Search / Input Area */}
                                <section className="flex flex-col gap-6">
                                    <div className="flex flex-col md:flex-row gap-0">
                                        <div className="flex-1 bg-surface-container-low border border-outline-variant focus-within:border-primary transition-colors duration-150 group">
                                            <input 
                                                className="w-full bg-transparent border-none focus:outline-none focus:ring-0 text-on-surface font-label p-4 placeholder:text-outline-variant" 
                                                placeholder="Enter ticker..." 
                                                type="text"
                                                value={tickerInput}
                                                onChange={(e) => setTickerInput(e.target.value)}
                                                onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
                                            />
                                        </div>
                                        <button 
                                            onClick={handleAnalyze}
                                            disabled={loading}
                                            className="bg-primary text-on-primary font-bold px-8 py-4 hover:opacity-90 transition-opacity uppercase tracking-widest text-xs disabled:opacity-50"
                                        >
                                            Analyze
                                        </button>
                                    </div>
                                    <div className="flex gap-4 overflow-x-auto no-scrollbar">
                                        <span className="text-[10px] font-label text-outline uppercase tracking-tighter">Recent:</span>
                                        <span className="text-[10px] font-label text-primary uppercase tracking-tighter cursor-pointer" onClick={() => setTickerInput('NVDA')}>$NVDA</span>
                                        <span className="text-[10px] font-label text-on-surface-variant uppercase tracking-tighter cursor-pointer" onClick={() => setTickerInput('AAPL')}>$AAPL</span>
                                        <span className="text-[10px] font-label text-on-surface-variant uppercase tracking-tighter cursor-pointer" onClick={() => setTickerInput('TSLA')}>$TSLA</span>
                                    </div>
                                </section>

                                {/* Loading State */}
                                {loading && (
                                    <section className="flex items-center gap-4 py-4">
                                        <div className="w-2 h-2 bg-primary animate-pulse"></div>
                                        <p className="text-outline text-xs font-label uppercase tracking-[0.2em] animate-pulse">Running Agentic Analysis...</p>
                                    </section>
                                )}

                                {/* Results Card */}
                                {!loading && result && (
                                    <section className="flex flex-col gap-8">
                                        <div className="bg-surface-container-low border border-outline-variant p-8 flex flex-col gap-8">
                                            <div className="flex justify-between items-start">
                                                <div className="flex flex-col gap-1">
                                                    <span className="text-4xl font-label font-bold text-on-surface">${result.ticker.toUpperCase()}</span>
                                                    <span className="text-xs font-label text-outline uppercase tracking-widest">QUANTITATIVE ANALYSIS</span>
                                                </div>
                                                <div className={`px-3 py-1 flex items-center gap-2 border ${result.approved ? 'border-[#4ade80] bg-[#4ade80]/10' : 'border-error bg-error/10'}`}>
                                                    <span className={`material-symbols-outlined text-[14px] ${result.approved ? 'text-[#4ade80]' : 'text-error'}`}>
                                                        {result.approved ? 'check_circle' : 'cancel'}
                                                    </span>
                                                    <span className={`text-[10px] font-label uppercase tracking-widest font-bold ${result.approved ? 'text-[#4ade80]' : 'text-error'}`}>
                                                        {result.approved ? 'Trade Approved' : 'Trade Rejected'}
                                                    </span>
                                                </div>
                                            </div>
                                            
                                            <div className="flex flex-col gap-4 py-6 border-t border-outline-variant/30">
                                                <h3 className="text-xs font-bold font-headline uppercase tracking-widest text-primary flex items-center gap-2">
                                                    <span className="material-symbols-outlined text-sm">smart_toy</span>
                                                    AI Investment Memo
                                                </h3>
                                                <p className="text-on-surface-variant text-sm leading-relaxed font-body">
                                                    {result.memo}
                                                </p>
                                            </div>
                                        </div>
                                    </section>
                                )}

                                {/* Footer Metric */}
                                <footer className="mt-20 py-8 border-t border-outline-variant/20 flex flex-col gap-4 items-center">
                                    <div className="bg-primary/5 px-6 py-2 border border-primary/20">
                                        <span className="text-[10px] font-label text-primary uppercase tracking-[0.3em]">System Latency: 4ms | Nodes Active: 3</span>
                                    </div>
                                    <p className="text-[10px] text-outline-variant font-label">© 2026 VANTAGE QUANT SYSTEMS</p>
                                </footer>
                            </>
                        )}
                    </div>
                </main>
            </div>

            {/* BottomNavBar (Mobile) */}
            <nav className="lg:hidden w-full z-50 flex justify-around items-center h-16 bg-[#0e0e0e] border-t border-[#191a1a] shrink-0">
                <button 
                    onClick={() => setShowSettings(false)}
                    className={`flex flex-col items-center justify-center p-2 flex-1 h-full transition-transform ${!showSettings ? 'text-[#c6c6c7] bg-[#191a1a]' : 'text-[#484848] hover:bg-[#131313]'}`}
                >
                    <span className="material-symbols-outlined">terminal</span>
                    <span className="font-['Space_Grotesk'] text-[10px] uppercase tracking-widest mt-1">Terminal</span>
                </button>
                <button className="flex flex-col items-center justify-center text-[#484848] p-2 flex-1 h-full hover:bg-[#131313] transition-transform">
                    <span className="material-symbols-outlined">account_balance_wallet</span>
                    <span className="font-['Space_Grotesk'] text-[10px] uppercase tracking-widest mt-1">Portfolio</span>
                </button>
                <button className="flex flex-col items-center justify-center text-[#484848] p-2 flex-1 h-full hover:bg-[#131313] transition-transform">
                    <span className="material-symbols-outlined">query_stats</span>
                    <span className="font-['Space_Grotesk'] text-[10px] uppercase tracking-widest mt-1">Risk</span>
                </button>
                <button 
                    onClick={() => setShowSettings(true)}
                    className={`flex flex-col items-center justify-center p-2 flex-1 h-full transition-transform ${showSettings ? 'text-[#c6c6c7] bg-[#191a1a]' : 'text-[#484848] hover:bg-[#131313]'}`}
                >
                    <span className="material-symbols-outlined">settings</span>
                    <span className="font-['Space_Grotesk'] text-[10px] uppercase tracking-widest mt-1">Settings</span>
                </button>
            </nav>
        </div>
    );
}
