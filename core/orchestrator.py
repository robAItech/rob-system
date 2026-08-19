from core.gbrain_bridge import GBrainBridge
from core.graphify_bridge import GraphifyBridge
from core.gstack_bridge import GSTACKArchitectBridge
from core.hermes_bridge import HermesBuilderBridge
from core.loopx_bridge import LoopXEngineBridge

class RobAIOrchestrator:
    @staticmethod
    def _phase(project: str, directive: str, label: str) -> bool:
        """Izvede en GStack/RSI fazni tek (gbrain → gstack → hermes → loopx)."""
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
        ok = loopx.execute_and_heal(directive, spec_hint=spec_hint)
        # Zanka 2 — post-run samoevalvacija odločitev (produkcijska pot; ne blokira).
        try:
            from core.run_review import RunReviewer
            RunReviewer(loopx.gbrain.db_path).review({
                "project": project,
                "directive": directive,
                "outcome": "green" if ok else "failed",
                "traceback": getattr(loopx, "last_reason", "") or "",
                "llm_calls": loopx.llm_calls,
                "attempts": loopx.max_attempts,
                "spec_hint": spec_hint,
            })
        except Exception as e:
            print(f"[ORCH] post-run review preskočen: {e}", flush=True)
        print(f"  ── Faza '{label}': {'ZELEN' if ok else 'FAIL'} ──")
        return ok

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
    def run_autonomous(project: str, goal: str) -> bool:
        """Faza 2 — avtonomno podjetje: nalogo razčleni na več RSI faz in
        vsako izvede (SPEC → IMPLEMENT). Menedžer načrtuje, RSI zanka gradi.

        Determinating (no LLM planiranje): iz cilja, če cilj zveni kot dokument/
        Markdown → samo spec; sicer spec + implement.
        """
        print(f"🤖 [F2] Avtonomni delovnik za: '{goal}'")
        g = goal.lower()
        # Preprost menedžerjev načrt: ali želiš dokument ali modul?
        wants_doc = any(w in g for w in ("markdown", "predlog", "poročilo", "roadmap", "dokument"))
        if wants_doc:
            # Samo ena faza — dokument (MD/HTML) izdelava.
            return RobAIOrchestrator._phase(project, goal, "dokument")
        # Dvofaza: spec (MD) + implementacija (Python).
        spec_directive = f"Izdelaj Markdown specifikacijo v actions/{project}/ za naslednji cilj: {goal}. Vsebuj naslov #, odstavke in načrt."
        impl_directive = f"Izdelaj Python modul {project} v actions/{project}/, ki uresniči cilj: {goal}. Vsebuj funkcionalne funkcije in pytest test, vsi testi 100% zeleni."
        ok_spec = RobAIOrchestrator._phase(project, spec_directive, "specifikacija")
        if not ok_spec:
            print(f"❌ [F2] Specifikacijska faza ni zelena — avtonomni delovnik prekinjen.")
            return False
        # Spec shranimo kot dokument zraven; nato implement.
        ok_impl = RobAIOrchestrator._phase(project, impl_directive, "implementacija")
        print("✅ [F2] Avtonomni delovnik končan."
              f" spec={'ZELEN' if ok_spec else 'X'} / implement={'ZELEN' if ok_impl else 'X'}")
        return ok_impl