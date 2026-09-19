"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { GroupView } from "@/types/groupDetail";
import { companySections, withCompanyContext } from "@/lib/analysisNavigation";
import { groupTabs } from "@/lib/groupPresentation";
import { CompanyNavigationContext, useAnalysisNavigation } from "./AnalysisNavigationProvider";
import styles from "./navigation.module.css";

type ShellProps = { companyId: string | null; groupId?: string | null; view: "company" | GroupView; children: ReactNode };

function NavigationIcon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    health: "M4 12h4l2-6 4 12 2-6h4",
    trend: "M4 18V5m0 13h16M7 14l4-4 4 2 5-7",
    actions: "M4 18h16M7 15l4-4 3 2 4-6M16 7h2v2",
    cash: "M4 7h16v12H4zM4 7V4h12m-1 8h5m-4 0v3",
    time: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18m0 4v5l4 2",
    overview: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
    network: "M12 4v5M5 17l5-4m4 0 5 4M9 2h6v5H9zM2 16h6v5H2zM16 16h6v5h-6z",
    recommendations: "M8 4h12v16H4V4h4m0-2h8v5H8zM8 12l2 2 5-5M8 17h8",
    company: "M5 21V3h14v18M2 21h20M8 7h2m4 0h2M8 11h2m4 0h2M10 21v-5h4v5",
    chevron: "m8 5 7 7-7 7",
    menu: "M4 6h16M4 12h16M4 18h16",
    close: "m6 6 12 12M18 6 6 18",
    collapse: "M4 4h16v16H4zM9 4v16m7-12-4 4 4 4",
  };
  return <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] ?? paths.overview} /></svg>;
}

function SidebarContents({ companyId, groupId, view, activeSection, onSection, mobile = false, close }: Omit<ShellProps, "children"> & { activeSection: string; onSection: (id: string) => void; mobile?: boolean; close?: () => void }) {
  const navigation = useAnalysisNavigation();
  const collapsed = !mobile && navigation.collapsed;
  const sectionsId = useId();
  const groupIdRef = useId();
  const home = companyId ? `/companies/${companyId}#health-score` : groupId ? `/groups/${groupId}` : null;

  return <div className={styles.sidebarContents} data-compact={collapsed}>
    <div className={styles.brandRow}>
      {home ? <Link href={withCompanyContext(home, companyId)} className={styles.brand} aria-label="Embat Pulse, inicio del análisis" onClick={close}><span className={styles.brandMark}>P</span><span className={styles.brandWords}>embat <strong>Pulse</strong></span></Link> : <span className={styles.brand}><span className={styles.brandMark}>P</span><span className={styles.brandWords}>embat <strong>Pulse</strong></span></span>}
      {mobile ? <button className={styles.iconButton} aria-label="Cerrar navegación" onClick={close}><NavigationIcon name="close" /></button> : <button className={styles.iconButton} aria-label={collapsed ? "Expandir menú lateral" : "Contraer menú lateral"} aria-expanded={!collapsed} onClick={() => navigation.setCollapsed((value) => !value)}><NavigationIcon name="collapse" /></button>}
    </div>
    <div className={styles.selectedCompany} role="group" aria-label={`Empresa seleccionada: ${companyId ?? "sin seleccionar"}`} title={companyId ?? "Sin empresa seleccionada"}><NavigationIcon name="company" /><div className={styles.contextText}><span>Empresa seleccionada</span><strong data-testid={mobile ? "mobile-navigation-company" : "navigation-company"}>{companyId ?? "Sin seleccionar"}</strong></div></div>
    <div className={styles.menuSections}>
      <button className={styles.sectionToggle} aria-label="Secciones de empresa" aria-expanded={navigation.companyExpanded} aria-controls={sectionsId} onClick={() => navigation.setCompanyExpanded((value) => !value)}><span className={styles.sectionInitial}>E</span><span className={styles.sectionText}>Empresa</span><span className={styles.disclosure} data-expanded={navigation.companyExpanded}><NavigationIcon name="chevron" /></span></button>
      <nav id={sectionsId} hidden={!navigation.companyExpanded} aria-label="Secciones de empresa" className={styles.menuLinks}>
        {companyId ? companySections.map((section) => <Link key={section.id} href={`/companies/${companyId}#${section.id}`} aria-label={section.label} title={collapsed ? section.label : undefined} aria-current={view === "company" && activeSection === section.id ? "location" : undefined} onClick={(event) => { if (view === "company" && window.location.pathname === `/companies/${companyId}` && window.location.hash === `#${section.id}`) event.preventDefault(); onSection(section.id); close?.(); }}><NavigationIcon name={section.icon} /><span className={styles.linkText}>{section.label}</span></Link>) : <p className={styles.menuHint}>Abre una ficha de empresa para consultar su análisis individual.</p>}
      </nav>
      {groupId ? <>
        <hr className={styles.divider} />
        <button className={styles.sectionToggle} aria-label="Secciones de grupo" aria-expanded={navigation.groupExpanded} aria-controls={groupIdRef} onClick={() => navigation.setGroupExpanded((value) => !value)}><span className={styles.sectionInitial}>G</span><span className={styles.sectionText}>Grupo</span><span className={styles.disclosure} data-expanded={navigation.groupExpanded}><NavigationIcon name="chevron" /></span></button>
        <span className={styles.groupIdentity}>{groupId}</span>
        <nav id={groupIdRef} hidden={!navigation.groupExpanded} aria-label="Vistas de inteligencia de grupo" className={styles.menuLinks}>{groupTabs.map((tab) => <Link key={tab.key} href={withCompanyContext(`/groups/${groupId}${tab.suffix}`, companyId)} aria-label={tab.label} title={collapsed ? tab.label : undefined} aria-current={view === tab.key ? "page" : undefined} onClick={close}><NavigationIcon name={tab.key} /><span className={styles.linkText}>{tab.label}</span></Link>)}</nav>
      </> : <p className={styles.noGroup}>{groupId === null ? "Empresa sin grupo asociado" : "Grupo pendiente de datos"}</p>}
    </div>
    <div className={styles.sidebarFooter}><span className={styles.footerDot} /><span className={styles.footerText}>Datos preparados</span></div>
  </div>;
}

