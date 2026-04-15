from __future__ import annotations


class FuelManager:
    # hardcoded prices for now, we should probably pull this from a config later
    TOOL_BASE_COST = {
        "gemini": 12,
        "codex": 16,
        "unassigned": 4,
    }

    def calculate(self, tool: str, output: str) -> dict[str, int]:
        base = self.TOOL_BASE_COST.get(tool, 8)
        
        # super rough token estimation just splitting on spaces
        output_tokens = max(1, len(output.split()))
        total = base + output_tokens
        
        return {
            "base_cost": base,
            "output_tokens": output_tokens,
            "total_cost": total,
        }
