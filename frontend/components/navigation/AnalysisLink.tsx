"use client";

import Link from "next/link";
import { useContext, type ComponentProps } from "react";
import { withCompanyContext } from "@/lib/analysisNavigation";
import { CompanyNavigationContext } from "./AnalysisNavigationProvider";

export function AnalysisLink({ href, ...props }: Omit<ComponentProps<typeof Link>, "href"> & { href: string }) {
  const companyId = useContext(CompanyNavigationContext);
  return <Link {...props} href={withCompanyContext(href, companyId)} />;
}
