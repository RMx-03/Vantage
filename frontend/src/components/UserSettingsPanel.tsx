import { useState } from 'react';
import { useAuth } from '../context/AuthContext';

type SettingsTab = 'profile' | 'preferences' | 'history';

export default function UserSettingsPanel() {
    const { user, signOut } = useAuth();
    const [activeTab, setActiveTab] = useState<SettingsTab>('profile');
    
    const handleLogout = async () => {
        await signOut();
    };

    return (
        <div className="w-full flex flex-col gap-12 pb-24">
            {/* Section Header with Tabs */}
            <div className="space-y-8 border-b border-[#191a1a] pb-6">
                <div>
                    <h1 className="text-3xl font-headline tracking-tight text-[#e7e5e4]">System Configurations</h1>
                    <p className="text-[#acabaa] font-body text-sm">Manage terminal access and local endpoints.</p>
                </div>
                
                {/* Internal Tabs */}
                <div className="flex gap-8">
                    <button 
                        onClick={() => setActiveTab('profile')}
                        className={`font-label text-[11px] uppercase tracking-widest pb-2 transition-colors ${activeTab === 'profile' ? 'text-primary border-b border-primary' : 'text-[#484848] hover:text-[#c6c6c7]'}`}
                    >
                        Profile
                    </button>
                    <button 
                        onClick={() => setActiveTab('preferences')}
                        className={`font-label text-[11px] uppercase tracking-widest pb-2 transition-colors ${activeTab === 'preferences' ? 'text-primary border-b border-primary' : 'text-[#484848] hover:text-[#c6c6c7]'}`}
                    >
                        Preferences
                    </button>
                    <button 
                        onClick={() => setActiveTab('history')}
                        className={`font-label text-[11px] uppercase tracking-widest pb-2 transition-colors ${activeTab === 'history' ? 'text-primary border-b border-primary' : 'text-[#484848] hover:text-[#c6c6c7]'}`}
                    >
                        History
                    </button>
                </div>
            </div>
            
            {activeTab === 'profile' && (
                <>
                    {/* Profile / Account Details Block */}
                    <section className="bg-[#191a1a] p-8 space-y-8">
                        <h3 className="font-label text-xs uppercase tracking-widest text-[#acabaa] mb-6 border-b border-[#131313] pb-2">Account Verification</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                            {/* Read-only Email */}
                            <div className="space-y-2">
                                <label className="font-label text-[11px] uppercase tracking-wider text-[#767575] block">Active User Directive</label>
                                <div className="w-full bg-[#131313] border-b border-[#484848]/30 text-[#acabaa] font-label text-sm py-3 px-4 select-all">
                                    {user?.email || 'operator.alpha@vantage.quant'}
                                </div>
                            </div>
                            {/* Password Management */}
                            <div className="space-y-2 flex flex-col justify-end">
                                <label className="font-label text-[11px] uppercase tracking-wider text-[#767575] block">Security Key</label>
                                <button className="h-[46px] w-full bg-transparent border border-[#484848]/50 text-[#c6c6c7] hover:bg-[#2c2c2c] transition-colors font-headline text-sm flex items-center justify-center gap-2">
                                    <span className="material-symbols-outlined text-[18px]">key</span>
                                    Reset Cryptographic Key
                                </button>
                            </div>
                        </div>
                    </section>

                    {/* Session Control Block */}
                    <section className="pt-8 flex justify-end">
                        <button onClick={handleLogout} className="bg-transparent border border-[#7f2927] text-[#ee7d77] hover:bg-[#7f2927]/20 hover:text-[#bb5551] transition-colors py-3 px-8 font-label text-sm tracking-widest uppercase flex items-center gap-3">
                            <span className="material-symbols-outlined text-[18px]">power_settings_new</span>
                            Terminate Session
                        </button>
                    </section>
                </>
            )}

            {activeTab === 'preferences' && (
                <section className="bg-[#191a1a] p-8 space-y-8 relative overflow-hidden">
                    {/* Subtle AI Glow Texture */}
                    <div className="absolute -top-24 -right-24 w-64 h-64 bg-[#c6c6c7]/5 blur-[100px] rounded-full pointer-events-none"></div>
                    
                    <h3 className="font-label text-xs uppercase tracking-widest text-[#acabaa] mb-6 border-b border-[#131313] pb-2">Computational Endpoints</h3>
                    <div className="space-y-10">
                        {/* LLM Endpoint Input */}
                        <div className="space-y-2">
                            <div className="flex justify-between items-end">
                                <label className="font-label text-[11px] uppercase tracking-wider text-[#767575]" htmlFor="llm-endpoint">Local LLM Endpoint (Ollama)</label>
                                <span className="text-[10px] font-label text-[#c6c6c7] bg-[#c6c6c7]/10 px-2 py-0.5">STATUS: ONLINE</span>
                            </div>
                            <div className="relative">
                                <span className="absolute left-0 top-1/2 -translate-y-1/2 text-[#484848] pl-4 font-label text-sm pointer-events-none">http://</span>
                                <input className="w-full bg-[#131313] border-0 border-b border-[#484848] text-[#e7e5e4] font-label text-sm py-3 pl-16 pr-4 focus:ring-0 focus:border-[#c6c6c7] transition-colors placeholder:text-[#484848]" id="llm-endpoint" type="text" defaultValue="127.0.0.1:11434" />
                            </div>
                        </div>
                        
                        {/* Volatility Threshold */}
                        <div className="space-y-4">
                            <div className="flex justify-between items-end">
                                <label className="font-label text-[11px] uppercase tracking-wider text-[#767575]">Default Volatility Threshold (σ)</label>
                                <span className="font-label text-lg text-[#e7e5e4]">1.25</span>
                            </div>
                            <div className="w-full bg-[#000000] h-2 flex relative group cursor-pointer border border-[#484848]/20">
                                <div className="absolute top-0 left-0 h-full bg-[#c6c6c7]/20 w-full"></div>
                                <div className="absolute top-0 left-0 h-full bg-[#c6c6c7] w-[35%] transition-all group-hover:bg-[#e7e5e4]"></div>
                                <div className="absolute top-1/2 -translate-y-1/2 left-[35%] w-1.5 h-6 bg-[#c6c6c7] group-hover:bg-white transition-colors"></div>
                            </div>
                            <div className="flex justify-between font-label text-[10px] text-[#767575] pt-2">
                                <span>0.00 (Conservative)</span>
                                <span>5.00 (Aggressive)</span>
                            </div>
                        </div>
                    </div>
                </section>
            )}

            {activeTab === 'history' && (
                <section className="bg-[#191a1a] p-8">
                    <h3 className="font-label text-xs uppercase tracking-widest text-[#acabaa] mb-6 border-b border-[#131313] pb-2">Analysis Log</h3>
                    <div className="space-y-4">
                        <div className="p-4 bg-[#131313] border-l-2 border-primary flex justify-between items-center">
                            <div>
                                <p className="font-label text-sm text-[#e7e5e4]">$NVDA Analysis</p>
                                <p className="font-label text-[10px] text-[#767575]">2026-04-19 14:22:05</p>
                            </div>
                            <span className="text-[10px] font-label text-[#4ade80]">APPROVED</span>
                        </div>
                        <div className="p-4 bg-[#131313] border-l-2 border-error flex justify-between items-center opacity-60">
                            <div>
                                <p className="font-label text-sm text-[#e7e5e4]">$AAPL Analysis</p>
                                <p className="font-label text-[10px] text-[#767575]">2026-04-19 12:10:11</p>
                            </div>
                            <span className="text-[10px] font-label text-error">REJECTED</span>
                        </div>
                    </div>
                </section>
            )}
        </div>
    );
}
