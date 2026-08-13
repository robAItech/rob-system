from bridges.llm_bridge import LLMBridge

def main():
    llm = LLMBridge()
    
    system_prompt = """Si GSTACK-Architect, glavni inženir za avtonomne sisteme. 
Naš ekosistem (Rob AI Studio) trenutno obsega 21 Enterprise modulov, ki vključujejo:
- Saga Orchestrator (distribuirane transakcije)
- Schema Registry (validacije)
- Unified Gateway (enoten vstop)
- Avtonomni CLI motor za samodejno generiranje kode in izvajanje Pytest testov (ki se že zna avtomatsko zdraviti v primeru napak).
"""

    prompt = """Uporabnik predlaga naslednje: "Recursive Self-Improvement (RSI) as an autonomous, closed-loop engine."

Tvoja naloga:
1. OCENA POTREBE: Ali naš 21-modularni sistem dejansko potrebuje RSI zanko ali je to 'over-engineering'? Bodi brutalno inženirsko iskren.
2. MEHANIKA: Če je RSI potreben, KAKO ga integriramo v naš obstoječi "rob build/test" ekosistem? Kako zapremo zanko (closed-loop), da bo sistem proaktivno in avtonomno iskal podoptimalno kodo (npr. znotraj core_utils), napisal boljšo različico, pognal teste in jo sam zamenjal?
3. TVEGANJA: Kaj so največje nevarnosti (npr. avtomatska degradacija, halucinacije v produkciji) in kako jih preprečimo s pomočjo obstoječega Contract Testinga in Saga vzorcev?

Standard je 'Holy shit, that's done'. Podaj popoln, inženirsko natančen načrt."""

    print("=" * 80)
    print("🧠 INICIALIZACIJA DIREKTNEGA KLICA: Analiza RSI (Recursive Self-Improvement)")
    print("=" * 80)
    
    response = llm.complete(prompt, system_prompt=system_prompt)
    
    print("\n📋 ODGOVOR AI ARHITEKTA:\n")
    print(response)
    print("=" * 80)

if __name__ == "__main__":
    main()
