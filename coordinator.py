# -*- coding: utf-8 -*-
"""
Coordinator -- Orchestrates the 3-agent self-healing pipeline with incident tracking.

Pipeline stages:
  1. Health check -- verify all agents are online
  2. Monitor Agent -- detect anomalies (Tier-1: fast detection)
  3. Diagnostic Agent -- root cause analysis (Tier-2: deep analysis)
  4. Repair Agent -- generate repair plan (Tier-3: runbook generation)
  5. Repair Agent -- execute repair steps with verification
  6. Verify -- post-repair health check and SLO validation
  7. Post-mortem -- generate incident report with timeline
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any

import httpx

from infrastructure import InfrastructureSimulator
from config import AGENT_CONFIGS, ESCALATION_POLICY, TIMESTAMP_FMT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Coordinator")


class IncidentTimeline:
    """Tracks the timeline of a self-healing incident."""

    def __init__(self):
        self.incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
        self.events: list[dict] = []
        self.started_at = datetime.now()
        self.resolved_at = None

    def add_event(self, event_type: str, agent: str, summary: str, details: dict = None):
        now = datetime.now()
        elapsed = (now - self.started_at).total_seconds()
        self.events.append({
            "timestamp": now.strftime(TIMESTAMP_FMT),
            "elapsed_s": round(elapsed, 2),
            "event_type": event_type,
            "agent": agent,
            "summary": summary,
            "details": details or {},
        })

    def resolve(self):
        self.resolved_at = datetime.now()

    def to_dict(self) -> dict:
        total = (self.resolved_at or datetime.now()) - self.started_at
        return {
            "incident_id": self.incident_id,
            "started_at": self.started_at.strftime(TIMESTAMP_FMT),
            "resolved_at": self.resolved_at.strftime(TIMESTAMP_FMT) if self.resolved_at else None,
            "total_duration_s": round(total.total_seconds(), 2),
            "event_count": len(self.events),
            "events": self.events,
        }


class MCPCoordinator:
    """Orchestrates Monitor -> Diagnostic -> Repair self-healing pipeline."""

    def __init__(self, infra: InfrastructureSimulator):
        self.infra = infra
        self.monitor_url = f"http://127.0.0.1:{AGENT_CONFIGS['monitor']['port']}"
        self.diagnostic_url = f"http://127.0.0.1:{AGENT_CONFIGS['diagnostic']['port']}"
        self.repair_url = f"http://127.0.0.1:{AGENT_CONFIGS['repair']['port']}"
        self.execution_log: list[dict] = []

    async def _call_mcp_tool(self, server_url: str, tool_name: str, arguments: dict = None) -> str:
        url = f"{server_url}/tools/{tool_name}/invoke"
        payload = {"arguments": arguments or {}}
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                port = server_url.split(":")[-1]
                logger.info(f"  -> Calling :{port}/{tool_name}")
                start = time.time()
                response = await client.post(url, json=payload)
                elapsed = (time.time() - start) * 1000
                response.raise_for_status()
                data = response.json()
                result = data.get("result", str(data))
                server_elapsed = data.get("elapsed_ms", elapsed)
                logger.info(f"  <- Response from :{port} ({server_elapsed:.0f}ms, {len(str(result))} chars)")
                return result
        except httpx.ConnectError:
            logger.error(f"Cannot connect to {server_url}, make sure agent is running")
            return json.dumps({"error": f"Service unreachable: {server_url}"})
        except Exception as e:
            logger.error(f"MCP call failed: {e}")
            return json.dumps({"error": str(e)})

    async def check_health(self) -> dict:
        urls = [
            ("MonitorAgent", self.monitor_url),
            ("DiagnosticAgent", self.diagnostic_url),
            ("RepairAgent", self.repair_url),
        ]
        results = {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            for name, base_url in urls:
                try:
                    resp = await client.get(f"{base_url}/health")
                    if resp.status_code == 200:
                        data = resp.json()
                        results[name] = {
                            "status": "ONLINE",
                            "model": data.get("model", "?"),
                            "requests": data.get("request_count", 0),
                        }
                    else:
                        results[name] = {"status": f"ERROR ({resp.status_code})"}
                except Exception:
                    results[name] = {"status": "OFFLINE"}
        return results

    async def run_self_healing_pipeline(self, verbose: bool = True) -> dict:
        start_time = time.time()
        timeline = IncidentTimeline()
        pipeline_result = {
            "status": "running",
            "incident_id": timeline.incident_id,
            "steps": [],
            "final_health": None,
            "timeline": None,
            "elapsed_seconds": 0,
        }

        if verbose:
            print("\n" + "=" * 70)
            print(f"  INCIDENT: {timeline.incident_id}")
            print(f"  SELF-HEALING PIPELINE: Monitor -> Diagnostic -> Repair")
            print(f"  STARTED: {datetime.now().strftime(TIMESTAMP_FMT)}")
            print("=" * 70)

        # )?)? Step 1: Monitor )?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?
        timeline.add_event("PIPELINE_START", "Coordinator", "Self-healing pipeline initiated")
        if verbose:
            print("\n" + "-" * 50)
            print("  [Step 1/5] ? MonitorAgent: Detecting anomalies...")
            print("-" * 50)

        monitor_result = await self._call_mcp_tool(self.monitor_url, "monitor_check")
        pipeline_result["steps"].append({"agent": "MonitorAgent", "tool": "monitor_check", "result": monitor_result})

        # Parse monitor result for severity
        try:
            monitor_data = json.loads(monitor_result)
            severity = monitor_data.get("severity", "unknown")
            anomaly_type = monitor_data.get("anomaly_type", "unknown")
            anomaly_summary = monitor_data.get("anomaly_summary", "N/A")
        except (json.JSONDecodeError, TypeError):
            severity = "unknown"
            anomaly_type = "unknown"
            anomaly_summary = str(monitor_result)[:200]

        timeline.add_event("ANOMALY_DETECTED", "MonitorAgent",
                           f"[{severity}] {anomaly_type}: {anomaly_summary}",
                           {"severity": severity, "type": anomaly_type})

        if verbose:
            print(f"\n  [ALERT] Severity: {severity}")
            print(f"  [ALERT] Type: {anomaly_type}")
            print(f"  [ALERT] Summary: {anomaly_summary}")
            self._print_json_truncated("Monitor Report", monitor_result, max_chars=800)

        # )?)? Step 2: Diagnosis )?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?
        if verbose:
            print("\n" + "-" * 50)
            print("  [Step 2/5] ? DiagnosticAgent: Root cause analysis...")
            print("-" * 50)

        diagnostic_result = await self._call_mcp_tool(
            self.diagnostic_url, "diagnose", {"monitor_alert": monitor_result}
        )
        pipeline_result["steps"].append({"agent": "DiagnosticAgent", "tool": "diagnose", "result": diagnostic_result})

        # Parse diagnosis for root cause
        try:
            diag_data = json.loads(diagnostic_result)
            root_cause = diag_data.get("root_cause", {})
            if isinstance(root_cause, dict):
                root_cause_desc = root_cause.get("description", str(root_cause))
            else:
                root_cause_desc = str(root_cause)
            diag_severity = diag_data.get("severity", "unknown")
            blast_radius = diag_data.get("blast_radius", {})
            user_impact = blast_radius.get("user_impact", "N/A")
        except (json.JSONDecodeError, TypeError):
            root_cause_desc = "Unable to parse"
            diag_severity = "unknown"
            user_impact = "N/A"

        timeline.add_event("DIAGNOSIS_COMPLETE", "DiagnosticAgent",
                           f"Root cause: {root_cause_desc}",
                           {"severity": diag_severity, "root_cause": root_cause_desc})

        if verbose:
            print(f"\n  [DIAGNOSIS] Root Cause: {root_cause_desc}")
            print(f"  [DIAGNOSIS] Severity: {diag_severity}")
            print(f"  [DIAGNOSIS] User Impact: {user_impact}")
            self._print_json_truncated("Diagnosis Report", diagnostic_result, max_chars=800)

        # )?)? Step 3: Repair Plan )?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?
        if verbose:
            print("\n" + "-" * 50)
            print("  [Step 3/5] ? RepairAgent: Creating repair plan...")
            print("-" * 50)

        repair_plan_result = await self._call_mcp_tool(
            self.repair_url, "create_repair_plan", {"diagnosis": diagnostic_result}
        )
        pipeline_result["steps"].append({"agent": "RepairAgent", "tool": "create_repair_plan", "result": repair_plan_result})

        # Parse repair plan
        try:
            plan = json.loads(repair_plan_result)
            repair_steps = plan.get("repair_plan", [])
            runbook_name = plan.get("runbook_name", "Unknown")
            est_time = plan.get("estimated_total_time", "N/A")
            requires_approval = plan.get("requires_approval", False)
        except (json.JSONDecodeError, TypeError):
            repair_steps = self._extract_actions_from_text(repair_plan_result)
            runbook_name = "Extracted from text"
            est_time = "N/A"
            requires_approval = False

        timeline.add_event("REPAIR_PLAN_READY", "RepairAgent",
                           f"Runbook: {runbook_name} ({len(repair_steps)} steps)",
                           {"steps": len(repair_steps), "requires_approval": requires_approval})

        if verbose:
            print(f"\n  [PLAN] Runbook: {runbook_name}")
            print(f"  [PLAN] Steps: {len(repair_steps)}")
            print(f"  [PLAN] Est. Time: {est_time}")
            print(f"  [PLAN] Requires Approval: {requires_approval}")
            for step in repair_steps:
                print(f"    Step {step.get('step', '?')}: [{step.get('phase', '?')}] "
                      f"{step.get('action', '?')} -> {step.get('target', '?')} "
                      f"(risk: {step.get('risk', '?')})")

        # )?)? Step 4: Execute Repairs )?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?
        if verbose:
            print("\n" + "-" * 50)
            print(f"  [Step 4/5] ?? RepairAgent: Executing {len(repair_steps)} repair steps...")
            print("-" * 50)

        repair_results = []
        for i, step in enumerate(repair_steps, 1):
            action = step.get("action", "")
            target = step.get("target", "")
            phase = step.get("phase", "resolve")
            risk = step.get("risk", "unknown")
            expected = step.get("expected_result", "N/A")

            if verbose:
                phase_icon = {"mitigate": "??", "resolve": "??", "verify": "??", "prevent": "??"}.get(phase, "??")
                print(f"\n  {phase_icon} [{i}/{len(repair_steps)}] {phase.upper()}: {action} -> {target}")
                print(f"     Risk: {risk} | Expected: {expected}")

            timeline.add_event("REPAIR_STEP_START", "RepairAgent",
                               f"Step {i}: {action} -> {target}",
                               {"action": action, "target": target, "phase": phase, "risk": risk})

            exec_result = await self._call_mcp_tool(
                self.repair_url, "execute_repair", {"action": action, "target": target}
            )
            repair_results.append({"step": i, "action": action, "target": target, "result": exec_result})

            if verbose:
                try:
                    r = json.loads(exec_result)
                    success = r.get("success", False)
                    status = "? OK" if success else "? FAIL"
                    print(f"     Result: {status} - {r.get('message', '')}")
                    for act in r.get("actions_taken", []):
                        print(f"       -> {act}")
                    for side in r.get("side_effects", []):
                        print(f"       ?? {side}")
                except (json.JSONDecodeError, TypeError):
                    print(f"     Result: {str(exec_result)[:200]}")

            # Quick health check after each step
            quick_health = self.infra.health_check()
            if verbose:
                print(f"     Health: {quick_health['overall'].upper()} "
                      f"(servers: {quick_health['healthy_servers']}/{quick_health['total_servers']}, "
                      f"services: {quick_health['healthy_services']}/{quick_health['total_services']})")

            timeline.add_event("REPAIR_STEP_COMPLETE", "RepairAgent",
                               f"Step {i} completed: {action}",
                               {"success": True, "health": quick_health["overall"]})

        pipeline_result["steps"].append({"agent": "RepairAgent", "tool": "execute_repair", "results": repair_results})

        # )?)? Step 5: Verify )?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?
        if verbose:
            print("\n" + "-" * 50)
            print("  [Step 5/5] ?? Post-repair verification...")
            print("-" * 50)

        final_health = self.infra.health_check()
        pipeline_result["final_health"] = final_health

        timeline.add_event("VERIFICATION_COMPLETE", "Coordinator",
                           f"System status: {final_health['overall']}",
                           {"health": final_health})

        if verbose:
            print(f"\n  [HEALTH] Overall: {final_health['overall'].upper()}")
            print(f"  [HEALTH] Servers: {final_health['healthy_servers']}/{final_health['total_servers']} healthy")
            print(f"  [HEALTH] Services: {final_health['healthy_services']}/{final_health['total_services']} healthy")
            if final_health["unhealthy_servers"]:
                for s in final_health["unhealthy_servers"]:
                    print(f"  [WARN] Server {s['server']}: {', '.join(s['issues'])}")
            if final_health["unhealthy_services"]:
                for s in final_health["unhealthy_services"]:
                    print(f"  [WARN] Service {s['service']}: {', '.join(s['issues'])}")
            if final_health.get("slo_violations"):
                for v in final_health["slo_violations"]:
                    print(f"  [SLO] {v['service']}: {v['current_availability']} (target: {v['slo_target']})")
            if not final_health["unhealthy_servers"] and not final_health["unhealthy_services"]:
                print("  ? All components recovered!")

        timeline.resolve()
        pipeline_result["timeline"] = timeline.to_dict()

        elapsed = time.time() - start_time
        pipeline_result["status"] = "completed"
        pipeline_result["elapsed_seconds"] = round(elapsed, 2)

        if verbose:
            # Post-mortem summary
            print("\n" + "=" * 70)
            print("  POST-INCIDENT REPORT")
            print("=" * 70)
            print(f"  Incident ID:     {timeline.incident_id}")
            print(f"  Duration:        {elapsed:.1f}s")
            print(f"  Severity:        {severity}")
            print(f"  Anomaly:         {anomaly_type}")
            print(f"  Root Cause:      {root_cause_desc[:80]}")
            print(f"  Steps Executed:  {len(repair_steps)}")
            print(f"  Final Status:    {final_health['overall'].upper()}")
            print(f"  Timeline Events: {len(timeline.events)}")
            print("=" * 70)

        self.execution_log.append(pipeline_result)
        return pipeline_result

    def _extract_actions_from_text(self, text: str) -> list[dict]:
        actions = []
        action_keywords = [
            "restart_service", "rollback_deploy", "kill_process", "clear_cache",
            "scale_up", "cleanup_disk", "fix_config", "add_index",
            "failover_replica", "drain_connections", "circuit_breaker_reset",
        ]
        service_names = [
            "nginx", "api-gateway", "user-service", "order-service",
            "payment-service", "inventory-service", "notification-service",
            "mysql-primary", "mysql-replica", "redis-cluster", "rabbitmq", "elasticsearch",
        ]
        for keyword in action_keywords:
            if keyword in text:
                idx = text.index(keyword)
                context = text[max(0, idx - 50):idx + 100]
                target = ""
                for svc in service_names:
                    if svc in context:
                        target = svc
                        break
                actions.append({"action": keyword, "target": target, "reason": "Extracted from diagnosis"})
        return actions

    def _print_json_truncated(self, label: str, json_str: str, max_chars: int = 800):
        """Print truncated JSON for readability."""
        try:
            data = json.loads(json_str)
            formatted = json.dumps(data, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, TypeError):
            formatted = str(json_str)

        if len(formatted) > max_chars:
            print(f"\n  [{label}] (truncated, {len(formatted)} chars total):")
            for line in formatted[:max_chars].split("\n"):
                print(f"    {line}")
            print(f"    ... ({len(formatted) - max_chars} more chars)")
        else:
            print(f"\n  [{label}]:")
            for line in formatted.split("\n"):
                print(f"    {line}")


def create_coordinator(infra: InfrastructureSimulator) -> MCPCoordinator:
    return MCPCoordinator(infra)