export function AnalysisShell({ companyId, groupId, view, children }: ShellProps) {
  const { collapsed } = useAnalysisNavigation();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [activeSection, setActiveSection] = useState<string>("health-score");
  const dialog = useRef<HTMLDialogElement>(null);
  const dialogTitle = useId();
  const selectSection = (id: string) => {
    setActiveSection(id);
    if (view === "company" && pathname === `/companies/${companyId}`) {
      requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" }));
    }
  };

  useEffect(() => {
    if (view !== "company" || pathname !== `/companies/${companyId}`) return;
    const update = () => {
      const current = [...companySections].reverse().find((section) => {
        const node = document.getElementById(section.id);
        return node && node.getBoundingClientRect().top <= 160;
      });
      setActiveSection(current?.id ?? "health-score");
    };
    const followHash = () => {
      const section = companySections.find((item) => `#${item.id}` === window.location.hash);
      if (section) document.getElementById(section.id)?.scrollIntoView({ block: "start", behavior: "instant" });
      update();
    };
    const frame = requestAnimationFrame(followHash);
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("hashchange", followHash);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("scroll", update); window.removeEventListener("hashchange", followHash); };
  }, [companyId, view, pathname]);

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 981px)");
    const closeOnDesktop = () => { if (desktop.matches) setMobileOpen(false); };
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, []);

  useEffect(() => {
    if (!mobileOpen) return;
    const modal = dialog.current;
    const trigger = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    modal?.showModal();
    document.body.style.overflow = "hidden";
    return () => { modal?.close(); document.body.style.overflow = overflow; trigger?.focus({ preventScroll: true }); };
  }, [mobileOpen]);

  return <CompanyNavigationContext.Provider value={companyId}>
    <div className={styles.shell} data-collapsed={collapsed} data-testid="analysis-shell">
      <aside className={styles.desktopSidebar} aria-label="Menú lateral"><SidebarContents companyId={companyId} groupId={groupId} view={view} activeSection={activeSection} onSection={selectSection} /></aside>
      <div className={styles.content}>
        <div className={styles.mobileBar}><button className={styles.mobileMenuButton} aria-label="Abrir navegación" aria-expanded={mobileOpen} aria-haspopup="dialog" onClick={() => setMobileOpen(true)}><NavigationIcon name="menu" /><span>Menú</span></button><div><strong>Pulse</strong><span>{companyId ?? groupId ?? "Cartera"}</span></div></div>
        {children}
      </div>
      <dialog ref={dialog} className={styles.mobileDrawer} aria-labelledby={dialogTitle} onCancel={() => setMobileOpen(false)} onClick={(event) => { if (event.target === event.currentTarget) setMobileOpen(false); }}><h2 id={dialogTitle} className={styles.srOnly}>Navegación de empresa y grupo</h2>{mobileOpen && <SidebarContents companyId={companyId} groupId={groupId} view={view} activeSection={activeSection} onSection={selectSection} mobile close={() => setMobileOpen(false)} />}</dialog>
    </div>
  </CompanyNavigationContext.Provider>;
}
