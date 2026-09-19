"use client";

import { createContext, useContext, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";

type NavigationState = {
  collapsed: boolean;
  setCollapsed: Dispatch<SetStateAction<boolean>>;
  companyExpanded: boolean;
  setCompanyExpanded: Dispatch<SetStateAction<boolean>>;
  groupExpanded: boolean;
  setGroupExpanded: Dispatch<SetStateAction<boolean>>;
};

const NavigationContext = createContext<NavigationState | null>(null);
export const CompanyNavigationContext = createContext<string | null>(null);

export function AnalysisNavigationProvider({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [companyExpanded, setCompanyExpanded] = useState(true);
  const [groupExpanded, setGroupExpanded] = useState(true);
  return <NavigationContext.Provider value={{ collapsed, setCollapsed, companyExpanded, setCompanyExpanded, groupExpanded, setGroupExpanded }}>{children}</NavigationContext.Provider>;
}

export function useAnalysisNavigation() {
  const state = useContext(NavigationContext);
  if (!state) throw new Error("La navegación necesita su proveedor de contexto.");
  return state;
}
