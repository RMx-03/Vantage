import { useState } from 'react';
import { supabase } from '../lib/supabase';

interface AnalyzeResponse {
    ticker: string;
    memo: string;
    approved: boolean;
}

export default function Terminal() {
    const [tickerInput, setTickerInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<AnalyzeResponse | null>(null);

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
        <div className="dark font-body text-on-background selection:bg-primary selection:text-on-primary">
            {/* TopAppBar Shell */}
            <header className="bg-[#0e0e0e] text-[#c6c6c7] font-['Inter'] font-normal docked flex items-center justify-center top-0 border-b border-[#191a1a] flat no shadows fixed w-full z-50">
                <div className="flex flex-col items-center pt-8 pb-4 w-full max-w-2xl mx-auto px-6">
                    <div className="flex items-center justify-between w-full">
                        <span className="text-2xl font-bold tracking-tighter text-[#c6c6c7]">Vantage</span>
                        <nav className="hidden md:flex gap-6">
                            <a className="text-[#c6c6c7] border-b border-[#c6c6c7] transition-opacity duration-150 py-1" href="#terminal">Terminal</a>
                            <a className="text-[#484848] hover:text-[#c6c6c7] transition-opacity duration-150 py-1" href="#portfolio">Portfolio</a>
                            <a className="text-[#484848] hover:text-[#c6c6c7] transition-opacity duration-150 py-1" href="#risk">Risk</a>
                        </nav>
                        <span className="hidden md:block text-xs font-label uppercase tracking-widest text-outline">Agentic Quant Terminal</span>
                    </div>
                </div>
            </header>

            {/* Main Content Canvas */}
            <main className="max-w-2xl mx-auto py-32 md:py-40 px-6 flex flex-col gap-12">
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

                {/* Footer Metric / "Atmospheric Glow" */}
                <footer className="mt-20 py-8 border-t border-outline-variant/20 flex flex-col gap-4 items-center">
                    <div className="bg-primary/5 px-6 py-2 border border-primary/20">
                        <span className="text-[10px] font-label text-primary uppercase tracking-[0.3em]">System Latency: 4ms | Nodes Active: 3</span>
                    </div>
                    <p className="text-[10px] text-outline-variant font-label">© 2026 VANTAGE QUANT SYSTEMS</p>
                </footer>
            </main>

            {/* SideNavBar (Hidden on Mobile) */}
            <aside className="hidden lg:flex fixed left-0 top-0 h-full w-64 bg-[#0e0e0e] flex-col border-r border-[#191a1a] z-40">
                <div className="p-8 flex flex-col gap-12 h-full">
                    <div className="flex flex-col">
                        <span className="text-xl font-bold text-[#c6c6c7] font-headline">Vantage</span>
                        <span className="text-[10px] font-label uppercase tracking-widest text-outline">Quant AI</span>
                    </div>
                    <nav className="flex flex-col gap-4">
                        <a className="flex items-center gap-4 p-3 text-[#c6c6c7] bg-[#191a1a] transition-colors duration-150 font-['Inter'] text-sm tracking-tight" href="#terminal">
                            <span className="material-symbols-outlined">terminal</span>
                            Terminal
                        </a>
                        <a className="flex items-center gap-4 p-3 text-[#484848] hover:bg-[#131313] hover:text-[#c6c6c7] transition-colors duration-150 font-['Inter'] text-sm tracking-tight" href="#portfolio">
                            <span className="material-symbols-outlined">account_balance_wallet</span>
                            Portfolio
                        </a>
                        <a className="flex items-center gap-4 p-3 text-[#484848] hover:bg-[#131313] hover:text-[#c6c6c7] transition-colors duration-150 font-['Inter'] text-sm tracking-tight" href="#risk">
                            <span className="material-symbols-outlined">query_stats</span>
                            Risk
                        </a>
                        <a className="flex items-center gap-4 p-3 text-[#484848] hover:bg-[#131313] hover:text-[#c6c6c7] transition-colors duration-150 font-['Inter'] text-sm tracking-tight" href="#settings">
                            <span className="material-symbols-outlined">settings</span>
                            Settings
                        </a>
                    </nav>
                    <div className="mt-auto border-t border-[#191a1a] pt-6 flex flex-col gap-2">
                        <span className="text-[10px] font-label text-outline uppercase tracking-widest">Active Model</span>
                        <span className="text-xs font-label text-primary">vantage-finance</span>
                    </div>
                </div>
            </aside>

            {/* BottomNavBar (Mobile) */}
            <nav className="lg:hidden fixed bottom-0 left-0 w-full z-50 flex justify-around items-center h-16 bg-[#0e0e0e] border-t border-[#191a1a]">
                <a className="flex flex-col items-center justify-center text-[#c6c6c7] bg-[#191a1a] p-2 flex-1 h-full scale-95 transition-transform" href="#terminal">
                    <span className="material-symbols-outlined">terminal</span>
                    <span className="font-['Space_Grotesk'] text-[10px] uppercase tracking-widest mt-1">Terminal</span>
                </a>
                <a className="flex flex-col items-center justify-center text-[#484848] p-2 flex-1 h-full hover:bg-[#131313] transition-transform" href="#portfolio">
                    <span className="material-symbols-outlined">account_balance_wallet</span>
                    <span className="font-['Space_Grotesk'] text-[10px] uppercase tracking-widest mt-1">Portfolio</span>
                </a>
                <a className="flex flex-col items-center justify-center text-[#484848] p-2 flex-1 h-full hover:bg-[#131313] transition-transform" href="#risk">
                    <span className="material-symbols-outlined">query_stats</span>
                    <span className="font-['Space_Grotesk'] text-[10px] uppercase tracking-widest mt-1">Risk</span>
                </a>
                <a className="flex flex-col items-center justify-center text-[#484848] p-2 flex-1 h-full hover:bg-[#131313] transition-transform" href="#settings">
                    <span className="material-symbols-outlined">settings</span>
                    <span className="font-['Space_Grotesk'] text-[10px] uppercase tracking-widest mt-1">Settings</span>
                </a>
            </nav>
        </div>
    );
}
