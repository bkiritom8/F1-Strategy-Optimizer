import React from 'react';
import { motion } from 'framer-motion';
import { Shield, Book, Mail, Globe, Lock, Info, ExternalLink, Github } from 'lucide-react';

/**
 * @file Footer.tsx
 * @description Premium, racing-themed footer with legal and compliance links.
 */

interface FooterProps {
  onAdminClick?: () => void;
}

const Footer: React.FC<FooterProps> = ({ onAdminClick }) => {
  const currentYear = new Date().getFullYear();

  const sections = [
    {
      title: 'Navigation',
      links: [
        { label: 'Documentation', href: '/docs.html', icon: Book },
        { label: 'Technical Specs', href: '#', icon: Info },
        { label: 'Sitemap', href: '/sitemap.xml', icon: Globe },
      ],
    },
    {
      title: 'Compliance',
      links: [
        { label: 'Privacy Policy', href: '/privacy-policy.html', icon: Lock },
        { label: 'Terms of Service', href: '/terms.html', icon: Shield },
        { label: 'Cookie Policy', href: '/cookie-policy.html', icon: Shield },
      ],
    },
    {
      title: 'Support',
      links: [
        { label: 'Contact Strategist', href: '/contact.html', icon: Mail },
        { label: 'Manage Cookies', href: '#', icon: Info, isCookieTrigger: true },
        { label: 'Administrative Entry', href: '#', icon: Lock, isAdminTrigger: true },
      ],
    },
  ];

  const handleCookieClick = (e: React.MouseEvent) => {
    e.preventDefault();
    // Dispatch event to show cookie consent if hidden
    window.dispatchEvent(new CustomEvent('apex:open_cookie_settings'));
  };

  return (
    <footer className="relative mt-20 border-t border-white/5 bg-black/40 backdrop-blur-xl overflow-hidden">
      {/* Decorative racing line at the top */}
      <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-red-600/50 to-transparent" />
      
      <div className="max-w-7xl mx-auto px-6 pt-16 pb-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-12 mb-16">
          {/* Brand Section */}
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-red-600 flex items-center justify-center shadow-lg shadow-red-900/20">
                <span className="text-white font-black text-xl italic tracking-tighter">A</span>
              </div>
              <span className="text-xl font-black uppercase tracking-tighter italic text-white flex items-center">
                Apex <span className="text-red-600 ml-1">Intelligence</span>
              </span>
            </div>
            <p className="text-sm text-white/40 leading-relaxed max-w-xs">
              Next-generation F1 strategy optimization powered by advanced machine learning telemetry. High-stakes precision for the absolute limit.
            </p>
            <div className="flex gap-4">
              <a 
                href="https://github.com/nateplusplus/F1-Strategy-Optimizer" 
                target="_blank"
                rel="noopener noreferrer"
                className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 hover:border-red-500/50 transition-all flex items-center justify-center group"
              >
                <Github className="w-5 h-5 text-white/40 group-hover:text-white group-hover:scale-110 transition-all" />
              </a>
            </div>
          </div>

          {/* Links Sections */}
          {sections.map((section) => (
            <div key={section.title} className="space-y-6">
              <h4 className="text-xs font-black uppercase tracking-widest text-red-500 italic pb-2 border-b border-red-500/10 inline-block">
                {section.title}
              </h4>
              <ul className="space-y-4">
                {section.links.map((link) => {
                  const Icon = link.icon;
                  // @ts-ignore
                  const isLink = link.href !== '#' || link.isCookieTrigger || link.isAdminTrigger;
                  
                  const handleClick = (e: React.MouseEvent) => {
                    if (link.isCookieTrigger) handleCookieClick(e);
                    // @ts-ignore
                    if (link.isAdminTrigger && onAdminClick) {
                      e.preventDefault();
                      onAdminClick();
                    }
                  };

                  return (
                    <li key={link.label}>
                      <a
                        href={link.href}
                        onClick={handleClick}
                        className="group flex items-center gap-3 text-sm text-white/50 hover:text-white transition-colors"
                      >
                        <div className="p-1.5 rounded-md bg-white/5 group-hover:bg-red-600/10 border border-white/5 group-hover:border-red-500/20 transition-all">
                          <Icon className="w-3.5 h-3.5 group-hover:text-red-500" />
                        </div>
                        {link.label}
                      </a>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="pt-8 border-t border-white/5 flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="text-[10px] text-white/20 uppercase tracking-[0.2em] font-medium text-center md:text-left">
            © {currentYear} Apex Strategy Labs. All Data Streams Encrypted.
          </div>
          <div className="flex items-center gap-8">
             <div className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                <span className="text-[10px] text-white/30 uppercase tracking-widest">System Status: Optimal</span>
             </div>
             <div className="text-[10px] text-white/30 uppercase tracking-widest hover:text-red-500 transition-colors cursor-pointer">
                Privacy Rights
             </div>
          </div>
        </div>
      </div>

      {/* Background decoration */}
      <div className="absolute -bottom-24 -right-24 w-64 h-64 bg-red-600/5 blur-[100px] rounded-full pointer-events-none" />
      <div className="absolute -bottom-24 -left-24 w-64 h-64 bg-red-600/5 blur-[100px] rounded-full pointer-events-none" />
    </footer>
  );
};

export default Footer;
