"""Testes de sanidade da simulação. Rode: python testes.py"""
import simulador_goodwe as sg


def checar(nome, cond):
    print(("OK   " if cond else "FALHA"), nome)
    return cond


def main():
    ok = True
    for estrategia in ("imediata", "inteligente"):
        res, serie = sg.simular(estrategia)
        # 1) todas as sessões de recarga concluídas
        ok &= checar(f"[{estrategia}] 3/3 sessões concluídas", res["sessoes_concluidas"] == "3/3")
        # 2) SoC sempre dentro dos limites físicos (reserva 20 % a 100 %)
        socs = [s["soc_pct"] for s in serie]
        ok &= checar(f"[{estrategia}] SoC entre 19,9 % e 100 %", min(socs) >= 19.9 and max(socs) <= 100.01)
        # 3) potência do carregador nunca excede o limite do equipamento
        ok &= checar(f"[{estrategia}] recarga <= 7,4 kW", max(s["ev_kw"] for s in serie) <= sg.CONFIG["ev_max_kw"] + 1e-6)
        # 4) balanço de energia em cada passo: FV + rede + (descarga) = casa + VE + injeção + (carga)
        erro = max(abs(s["pv_kw"] + s["rede_kw"] - s["casa_kw"] - s["ev_kw"] - s["injecao_kw"] - s["bateria_kw"])
                   for s in serie)
        ok &= checar(f"[{estrategia}] balanço de potência fecha (erro {erro:.3f} kW)", erro < 0.02)
    a, _ = sg.simular("imediata")
    b, _ = sg.simular("inteligente")
    ok &= checar("inteligente importa menos na ponta", b["importado_na_ponta_kwh"] < a["importado_na_ponta_kwh"])
    ok &= checar("inteligente custa menos", b["custo_liquido_rs"] < a["custo_liquido_rs"])
    ok &= checar("assistente entende 'economizei'", "custo" in sg.responder("quanto economizei?", b).lower())
    ok &= checar("assistente entende 'CO2'", "CO2" in sg.responder("Quanto CO2 evitei?", b))
    print("\nTODOS OS TESTES PASSARAM" if ok else "\nHÁ FALHAS")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
