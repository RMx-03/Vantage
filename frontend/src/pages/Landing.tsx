import { useNavigate } from 'react-router-dom';

export default function Landing() {
    const navigate = useNavigate();

    return (
        <div className="dark bg-background text-on-background font-body antialiased min-h-screen">
            {/* TopNavBar */}
            <nav className="bg-[#0e0e0e] border-b border-[#191a1a] fixed top-0 left-0 right-0 z-50">
                <div className="flex justify-between items-center py-6 w-full max-w-2xl mx-auto px-6">
                    <span className="text-2xl font-bold tracking-tighter text-[#c6c6c7] font-headline">Vantage</span>
                    <div className="flex items-center gap-6">
                        <button 
                            onClick={() => navigate('/app')}
                            className="bg-primary text-on-primary px-4 py-2 font-label text-sm font-bold hover:opacity-80 transition-opacity duration-150">
                            Launch Terminal
                        </button>
                    </div>
                </div>
            </nav>
            <main className="w-full max-w-2xl mx-auto px-6 pt-32">
                {/* Hero Section */}
                <section className="py-32 flex flex-col items-center text-center">
                    <h1 className="text-5xl md:text-6xl font-extrabold tracking-tighter text-primary leading-none mb-8 font-headline">
                        Wall Street Intelligence. Local Architecture.
                    </h1>
                    <p className="text-on-surface-variant font-label text-lg leading-relaxed max-w-lg mb-12">
                        A fully localized, multi-agent AI platform for event-driven quantitative financial research. Zero cloud costs. Total privacy.
                    </p>
                    {/* Hero CTAs */}
                    <div className="flex flex-col sm:flex-row gap-4 w-full sm:w-auto">
                        <button 
                            onClick={() => navigate('/app')}
                            className="bg-primary text-on-primary font-label px-8 py-4 font-bold transition-all duration-300 hover:shadow-[0_0_20px_rgba(198,198,199,0.2)]">
                            Initialize Terminal
                        </button>
                        <button className="border border-outline-variant text-primary font-label px-8 py-4 hover:bg-surface-container transition-colors duration-150">
                            View Architecture
                        </button>
                    </div>
                </section>
                {/* Visual Anchor: Atmospheric Glow */}
                <div className="relative w-full h-px bg-outline-variant/20 mb-24">
                    <div className="absolute inset-0 bg-primary/10 blur-xl h-20 -top-10"></div>
                </div>
                {/* Features Grid */}
                <section className="grid grid-cols-1 gap-4 mb-32">
                    {/* Feature 1 */}
                    <div className="bg-surface-container p-8 border border-outline-variant/20 group hover:border-outline-variant transition-colors duration-300">
                        <div className="flex flex-col gap-4">
                            <span className="material-symbols-outlined text-primary text-3xl">hub</span>
                            <div>
                                <h3 className="text-primary font-headline font-bold text-xl mb-2">Multi-Agent Orchestration</h3>
                                <p className="text-on-surface-variant text-sm font-label leading-relaxed">
                                    Autonomous LangGraph workflow that scales from news scraping to deep sentiment analysis and risk calculation.
                                </p>
                            </div>
                        </div>
                    </div>
                    {/* Feature 2 */}
                    <div className="bg-surface-container p-8 border border-outline-variant/20 group hover:border-outline-variant transition-colors duration-300">
                        <div className="flex flex-col gap-4">
                            <span className="material-symbols-outlined text-primary text-3xl">memory</span>
                            <div>
                                <h3 className="text-primary font-headline font-bold text-xl mb-2">Local LLM Inference</h3>
                                <p className="text-on-surface-variant text-sm font-label leading-relaxed">
                                    Leverage fine-tuned Small Language Models (SLM) served via Ollama. Institutional intelligence without the cloud subscription.
                                </p>
                            </div>
                        </div>
                    </div>
                    {/* Feature 3 */}
                    <div className="bg-surface-container p-8 border border-outline-variant/20 group hover:border-outline-variant transition-colors duration-300">
                        <div className="flex flex-col gap-4">
                            <span className="material-symbols-outlined text-primary text-3xl">analytics</span>
                            <div>
                                <h3 className="text-primary font-headline font-bold text-xl mb-2">QuantRisk Guardrails</h3>
                                <p className="text-on-surface-variant text-sm font-label leading-relaxed">
                                    Real-time sentiment-to-volatility mapping ensuring trade approvals only trigger when signal-to-noise ratios are peak.
                                </p>
                            </div>
                        </div>
                    </div>
                </section>
                {/* Product Preview (Contextual Decorative) */}
                <section className="mb-32">
                    <div className="bg-surface-container-low border border-outline-variant/20 p-1">
                        <img className="w-full grayscale contrast-125 opacity-80" alt="Vantage Terminal interface showing real-time LangGraph agent state transitions and financial analysis memos" src="https://lh3.googleusercontent.com/aida-public/AB6AXuCbJMr9N71GEdkiGPBkXwp7tyI_23YpO9ChnoPGNydYuZQ1osXdzVoYXUYzyDTn89szN15duSPVQBs-7_Nnaq5LqnlG-1_zlN_ySoNtX28Wd9N_gf08C8qVTiSXms1P7lVOHpqaml_ReerCVsU39UYo6zwlWvnNJgMq3LiGpP3uS7QWfNA_WWbQV7wW0mn86Tthh3qFS5ie4h8FfvKEu1KYX3Y5GHidXiqDOV_9WRxIfcDCfJ4Zsi8frTgBIKko5voQFz-5YlPZhS1O"/>
                    </div>
                </section>
            </main>
            {/* Footer */}
            <footer className="bg-[#0e0e0e] border-t border-[#191a1a] py-12">
                <div className="flex flex-col items-center gap-4 w-full max-w-2xl mx-auto px-6">
                    <p className="font-['Inter'] text-xs tracking-tight text-[#484848]">© 2024 Vantage. Wall Street Intelligence. Local Execution.</p>
                    <div className="flex gap-6">
                        <a className="text-[#484848] text-xs font-['Inter'] hover:text-[#c6c6c7] transition-colors" href="#">Documentation</a>
                        <a className="text-[#484848] text-xs font-['Inter'] hover:text-[#c6c6c7] transition-colors" href="#">Privacy</a>
                        <a className="text-[#484848] text-xs font-['Inter'] hover:text-[#c6c6c7] transition-colors" href="#">Terms</a>
                    </div>
                </div>
            </footer>
        </div>
    );
}
