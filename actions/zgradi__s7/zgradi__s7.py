"""zgradi__s7.py — jedro domenske logike (čista async logika).

Engine preveri, da so vsi pričakovani moduli prisotni, da imajo vse obvezne
faze (schema, logic, api, tests), da noben ni v stanju FAILED, nato zgradi
deterministično integracijsko poročilo. Vsa logika je async in brez
stranskih učinkov (ni I/O, ni globalnega stanja).
"""

import asyncio
from typing import Dict, List, Sequence, Tuple

try:  # paketni uvoz (pytest z basedir nad actions/)
    from .schemas import (
        IntegrationIssue,
        IntegrationPhase,
        IntegrationRequest,
        IntegrationResult,
        ModuleSpec,
        ModuleStatus,
    )
except ImportError:  # pragma: no cover — neposredni uvoz modula
    from schemas import (  # type: ignore
        IntegrationIssue,
        IntegrationPhase,
        IntegrationRequest,
        IntegrationResult,
        ModuleSpec,
        ModuleStatus,
    )

# Pet modulov, ki tvorijo povezan sistem zgradi__s7.
EXPECTED_MODULES: Tuple[str, ...] = (
    "__init__",
    "schemas",
    "zgradi__s7",
    "main",
    "test_zgradi__s7",
)

# Faze, ki jih mora imeti vsak modul, da velja za integriranega.
REQUIRED_PHASES: Tuple[IntegrationPhase, ...] = (
    IntegrationPhase.SCHEMA,
    IntegrationPhase.LOGIC,
    IntegrationPhase.API,
    IntegrationPhase.TESTS,
)


class IntegrationEngine:
    """Async pogon za integracijo petih modulov v povezan sistem."""

    def __init__(self) -> None:
        self.expected_modules: Tuple[str, ...] = EXPECTED_MODULES
        self.required_phases: Tuple[IntegrationPhase, ...] = REQUIRED_PHASES

    async def health(self) -> Dict[str, object]:
        """Health-check brez stranskih učinkov (ohranjamo async kontrakt)."""
        await asyncio.sleep(0)
        return {
            "service": "zgradi__s7",
            "status": "ok",
            "expected_modules": list(self.expected_modules),
            "expected_module_count": len(self.expected_modules),
        }

    def missing_modules(self, request: IntegrationRequest) -> List[str]:
        """Vrne imena pričakovanih modulov, ki v zahtevku manjkajo."""
        present = {module.name for module in request.modules}
        return [name for name in self.expected_modules if name not in present]

    def _phase_gaps(self, module: ModuleSpec) -> List[IntegrationPhase]:
        """Vrne obvezne faze, ki jih modul še nima."""
        return [phase for phase in self.required_phases if phase not in module.phases]

    def _validate_request(self, request: IntegrationRequest) -> List[IntegrationIssue]:
        """Preveri prisotnost, stanje in fazno popolnost vseh modulov."""
        issues: List[IntegrationIssue] = []
        by_name = {module.name: module for module in request.modules}

        for name in self.expected_modules:
            module = by_name.get(name)
            if module is None:
                issues.append(
                    IntegrationIssue(
                        module=name,
                        phase=IntegrationPhase.SCHEMA,
                        message=f"manjka zahtevani modul '{name}'",
                    )
                )
                continue
            if module.status is ModuleStatus.FAILED:
                issues.append(
                    IntegrationIssue(
                        module=name,
                        phase=IntegrationPhase.SCHEMA,
                        message=f"modul '{name}' je v stanju FAILED",
                    )
                )

        for module in request.modules:
            gaps = self._phase_gaps(module)
            if gaps:
                missing = ", ".join(phase.value for phase in gaps)
                issues.append(
                    IntegrationIssue(
                        module=module.name,
                        phase=gaps[0],
                        message=f"modul '{module.name}' nima faz: {missing}",
                    )
                )

        return issues

    async def integrate(self, request: IntegrationRequest) -> IntegrationResult:
        """Integrira prijavljene module in vrne poročilo.

        Uspeh = prisotni vsi pričakovani moduli, noben ni FAILED in vsak ima
        vse obvezne faze. Rezultat je determinističen.
        """
        await asyncio.sleep(0)
        issues = self._validate_request(request)
        ok = not issues
        integrated = sorted(module.name for module in request.modules) if ok else []
        report = self.build_report(request, ok, integrated, issues)
        return IntegrationResult(
            ok=ok, integrated=integrated, issues=issues, report=report
        )

    def build_report(
        self,
        request: IntegrationRequest,
        ok: bool,
        integrated: Sequence[str],
        issues: Sequence[IntegrationIssue],
    ) -> str:
        """Zgradi človeško berljivo poročilo o integraciji."""
        lines: List[str] = []
        lines.append("Integracijsko poročilo: zgradi__s7")
        lines.append("=" * 42)
        lines.append(f"opis: {request.description or '-'}")
        lines.append(
            f"prijavljeni moduli ({len(request.modules)}): "
            + ", ".join(sorted(module.name for module in request.modules))
        )
        if ok:
            lines.append(f"status: OK — integrirano {len(integrated)} modulov")
            lines.append("integrirani: " + ", ".join(sorted(integrated)))
        else:
            lines.append(f"status: NEUSPEH — {len(issues)} težav")
            for issue in issues:
                lines.append(
                    f"  - [{issue.phase.value}] {issue.module}: {issue.message}"
                )
        return "\n".join(lines) + "\n"
