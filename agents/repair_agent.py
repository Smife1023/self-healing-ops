# -*- coding: utf-8 -*-
"""
Repair Agent -- MCP Server for automated remediation with rollback capability.

Role: Tier-3 Remediation Agent (execution, verification, rollback)
Key: MIMO Standard tier

Capabilities:
  - Runbook-based repair plan generation
  - Step-by-step execution with verification after each step
  - Automatic rollback on failure
  - Risk-aware action sequencing
  - Post-repair health verification
  - Incident timeline recording
"""

import json
from typing import Any

from mcp_agent_server import MCPAgentServer
from config import AGENT_CONFIGS, MIMO_BASE_URL, ESCALATION_POLICY
from infrastructure import InfrastructureSimulator


class RepairAgent(MCPAgentServer):
    """
    Repair Agent: Generates and executes repair runbooks based on
    diagnostic reports, with automatic rollback on failure.
    """

    def __init__(self, infra: InfrastructureSimulator):
        cfg = AGENT_CONFIGS["repair"]
        super().__init__(
            name=cfg["name"], port=cfg["port"],
            api_key=cfg["api_key"], model=cfg["model"],
            base_url=MIMO_BASE_URL,
        )
        self.infra = infra
        self.repair_prompt = """You are a senior SRE repair engineer responsible for executing
automated remediation of production incidents. You have received a diagnostic report
and must create a precise, safe repair runbook.

## Your Repair Philosophy

### Principle 1: Stop the Bleeding First
- Before fixing root cause, mitigate user impact
- Quick wins: circuit breaker reset, traffic reroute, scale up
- This buys time for proper root-cause fix

### Principle 2: Minimal Blast Radius
- Prefer targeted fixes over broad changes
- One service at a time, verify between steps
- Avoid "big bang" fixes that could make things worse

### Principle 3: Always Have a Rollback Plan
- Every action should be reversible
- If an action fails, know how to undo it
- Never perform irreversible actions without explicit approval

### Principle 4: Verify After Each Step
- After each repair action, check if the system improved
- If no improvement, reassess before proceeding
- If things got worse, rollback immediately

## Available Repair Actions

| Action | Description | Risk | Reversible |
|--------|-------------|------|------------|
| restart_service | Graceful service restart | Low | Yes (stop/start) |
| rollback_deploy | Roll back to previous version | Medium | Yes (re-deploy) |
| kill_process | Kill a specific OS process | Low | N/A (restarts) |
| clear_cache | Flush Redis/in-memory cache | Medium | No (warmup needed) |
| scale_up | Add service replicas via HPA | Low | Yes (scale down) |
| cleanup_disk | Remove old logs, rotate binlogs | Low | No |
| fix_config | Inject config from Vault/secret store | Medium | Yes (revert config) |
| add_index | Create database index (online DDL) | Low | Yes (DROP INDEX) |
| failover_replica | Promote DB replica to primary | High | Complex |
| drain_connections | Close stale connections in pool | Low | N/A |
| circuit_breaker_reset | Reset circuit breaker to half-open | Low | Auto-closes |

## Escalation Rules
- P0: Execute immediately, no approval needed. Auto-restart, failover, etc.
- P1: Execute with notification. Rollback deploy, scale up, etc.
- P2: Requires approval. Config changes, index additions.
- P3: Schedule for maintenance window. Schema changes, major refactors.

## Output Format

Return ONLY valid JSON (no markdown, no explanation):

{
  "incident_id": "from diagnosis",
  "runbook_name": "descriptive name for this repair runbook",
  "estimated_total_time": "5 min",
  "requires_approval": false,
  "approval_reason": null,
  "repair_plan": [
    {
      "step": 1,
      "phase": "mitigate | resolve | verify | prevent",
      "action": "action_type",
      "target": "target service or resource",
      "params": {},
      "reason": "why this action in this order",
      "risk": "low | medium | high",
      "risk_detail": "what could go wrong and how we'd detect it",
      "expected_result": "what we expect to see after this action",
      "rollback_action": "how to undo if this fails",
      "verification_check": "how to verify this action worked"
    }
  ],
  "total_steps": 5,
  "contingency_plan": "If primary repair fails, fallback strategy is...",
  "post_repair_validation": [
    "Check service health endpoints",
    "Verify error rate < 1%",
    "Confirm latency p99 < 500ms"
  ]
}
"""

    def get_tool_definitions(self) -> list[dict]:
        return [
            {
                "name": "create_repair_plan",
                "description": (
                    "Generate a detailed repair runbook based on the diagnostic report. "
                    "Includes step-by-step actions with risk assessment, rollback plans, "
                    "and verification checks for each step."
                ),
                "parameters": [
                    {
                        "name": "diagnosis",
                        "type": "string",
                        "description": "Diagnostic agent's structured diagnosis report (JSON)",
                        "required": True,
                    }
                ],
            },
            {
                "name": "execute_repair",
                "description": (
                    "Execute a single repair action from the runbook. "
                    "Returns the result including success/failure, actions taken, "
                    "side effects, and post-fix system snapshot."
                ),
                "parameters": [
                    {
                        "name": "action",
                        "type": "string",
                        "description": (
                            "Repair action type: restart_service | rollback_deploy | kill_process | "
                            "clear_cache | scale_up | cleanup_disk | fix_config | add_index | "
                            "failover_replica | drain_connections | circuit_breaker_reset"
                        ),
                        "required": True,
                    },
                    {
                        "name": "target",
                        "type": "string",
                        "description": "Target service name, PID, or resource",
                        "required": False,
                    },
                    {
                        "name": "params",
                        "type": "object",
                        "description": "Additional parameters for the action (e.g., config_key for fix_config)",
                        "required": False,
                    },
                ],
            },
            {
                "name": "verify_health",
                "description": (
                    "Run post-repair health verification. Checks all servers and services "
                    "for remaining issues and SLO violations."
                ),
                "parameters": [],
            },
            {
                "name": "rollback_last_action",
                "description": (
                    "Attempt to rollback the last executed repair action. "
                    "Only available if the last action was reversible."
                ),
                "parameters": [
                    {
                        "name": "action",
                        "type": "string",
                        "description": "The action to rollback",
                        "required": True,
                    },
                    {
                        "name": "target",
                        "type": "string",
                        "description": "The target that was acted upon",
                        "required": False,
                    },
                ],
            },
        ]

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        if tool_name == "create_repair_plan":
            return await self._create_repair_plan(arguments.get("diagnosis", ""))
        elif tool_name == "execute_repair":
            return await self._execute_repair(
                arguments.get("action", ""),
                arguments.get("target", ""),
                arguments.get("params"),
            )
        elif tool_name == "verify_health":
            return self._verify_repair()
        elif tool_name == "rollback_last_action":
            return await self._rollback(
                arguments.get("action", ""),
                arguments.get("target", ""),
            )
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    async def _create_repair_plan(self, diagnosis: str) -> str:
        """Generate a repair runbook from the diagnostic report."""
        # Get current system state for context
        health = self.infra.health_check()
        health_str = json.dumps(health, ensure_ascii=False, indent=2)

        user_msg = f"""## Diagnostic Report

{diagnosis}

## Current System Health

```json
{health_str}
```

## Your Task

Create a repair runbook based on the diagnosis. Follow these priorities:

1. **Mitigate** (first): Immediate actions to reduce user impact
   - Scale up healthy instances
   - Reset circuit breakers
   - Reroute traffic if possible

2. **Resolve** (second): Fix the root cause
   - Apply the specific fix identified in the diagnosis
   - Use the least risky action that will work

3. **Verify** (third): Confirm the fix worked
   - Check service health
   - Verify metrics returned to normal
   - Confirm error rates dropped

4. **Prevent** (last): Actions to prevent recurrence
   - Configuration changes
   - Monitoring improvements
   - Runbook updates

For each step, specify:
- The exact action and target
- Why this action is needed
- Risk level and what could go wrong
- How to verify it worked
- How to rollback if it fails
"""

        plan = await self.call_llm(self.repair_prompt, user_msg)
        self.logger.info(f"Repair plan created ({len(plan)} chars)")
        return plan

    async def _execute_repair(self, action: str, target: str, params: dict = None) -> str:
        """Execute a single repair action and return the result."""
        self.logger.info(f"Executing repair: {action} -> {target}")
        result = self.infra.apply_fix(action, target, params)
        self.logger.info(
            f"Repair result: {action}/{target} -> "
            f"success={result['success']}, msg={result['message']}"
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _verify_repair(self) -> str:
        """Run post-repair health verification."""
        health = self.infra.health_check()
        return json.dumps(health, ensure_ascii=False, indent=2)

    async def _rollback(self, action: str, target: str) -> str:
        """Attempt to rollback a repair action."""
        rollback_map = {
            "restart_service": ("restart_service", target),  # restart again
            "rollback_deploy": ("rollback_deploy", target),  # re-deploy forward
            "scale_up": ("scale_down", target),
            "clear_cache": None,  # cannot un-flush cache
            "fix_config": ("fix_config", target),
            "add_index": ("drop_index", target),
            "cleanup_disk": None,  # cannot un-delete
        }

        rollback_info = rollback_map.get(action)
        if rollback_info is None:
            return json.dumps({
                "success": False,
                "message": f"Action '{action}' is not reversible",
                "recommendation": "Manual intervention required",
            })

        rollback_action, rollback_target = rollback_info
        self.logger.info(f"Rolling back: {action}/{target} -> {rollback_action}/{rollback_target}")
        result = self.infra.apply_fix(rollback_action, rollback_target)
        result["rollback_of"] = f"{action}/{target}"
        return json.dumps(result, ensure_ascii=False, indent=2)


def create_repair_agent(infra: InfrastructureSimulator) -> RepairAgent:
    return RepairAgent(infra)