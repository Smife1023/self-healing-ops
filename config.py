# -*- coding: utf-8 -*-
"""
Configuration - API keys, agent settings, alerting thresholds, and SLA definitions.

This module centralizes all configuration for the Self-Healing Ops system,
including LLM API endpoints, per-agent key allocation, monitoring thresholds
aligned with industry-standard SLO/SLI definitions, and escalation policies.
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

# -- LLM API -----------------------------------------------------------------
MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "https://api.anthropic.com")

# -- Agent Configs ------------------------------------------------------------
# Each agent uses a separate API Key (simulating different service accounts /
# quota tiers in a real production environment).
# IMPORTANT: Set these via environment variables or .env file.
#            See .env.example for reference.
AGENT_CONFIGS = {
    "monitor": {
        "name": "MonitorAgent",
        "api_key": os.getenv("MONITOR_API_KEY", ""),
        "model": os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022"),
        "port": int(os.getenv("MONITOR_PORT", "9101")),
        "description": "Collects metrics, evaluates SLO burn-rate alerts, and detects anomalies via LLM reasoning",
        "role": "Tier-1: Detection (fastest response, highest priority key, Max tier)",
    },
    "diagnostic": {
        "name": "DiagnosticAgent",
        "api_key": os.getenv("DIAGNOSTIC_API_KEY", ""),
        "model": os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022"),
        "port": int(os.getenv("DIAGNOSTIC_PORT", "9102")),
        "description": "Performs multi-signal root-cause analysis with dependency-graph traversal",
        "role": "Tier-2: Diagnosis (deeper analysis, Standard tier key)",
    },
    "repair": {
        "name": "RepairAgent",
        "api_key": os.getenv("REPAIR_API_KEY", ""),
        "model": os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022"),
        "port": int(os.getenv("REPAIR_PORT", "9103")),
        "description": "Generates and executes repair runbooks with rollback capability",
        "role": "Tier-3: Remediation (execution agent, Standard tier key)",
    },
}

# Validate that API keys are configured
_missing_keys = [k for k, v in AGENT_CONFIGS.items() if not v["api_key"]]
if _missing_keys:
    import sys
    if "pytest" not in sys.modules and __name__ != "__main__":
        pass  # Will fail at LLM call time with clear error

COORDINATOR_PORT = int(os.getenv("COORDINATOR_PORT", "9200"))

# -- Monitoring Thresholds (aligned with Google SRE / Datadog conventions) ----
THRESHOLDS = {
    # Server-level
    "cpu_warning": 75.0,
    "cpu_critical": 90.0,
    "memory_warning": 80.0,
    "memory_critical": 92.0,
    "disk_warning": 80.0,
    "disk_critical": 90.0,
    "load_warning_multiplier": 2.0,   # load > cores * multiplier => warning
    "load_critical_multiplier": 4.0,
    "tcp_connections_warning": 5000,
    "tcp_connections_critical": 8000,

    # Service-level
    "error_rate_warning": 0.05,       # 5%
    "error_rate_critical": 0.10,      # 10%
    "latency_p99_warning_ms": 500,
    "latency_p99_critical_ms": 2000,
    "restart_count_warning": 2,

    # SLA / SLO
    "sla_target": 99.9,               # three nines
    "error_budget_burn_rate_window": "1h",
    "error_budget_burn_rate_threshold": 14.4,  # 2% budget in 1h = 14.4x burn rate
}

# -- Escalation Policy --------------------------------------------------------
ESCALATION_POLICY = {
    "P0_critical": {
        "description": "Production service down or data loss risk",
        "response_time_sla": "5 min",
        "notify": ["oncall-sre", "team-lead", "vp-engineering"],
        "auto_remediate": True,
        "requires_approval": False,  # P0 auto-remediate without approval
    },
    "P1_high": {
        "description": "Degraded service, user-facing impact",
        "response_time_sla": "15 min",
        "notify": ["oncall-sre", "team-lead"],
        "auto_remediate": True,
        "requires_approval": False,
    },
    "P2_medium": {
        "description": "Non-critical anomaly, no immediate user impact",
        "response_time_sla": "1 hour",
        "notify": ["oncall-sre"],
        "auto_remediate": True,
        "requires_approval": True,   # P2+ needs approval
    },
    "P3_low": {
        "description": "Warning-level, capacity planning",
        "response_time_sla": "Next business day",
        "notify": ["team-channel"],
        "auto_remediate": False,
        "requires_approval": True,
    },
}

# -- Incident Timeline Format --------------------------------------------------
TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S"
INCIDENT_LOG_PATH = os.getenv("INCIDENT_LOG_PATH", "incidents.jsonl")