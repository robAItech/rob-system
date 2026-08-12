import re
from typing import List, Dict, Any
from actions.enterprise_rsi_engine.schemas import OptimizationTarget


class RSIAnalyzer:
    """Analyzes Python source code to find optimization targets."""

    def find_optimization_targets(self, module_code: str) -> List[OptimizationTarget]:
        """Find all function definitions and assign risk scores."""
        targets = []
        # Regex to find function definitions
        pattern = r"^\s*def\s+(\w+)\s*\("
        matches = re.finditer(pattern, module_code, re.MULTILINE)

        for match in matches:
            func_name = match.group(1)
            # Simple heuristic: functions with more lines are riskier
            # Find the function body
            start = match.end()
            # Find the next def or end of string
            next_def = re.search(r"^\s*def\s+\w+\s*\(", module_code[start:], re.MULTILINE)
            if next_def:
                end = start + next_def.start()
            else:
                end = len(module_code)

            body = module_code[start:end]
            line_count = len([line for line in body.split("\n") if line.strip()])

            # Risk score based on complexity (line count)
            risk_score = min(1.0, line_count / 20.0)

            targets.append(
                OptimizationTarget(
                    module_name="module",
                    function_name=func_name,
                    risk_score=risk_score,
                )
            )

        return targets


class RSIValidator:
    """Validates behavioral equivalence between original and optimized functions."""

    def verify_behavioral_equivalence(
        self,
        original_func: str,
        optimized_func: str,
        func_name: str,
        test_args: List[Dict[str, Any]],
    ) -> bool:
        """Execute both functions with test arguments and compare results."""
        # Create namespaces for execution
        original_ns: Dict[str, Any] = {}
        optimized_ns: Dict[str, Any] = {}

        try:
            # Execute both function definitions
            exec(original_func, original_ns)
            exec(optimized_func, optimized_ns)

            # Get the functions
            orig_fn = original_ns.get(func_name)
            opt_fn = optimized_ns.get(func_name)

            if not orig_fn or not opt_fn:
                return False

            # Test with provided arguments
            for args in test_args:
                orig_result = orig_fn(**args)
                opt_result = opt_fn(**args)

                if orig_result != opt_result:
                    return False

            return True

        except Exception:
            return False