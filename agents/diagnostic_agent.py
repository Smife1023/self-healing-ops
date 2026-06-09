# -*- coding: utf-8 -*-
"""
Diagnostic Agent -- MCP Server for deep root-cause analysis.

Role: Tier-2 Diagnosis Agent (deeper analysis, multi-signal correlation)
Key: MIMO Standard tier

Capabilities:
  - Multi-signal root cause analysis (metrics + logs + dependency graph)
  - Causal chain reconstruction from log timelines
  - Dependency-graph traversal for cascading failure root identification
  - Historical pattern matching (similar incidents)
  - Blast radius estimation
  - Actionable repair recommendations with risk assessment
"""

import json
from typing import Any

from mcp_agent_server import MCPAgentServer
from config import AGENT_CONFIGS, MIMO_BASE_URL, ESCALATION_POLICY
from infrastructure import InfrastructureSimulator


class DiagnosticAgent(MCPAgentServer):
    """
    Diagnostic Agent: Receives monitoring alerts and performs deep
    root-cause analysis using dependency graph traversal and log correlation.
    """

    def __init__(self, infra: InfrastructureSimulator):
        cfg = AGENT_CONFIGS["diagnostic"]
        super().__init__(
            name=cfg["name"], port=cfg["port"],
            api_key=cfg["api_key"], model=cfg["model"],
            base_url=MIMO_BASE_URL,
        )
        self.infra = infra
        self.diagnostic_prompt = """You are a principal SRE diagnostic engineer with 15 years of experience
in distributed systems debugging. You have received a monitoring alert and must perform deep root-cause analysis.

## Your Diagnostic Methodology

### Step 1: Establish Timeline
- Parse all log entries and identify the chronological sequence of events
- Find the FIRST anomalous event (this is often the root cause)
- Map cause -u effect chains

### Step 2: Dependency Graph Analysis
- Given the service dependency graph, trace the failure propagation path
- If downstream service X fails, which upstream services are affected?
- Distinguish between ROOT CAUSE (origin of failure) and SYMPTOMS (cascading effects)

### Step 3: Multi-Signal Correlation
- Correlate system metrics (CPU, memory, disk) with application errors
- Cross-reference log patterns with known failure modes
- Check for temporal correlation with deployments or config changes

### Step 4: Root Cause Hypothesis
- Generate 1-3 hypotheses ranked by likelihood
- For each hypothesis, list supporting and contradicting evidence
- Select the most likely root cause

### Step 5: Blast Radius Assessment
- Which services are currently affected?
- Which services COULD be affected if the issue continues?
- What is the user-facing impact?

### Step 6: Repair Strategy
- Recommend specific repair actions with priority ordering
- For each action, assess risk level and potential side effects
- Consider: "stop bleeding first" (mitigate) vs "fix root cause" (resolve)

## Available Repair Actions
- restart_service: Restart a service (low risk, quick)
- rollback_deploy: Roll back to previous version (medium risk)
- kill_process: Kill a specific process (low risk)
- clear_cache: Flush cache (medium risk -- cache miss storm)
- scale_up: Add replicas (low risk)
- cleanup_disk: Free disk space (low risk)
- fix_config: Fix configuration (medium risk)
- add_index: Add database index (low risk, but needs DDL)
- failover_replica: Promote replica to primary (high risk)
- drain_connections: Drain stale connections (low risk)
- circuit_breaker_reset: Reset circuit breaker (low risk)

## Escalation Policy
- P0_critical: Auto-remediate immediately, no approval needed
- P1_high: Auto-remediate, notify oncall + team lead
- P2_medium: Remediate with approval, notify oncall
- P3_low: Schedule fix, notify team channel

## Output Format

Return ONLY valid JSON (no markdown, no explanation):

{
  "incident_id": "from monitoring alert or generate one",
  "root_cause": {
    "description": "Precise one-sentence root cause description",
    "category": "cpu | memory | disk | network | service_crash | database | config | code_bug | cascading | deployment",
    "confidence": "high | medium | low"
  },
  "severity": "P0_critical | P1_high | P2_medium | P3_low",
  "timeline": [
    {"time": "timestamp", "event": "what happened", "component": "where", "significance": "root_cause | contributing | symptom"}
  ],
  "causal_chain": "A caused B which caused C -- trace the full chain",
  "evidence": {
    "supporting": ["evidence that supports the root cause hypothesis"],
    "metrics_correlation": ["metric readings that correlate with the failure"],
    "log_evidence": ["key log entries that confirm the diagnosis"]
  },
  "blast_radius": {
    "currently_affected": ["list of affected services/endpoints"],
    "at_risk": ["services that may be affected next"],
    "user_impact": "description of user-facing impact",
    "estimated_affected_requests_pct": 25.0
  },
  "recommended_actions": [
    {
      "priority": 1,
      "action": "action_type",
      "target": "target service or resource",
      "reason": "why this action and why in this order",
      "risk": "low | medium | high",
      "risk_detail": "what could go wrong",
      "expected_outcome": "what we expect to happen",
      "rollback_plan": "what to do if this action fails"
    }
  ],
  "prevention": {
    "short_term": "immediate fix to prevent recurrence",
    "long_term": "systemic improvement to prevent similar issues",
    "monitoring_improvements": "additional alerts or dashboards to add"
  },
  "similar_historical_incidents": "description of similar known incidents (if pattern matches)"
}
"""

    def get_tool_definitions(self) -> list[dict]:
        return [
            {
                "name": "diagnose",
                "description": (
                    "Deep root-cause analysis based on monitoring alert data. "
                    "Performs dependency-graph traversal, log timeline analysis, "
                    "multi-signal correlation, and generates prioritized repair recommendations."
                ),
                "parameters": [
                    {
                        "name": "monitor_alert",
                        "type": "string",
                        "description": "Monitor agent's structured alert report (JSON)",
                        "required": True,
                    }
                ],
            },
            {
                "name": "get_detailed_logs",
                "description": (
                    "Get detailed application logs for a specific service. "
                    "Includes recent log entries with timestamps, levels, and messages."
                ),
                "parameters": [
                    {
                        "name": "service_name",
                        "type": "string",
                        "description": "Service name (e.g., 'order-service', 'mysql-primary')",
                        "required": True,
                    }
                ],
            },
            {
                "name": "get_dependency_graph",
                "description": (
                    "Get the full service dependency graph. Shows which services "
                    "depend on which, protocol types, timeouts, and criticality."
                ),
                "parameters": [],
            },
            {
                "name": "trace_impact",
                "description": (
                    "Trace the impact of a failing service through the dependency graph. "
                    "Returns all upstream services that would be affected by the failure."
                ),
                "parameters": [
                    {
                        "name": "service_name",
                        "type": "string",
                        "description": "The failing service to trace impact from",
                        "required": True,
                    }
                ],
            },
        ]

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        if tool_name == "diagnose":
            return await self._do_diagnosis(arguments.get("monitor_alert", ""))
        elif tool_name == "get_detailed_logs":
            return self._get_service_logs(arguments.get("service_name", ""))
        elif tool_name == "get_dependency_graph":
            return self._get_dependency_graph()
        elif tool_name == "trace_impact":
            return self._trace_impact(arguments.get("service_name", ""))
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    async def _do_diagnosis(self, monitor_alert: str) -> str:
        """Perform deep root-cause analysis."""
        snapshot = self.infra.get_monitor_snapshot()
        dep_graph = self.infra.get_dependency_graph()
        snapshot_str = json.dumps(snapshot, ensure_ascii=False, indent=2)
        dep_str = json.dumps(dep_graph, ensure_ascii=False, indent=2)

        user_msg = f"""## Monitor Alert Report

{monitor_alert}

## Full System Monitoring Data

```json
{snapshot_str}
```

## Service Dependency Graph

```json
{dep_str}
```

## Your Task

Perform a deep root-cause analysis:

1. **Timeline**: Reconstruct the event timeline from logs. What happened first?
2. **Dependency Trace**: Using the dependency graph, trace the failure propagation.
   If a downstream service is failing, find which upstream services are impacted.
3. **Root Cause**: Identify the SINGLE root cause vs cascading symptoms.
4. **Blast Radius**: What is currently affected? What might be affected next?
5. **Repair Plan**: Recommend specific actions prioritized by:
   - First: Stop the bleeding (mitigate user impact)
   - Second: Fix the root cause
   - Third: Prevent recurrence

Be precise. Use exact service names, metric values, and log messages from the data.
"""

        diagnosis = await self.call_llm(self.diagnostic_prompt, user_msg)
        self.logger.info(f"Diagnosis complete ({len(diagnosis)} chars)")
        return diagnosis

    def _get_service_logs(self, service_name: str) -> str:
        """Get detailed logs for a specific service."""
        logs = self.infra.get_service_logs(service_name, limit=30)
        if not logs:
            return json.dumps({
                "service": service_name,
                "logs": [],
                "message": f"No logs found for service: {service_name}",
            })
        return json.dumps({
            "service": service_name,
            "log_count": len(logs),
            "logs": logs,
        }, ensure_ascii=False, indent=2)

    def _get_dependency_graph(self) -> str:
        """Return the full dependency graph."""
        return json.dumps(self.infra.get_dependency_graph(), ensure_ascii=False, indent=2)

    def _trace_impact(self, service_name: str) -> str:
        """Trace which upstream services are impacted by a failing downstream service."""
        deps = self.infra.get_dependency_graph()
        services = self.infra.state.services

        # Build reverse dependency map (downstream -u list of upstreams)
        reverse_deps = {}
        for dep in deps:
            downstream = dep["to"]
            if downstream not in reverse_deps:
                reverse_deps[downstream] = []
            reverse_deps[downstream].append({
                "upstream": dep["from"],
                "protocol": dep["protocol"],
                "critical": dep["critical"],
            })

        # BFS to find all affected upstream services
        affected = []
        visited = set()
        queue = [service_name]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            for upstream_dep in reverse_deps.get(current, []):
                upstream = upstream_dep["upstream"]
                if upstream not in visited:
                    svc_status = services.get(upstream)
                    affected.append({
                        "service": upstream,
                        "depends_on": current,
                        "protocol": upstream_dep["protocol"],
                        "critical": upstream_dep["critical"],
                        "current_status": svc_status.status if svc_status else "unknown",
                        "current_error_rate": svc_status.error_rate if svc_status else 0,
                    })
                    queue.append(upstream)

        return json.dumps({
            "root_failure": service_name,
            "total_affected": len(affected),
            "affected_upstream": affected,
            "propagation_path": [a["service"] for a in affected],
        }, ensure_ascii=False, indent=2)


def create_diagnostic_agent(infra: InfrastructureSimulator) -> DiagnosticAgent:
    return DiagnosticAgent(infra)