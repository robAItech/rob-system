from pathlib import Path
from typing import Optional

from core.gbrain_bridge import GBrainBridge
from core.graphify_bridge import GraphifyBridge
from core.gstack_bridge import GSTACKArchitectBridge
from core.hermes_bridge import HermesBuilderBridge
from core.loopx_bridge import LoopXEngineBridge

class RobAIOrchestrator:
    @staticmethod
    def _required_test_files(directive: str) -> list:
        """Izvleci imena test datotek iz MODIFY direktive (npr. test_x.py / x_test.py).

        Heal zanka mora te teste USTVARITI (in morajo preiti) — sicer bi bil
        "zelen" le potrditev obstojecih testov, ne izvedba spremembe.
        """
        import re
        return sorted({f"{m}.py" for m in re.findall(
            r"\b(test_[A-Za-z0-9_]+|[A-Za-z0-9_]+_test)\.py\b", directive or "")})

    @staticmethod
    def _phase(project: str, directive: str, label: str, goal: Optional[str] = None,
               require_change: bool = False,
               required_files: Optional[list] = None) -> bool:
        """Izvede en GStack/RSI fazni tek (gbrain → gstack → hermes → loopx).

        `goal` (P1): čisti cilj naloge — zapiše se v run_reviews.goal (namesto
        morebitnega [PLAN KONTEKST] prefiksa v `directive`).

        `require_change` (MODIFY): modifikacijska naloga mora DEJANSKO spremeniti
        modul — če je build zelen, a nobena datoteka ni spremenjena (false green,
        npr. refaktor na že-zelenem modulu), se šteje kot neuspeh.
        """
        print(f"  ── Faza '{label}' zanke ──")
        # 1. GBRAIN: kontekst in prepovedani vzorci
        gbrain = GBrainBridge()
        blacklists = gbrain.get_blacklists(project)
        # 2. GRAPHIFY: AST graf
        graphify = GraphifyBridge()
        graphify.build_code_graph()
        # 3. GSTACK: arhitekturna specifikacija
        #    Graf-kontekst se posreduje v manifest (dependency_context), da spec
        #    nosi pregled odvisnosti za kasnejšo LLM uporabo.
        try:
            graph_ctx = graphify.render_context(project)
        except Exception:
            graph_ctx = ""
        gstack = GSTACKArchitectBridge(blacklists, code_graph_context=graph_ctx)
        manifest = gstack.generate_manifest(project, directive)
        # P0 — spec_hint: GStack blueprint + blacklists postanejo LLM usmeritev.
        spec_hint = gstack.render_spec_hint(manifest)
        # 4. HERMES: ogrodje/datoteke
        hermes = HermesBuilderBridge(project)
        hermes.write_initial_stubs_if_missing()
        # 5. LOOPX: verifikacijska + samoozdravitvena zanka
        loopx = LoopXEngineBridge(project)
        loopx.required_files = required_files or []   # MODIFY: testi iz direktive
        ok = loopx.execute_and_heal(directive, spec_hint=spec_hint)
        # MODIFY guard — modifikacijska naloga mora dejansko spremeniti modul;
        # sicer je "zelen" le potrditev obstoječega stanja → FALSE GREEN.
        if require_change and ok and not loopx._module_changed():
            print(f"[ORCH] modifikacija '{project}': zelen, a nobena datoteka "
                  f"ni spremenjena (false green).", flush=True)
            ok = False
            loopx.last_reason = ("zelen, a nobena datoteka ni spremenjena — "
                                 "zahtevana sprememba ni bila izvedena")
            loopx.last_traceback = ""
        RobAIOrchestrator._post_run_review(project, directive, goal, loopx, ok, spec_hint)
        print(f"  ── Faza '{label}': {'ZELEN' if ok else 'FAIL'} ──")
        return ok

    @staticmethod
    def _post_run_review(project: str, directive: str, goal: Optional[str],
                         loopx, ok: bool, spec_hint: str) -> None:
        """Zanka 2 — post-run samoevalvacija + C2 fix-enqueue (deljeno: _phase in
        run_surgical). Nikoli ne blokira builda."""
        run = {
            "project": project,
            "directive": directive,
            "goal": goal or directive,
            "plan": (spec_hint or "")[:1000],
            "task_type": LoopXEngineBridge._detect_kind(goal or directive),
            "outcome": "green" if ok else "failed",
            "traceback": getattr(loopx, "last_reason", "") or "",
            "last_traceback": getattr(loopx, "last_traceback", "") or "",
            "llm_calls": loopx.llm_calls,
            "attempts": loopx.max_attempts,
            "spec_hint": spec_hint,
        }
        review_result = None
        try:
            from core.run_review import RunReviewer
            review_result = RunReviewer(loopx.gbrain.db_path).review(run)
        except Exception as e:
            print(f"[ORCH] post-run review preskočen: {e}", flush=True)
        # C2 — zapri zanko neuspeha: padel build → konkretna fix naloga v agendo
        # (daemon jo pobere; `next_step` se konzumira v direktivi). Nikoli ne blokira.
        if not ok and review_result is not None:
            try:
                RunReviewer(loopx.gbrain.db_path).maybe_enqueue_fix(run, review_result)
            except Exception as e:
                print(f"[ORCH] enqueue fix preskočen: {e}", flush=True)

    @staticmethod
    def run(project: str, directive: str) -> bool:
        print(f"🚀 [ROB AI STUDIO] Inicializacija zahteve za modul: '{project}'")
        print(f"📜 Direktiva: '{directive}'")
        success = RobAIOrchestrator._phase(project, directive, "implementacija")
        if success:
            print(f"✅ Modul '{project}' uspešno potrjen (100% VERIFIED GREEN)!")
        else:
            print(f"❌ Napaka pri verifikaciji modula '{project}'. Traceback zablokiran v GBRAIN.")
        return success

    @staticmethod
    def run_modify(project: str, directive: str, goal: Optional[str] = None) -> bool:
        """MODIFY — modifikacijska naloga na OBSTOJEČEM modulu.

        Kot `run`, a z `require_change=True`: če je build zelen, a nobena
        datoteka ni spremenjena (false green — npr. "izboljšaj X" na že-zelenem
        modulu, kjer RSI samo potrdi obstoječe stanje), se šteje kot neuspeh.
        """
        print(f"🔧 [MODIFY] Modifikacija modula '{project}': '{directive[:80]}'")
        # MODIFY: testi iz direktive (npr. test_truncate_start.py) morajo obstajati
        # in preiti — heal jih mora ustvariti, da sprememba res nastane.
        required = RobAIOrchestrator._required_test_files(directive)
        if required:
            print(f"🔧 [MODIFY] zahtevani novi testi: {', '.join(required)}", flush=True)
        success = RobAIOrchestrator._phase(project, directive, "modifikacija",
                                           goal=goal, require_change=True,
                                           required_files=required)
        if success:
            print(f"✅ Modul '{project}' modificiran in potrjen (sprememba izvedena).")
        else:
            print(f"❌ Modifikacija '{project}' neuspešna (ali ni bila izvedena nobena sprememba).")
        return success

    @staticmethod
    def run_surgical(project: str, directive: str, target_test: Optional[str] = None,
                     goal: Optional[str] = None) -> bool:
        """C2/SURGICAL — kirurški popravek obstoječega modula (fix naloga).

        Reduciran RSI tek: gbrain (blacklisti) + graphify (svež graf) za kontekst,
        nato LoopX v surgical načinu — BREZ gstack manifesta (spec_hint="") in BREZ
        hermes stubov, da LLM ne re-scaffolda celega modula. Targeted verifikacija
        (`pytest -k <test>`) med healom + poln no-regression gate na koncu.
        """
        print(f"  ── SURGICAL FIX za '{project}' (target test: {target_test or 'cel suite'}) ──")
        # Varnost: če modul ne obstaja (ali nima .py), ni kaj kirurško popraviti → poln build.
        target_dir = Path(f"actions/{project}")
        if not target_dir.exists() or not list(target_dir.glob("*.py")):
            print(f"[ORCH] '{project}' nima obstoječih .py — surgical ni možen; poln build.",
                  flush=True)
            return RobAIOrchestrator._phase(project, directive, "implementacija", goal=goal)
        # 1. GBRAIN + GRAPHIFY kontekst (svež graf — vključi morebitno sveže bugirano kopijo).
        try:
            GBrainBridge().get_blacklists(project)
            GraphifyBridge().build_code_graph()
        except Exception:
            pass
        # 2. LOOPX v surgical načinu.
        loopx = LoopXEngineBridge(project)
        loopx.surgical = True
        loopx.target_test = (target_test or "").strip() or None
        ok = loopx.execute_and_heal(directive, spec_hint="")
        # 3. Post-run samoevalvacija + C2 (neuspeh → nov fix item do FIX_MAX_ATTEMPTS).
        RobAIOrchestrator._post_run_review(project, directive, goal, loopx, ok, spec_hint="")
        return ok

    @staticmethod
    def run_autonomous(project: str, goal: str, context: Optional[str] = None) -> bool:
        """Faza 2 — avtonomno podjetje: nalogo razčleni na več RSI faz in
        vsako izvede (SPEC → IMPLEMENT). Menedžer načrtuje, RSI zanka gradi.

        Determinating (no LLM planiranje): iz cilja, če cilj zveni kot dokument/
        Markdown → samo spec; sicer spec + implement.

        P2 — plan kontekst: če ni podan, se zgradi iz naučenega (pretekle lekcije
        + world-model napoved, max 1500 znakov) in vstavi v spec/impl direktive.
        """
        print(f"🤖 [F2] Avtonomni delovnik za: '{goal}'")
        if context is None:
            try:
                from core.plan_context import build_plan_context
                context = build_plan_context(project=project, goal=goal, max_chars=1500)
            except Exception:
                context = ""
        g = goal.lower()
        # Preprost menedžerjev načrt: ali želiš dokument ali modul?
        wants_doc = any(w in g for w in ("markdown", "predlog", "poročilo", "roadmap", "dokument"))
        if wants_doc:
            # Samo ena faza — dokument (MD/HTML) izdelava.
            return RobAIOrchestrator._phase(project, goal, "dokument", goal=goal)
        # Dvofaza: spec (MD) + implementacija (Python).
        spec_directive = f"Izdelaj Markdown specifikacijo v actions/{project}/ za naslednji cilj: {goal}. Vsebuj naslov #, odstavke in načrt."
        impl_directive = f"Izdelaj Python modul {project} v actions/{project}/, ki uresniči cilj: {goal}. Vsebuj funkcionalne funkcije in pytest test, vsi testi 100% zeleni."
        if context:
            from core.plan_context import prepend_context
            spec_directive = prepend_context(spec_directive, context)
            impl_directive = prepend_context(impl_directive, context)
        ok_spec = RobAIOrchestrator._phase(project, spec_directive, "specifikacija", goal=goal)
        if not ok_spec:
            print(f"❌ [F2] Specifikacijska faza ni zelena — avtonomni delovnik prekinjen.")
            return False
        # Spec shranimo kot dokument zraven; nato implement.
        ok_impl = RobAIOrchestrator._phase(project, impl_directive, "implementacija", goal=goal)
        print("✅ [F2] Avtonomni delovnik končan."
              f" spec={'ZELEN' if ok_spec else 'X'} / implement={'ZELEN' if ok_impl else 'X'}")
        return ok_impl

    @staticmethod
    def run_decomposed(project: str, goal: str, max_steps: int = 8) -> dict:
        """Zanka 5 — dolgoročno načrtovanje: razbij cilj na podcilje in izvedi
        vsakega skozi RSI zanko. Vrne povzetek (ne samo bool), da je napredek
        viden po korakih.
        """
        from core.task_planner import TaskPlanner
        planner = TaskPlanner()
        print(f"🧩 [Z5] Dekompozicija cilja: '{goal}'")
        try:
            from core.plan_context import build_plan_context
            ctx = build_plan_context(project=project, goal=goal, max_chars=1500)
        except Exception:
            ctx = ""
        return planner.execute(
            goal,
            executor=lambda subgoal: RobAIOrchestrator._phase(project, subgoal, "podcilj", goal=subgoal),
            max_steps=max_steps,
            context=ctx,
        )