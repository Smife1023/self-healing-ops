# -*- coding: utf-8 -*-
"""
Monitor Agent -- MCP Server for real-time anomaly detection and SLO monitoring.

Role: Tier-1 Detection Agent (highest priority, fastest response)
Key: MIMO Max tier (low latency, high throughput)

Capabilities:
  - Multi-signal anomaly detection (CPU, memory, disk, network, application)
  - SLO burn-rate alerting (Google SRE 4-window method)
  - Cascading failure pattern recognition
  - Change-point detection (correlate with recent deployments)
  - Structured alert generation for downstream Diagnostic Agent
"""

import json
from typing import Any

from mcp_agent_server import MCPAgentServer
from config import AGENT_CONFIGS, MIMO_BASE_URL, THRESHOLDS
from infrastructure import InfrastructureSimulator


class MonitorAgent(MCPAgentServer):
    """
    Monitor Agent: Evaluates system metrics against SLO thresholds,
    detects anomalies via LLM reasoning, and generates structured alerts.
    """

    def __init__(self, infra: InfrastructureSimulator):
        cfg = AGENT_CONFIGS["monitor"]
        super().__init__(
            name=cfg["name"], port=cfg["port"],
            api_key=cfg["api_key"], model=cfg["model"],
            base_url=MIMO_BASE_URL,
        )
        self.infra = infra
        self.monitor_prompt = f"""You are a senior SRE monitoring engineer at a major e-commerce company.
Your job is to analyze infrastructure metrics and application logs to detect anomalies and generate alerts.

## Your Analysis Framework

### 1. Metric Evaluation (check each threshold)
- CPU > {THRESHOLDS['cpu_critical']}% -> CRITICAL
- CPU > {THRESHOLDS['cpu_warning']}% -> WARNING
- Memory > {THRESHOLDS['memory_critical']}% -> CRITICAL
- Disk > {THRESHOLDS['disk_critical']}% -> CRITICAL
- Load avg > cores -? {THRESHOLDS['load_critical_multiplier']} -> CRITICAL
- Error rate > {THRESHOLDS['error_rate_critical']*100}% -> CRITICAL
- Latency p99 > {THRESHOLDS['latency_p99_critical_ms']}ms -> CRITICAL
- Service status = "down" -> CRITICAL

### 2. SLO Burn-Rate Analysis
- Calculate error budget burn rate: (actual_error_rate / (1 - sla_target/100))
- If burn_rate > {THRESHOLDS['error_budget_burn_rate_threshold']} in 1h window -> CRITICAL
- If burn_rate > 6.0 in 1h window -> WARNING

### 3. Cascading Failure Detection
- Check dependency graph: if downstream service is down, check upstream impact
- Look for correlation: multiple services degrading simultaneously
- Identify the root source (first service to degrade)

### 4. Change Correlation
- Check recent deployment events in logs
- Correlate timing of degradation with deploy timestamps
- Flag "deployment regression" if degradation started within 10min of deploy

## Output Format

Return ONLY valid JSON (no markdown, no explanation):

{{
  "has_anomaly": true,
  "severity": "P0_critical | P1_high | P2_medium | P3_low",
  "anomaly_type": "cpu_spike | memory_leak | service_crash | db_slow | connection_exhaustion | disk_full | cascading_failure | deployment_regression",
  "anomaly_summary": "One sentence summary of what happened",
  "affected_components": [
    {{
      "name": "component-name",
      "type": "server | service",
      "metric": "what metric breached",
      "current_value": "current value",
      "threshold": "threshold value",
      "breach_severity": "critical | warning"
    }}
  ],
  "slo_impact": {{
    "services_affected": ["list of services with SLO violations"],
    "estimated_availability_pct": 99.5,
    "error_budget_remaining_pct": 45.0,
    "burn_rate": 28.8
  }},
  "cascade_analysis": {{
    "is_cascading": false,
    "root_source": "first failing component or null",
    "propagation_path": ["component1 -> component2 -> component3"]
  }},
  "change_correlation": {{
    "recent_deploy_detected": false,
    "deploy_time": null,
    "deploy_service": null,
    "confidence": "high | medium | low | none"
  }},
  "key_evidence": [
    "Most critical log line or metric reading",
    "Second most important evidence",
    "Third piece of evidence"
  ],
  "recommended_escalation": "P0_immediate | P1_urgent | P2_soon | P3_routine"
}}

IMPORTANT: Analyze ALL servers and services systematically. Do not stop at the first anomaly.
"""

    def get_tool_definitions(self) -> list[dict]:
        return [
            {
                "name": "monitor_check",
                "description": (
                    "Execute comprehensive system monitoring check. Collects all server metrics, "
                    "service health, application logs, and dependency status. Uses LLM to analyze "
                    "for anomalies, SLO violations, cascading failures, and deployment regressions."
                ),
                "parameters": [],
            },
            {
                "name": "get_infra_snapshot",
                "description": (
                    "Get raw infrastructure monitoring data snapshot including all servers, "
                    "services, dependencies, and recent logs. No LLM analysis -- raw data only."
                ),
                "parameters": [],
            },
            {
                "name": "check_service_health",
                "description": (
                    "Quick health check for a specific service. Returns status, latency, "
                    "error rate, and recent logs for one service."
                ),
                "parameters": [
                    {
                        "name": "service_name",
                        "type": "string",
                        "description": "Name of the service to check (e.g., 'order-service', 'mysql-primary')",
                        "required": True,
                    }
                ],
            },
            {
                "name": "get_dependency_status",
                "description": (
                    "Get the current status of all service dependencies. "
                    "Shows which downstream services are healthy/degraded/down."
                ),
                "parameters": [],
            },
        ]

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        if tool_name == "monitor_check":
            return await self._do_monitor_check()
        elif tool_name == "get_infra_snapshot":
            return json.dumps(self.infra.get_monitor_snapshot(), ensure_ascii=False, indent=2)
        elif tool_name == "check_service_health":
            return self._check_service_health(arguments.get("service_name", ""))
        elif tool_name == "get_dependency_status":
            return self._get_dependency_status()
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    async def _do_monitor_check(self) -> str:
        """Full monitoring check with LLM analysis."""
        snapshot = self.infra.get_monitor_snapshot()
        snapshot_str = json.dumps(snapshot, ensure_ascii=False, indent=2)

        # Pre-compute some metrics for the LLM
        alerts = self._precompute_alerts(snapshot)

        user_msg = f"""## System Monitoring Snapshot

```json
{snapshot_str}
```

## Pre-computed Alerts (threshold-based)

```json
{json.dumps(alerts, ensure_ascii=False, indent=2)}
```

Perform a comprehensive anomaly analysis. Check every server and service.
Identify the root cause if multiple components are affected.
Determine if this is a cascading failure and trace the propagation path.
Check for deployment correlation in the logs.
"""

        analysis = await self.call_llm(self.monitor_prompt, user_msg)
        self.logger.info(f"Monitor analysis complete ({len(analysis)} chars)")
        return analysis

    def _precompute_alerts(self, snapshot: dict) -> list:
        """Pre-compute threshold-based alerts to help the LLM focus on analysis."""
        alerts = []

        for name, server in snapshot.get("servers", {}).items():
            cpu = server.get("cpu_usage_pct", 0)
            if cpu > THRESHOLDS["cpu_critical"]:
                alerts.append({"type": "cpu_critical", "server": name, "value": cpu,
                               "threshold": THRESHOLDS["cpu_critical"]})
            elif cpu > THRESHOLDS["cpu_warning"]:
                alerts.append({"type": "cpu_warning", "server": name, "value": cpu,
                               "threshold": THRESHOLDS["cpu_warning"]})

            mem = server.get("memory_usage_pct", 0)
            if mem > THRESHOLDS["memory_critical"]:
                alerts.append({"type": "memory_critical", "server": name, "value": mem,
                               "threshold": THRESHOLDS["memory_critical"]})

            disk = server.get("disk_usage_pct", 0)
            if disk > THRESHOLDS["disk_critical"]:
                alerts.append({"type": "disk_critical", "server": name, "value": disk,
                               "threshold": THRESHOLDS["disk_critical"]})

            load = server.get("load_avg", {}).get("1m", 0)
            cores = server.get("cpu_cores", 1)
            if load > cores * THRESHOLDS["load_critical_multiplier"]:
                alerts.append({"type": "load_critical", "server": name, "value": load,
                               "threshold": cores * THRESHOLDS["load_critical_multiplier"]})

        for name, svc in snapshot.get("services", {}).items():
            if svc.get("status") == "down":
                alerts.append({"type": "service_down", "service": name})
            elif svc.get("status") == "degraded":
                alerts.append({"type": "service_degraded", "service": name})

            err = svc.get("error_rate", 0)
            if err > THRESHOLDS["error_rate_critical"]:
                alerts.append({"type": "error_rate_critical", "service": name,
                               "value": err, "threshold": THRESHOLDS["error_rate_critical"]})

            p99 = svc.get("latency", {}).get("p99_ms", 0)
            if p99 > THRESHOLDS["latency_p99_critical_ms"]:
                alerts.append({"type": "latency_critical", "service": name,
                               "value": p99, "threshold": THRESHOLDS["latency_p99_critical_ms"]})

            cb = svc.get("circuit_breaker", "closed")
            if cb == "open":
                alerts.append({"type": "circuit_breaker_open", "service": name})

        return alerts

    def _check_service_health(self, service_name: str) -> str:
        """Quick health check for a single service."""
        snapshot = self.infra.get_monitor_snapshot()
        svc = snapshot.get("services", {}).get(service_name)
        if not svc:
            return json.dumps({"error": f"Service not found: {service_name}"})

        logs = self.infra.get_service_logs(service_name, limit=10)
        return json.dumps({
            "service": service_name,
            "status": svc,
            "recent_logs": logs,
        }, ensure_ascii=False, indent=2)

    def _get_dependency_status(self) -> str:
        """Check status of all dependencies."""
        snapshot = self.infra.get_monitor_snapshot()
        deps = snapshot.get("dependencies", [])
        services = snapshot.get("services", {})

        dep_status = []
        for dep in deps:
            upstream = dep["from"]
            downstream = dep["to"]
            downstream_svc = services.get(downstream, {})
            dep_status.append({
                "upstream": upstream,
                "downstream": downstream,
                "protocol": dep["protocol"],
                "critical": dep["critical"],
                "downstream_status": downstream_svc.get("status", "unknown"),
                "downstream_error_rate": downstream_svc.get("error_rate", 0),
            })

        return json.dumps(dep_status, ensure_ascii=False, indent=2)


def create_monitor_agent(infra: InfrastructureSimulator) -> MonitorAgent:
    return MonitorAgent(infra)