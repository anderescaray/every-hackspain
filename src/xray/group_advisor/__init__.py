"""Advisor de tesorería: plan de grupo y sensibilidad de empresa sobre el nivel V2 (ver docs/group-optimization.md)."""
from xray.group_advisor.config import AdvisorConfig
from xray.group_advisor.fx import FX_ASOF, FX_SOURCE, MissingFXRateError, convert, default_fx_table
from xray.group_advisor.grounding import GroundingResult, validate_grounding
from xray.group_advisor.narrative import render_plan, render_sensitivity
from xray.group_advisor.objective import group_utility, utility
from xray.group_advisor.optimizer import certificate, optimize_group
from xray.group_advisor.pipeline import run
from xray.group_advisor.plan import build_plan, plan_to_json
from xray.group_advisor.qa import answer
from xray.group_advisor.sensitivity import company_sensitivity, iter_company_sensitivities, sensitivity_to_json
from xray.group_advisor.state import (AdvisorInputs, GroupState, SUBSIDIARY_COLUMNS, assemble_group_state, build_group_state,
                                      iter_group_states, load_inputs, reference_state_for, window_sums)

__all__ = ["AdvisorConfig", "AdvisorInputs", "GroupState", "GroundingResult", "SUBSIDIARY_COLUMNS", "FX_ASOF", "FX_SOURCE",
           "MissingFXRateError", "answer", "assemble_group_state", "build_group_state", "build_plan", "certificate",
           "company_sensitivity", "convert", "default_fx_table", "group_utility", "iter_company_sensitivities", "iter_group_states",
           "load_inputs", "optimize_group", "plan_to_json", "reference_state_for", "render_plan", "render_sensitivity", "run",
           "sensitivity_to_json", "utility", "validate_grounding", "window_sums"]
