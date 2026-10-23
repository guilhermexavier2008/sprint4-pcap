"""
Simulador de Estação de Recarga Solar com gestão inteligente (referência Goodwe).

Simula 24 h (passos de 15 min) de:
  geração FV  ->  bateria  ->  carga da casa/condomínio  ->  recarga de veículos elétricos
e compara duas estratégias de recarga:
  - "imediata":   o carro carrega na potência máxima assim que chega (sem gestão)
  - "inteligente": prioriza sol e bateria, adia a recarga e só usa a rede quando o prazo exige

Uso:
    python simulador_goodwe.py                 # roda tudo e gera resultados/
    python simulador_goodwe.py --assistente    # modo conversa (assistente virtual)

Os parâmetros ficam em CONFIG para serem ajustados conforme o datasheet do equipamento real.
"""
import csv
import json
import math
import os
import re
import sys
import unicodedata
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# --------------------------------------------------------------------------
# PARÂMETROS (valores de referência/ilustrativos -> conferir com datasheets)
# --------------------------------------------------------------------------
CONFIG = {
    "dt_h": 0.25,              # passo de simulação: 15 min
    "pv_kwp": 8.0,             # campo FV de ~8 kWp (casado com inversor híbrido GW8K-ET, 8 kW AC)
    "bat_kwh": 9.8,            # capacidade útil ~9,8 kWh (Lynx Home F Plus+, kit de 3 módulos)
    "bat_max_kw": 5.0,         # potência máx. carga/descarga (PREMISSA: conferir no datasheet)
    "bat_reserva": 0.20,       # reserva mínima (20 %)
    "bat_soc_ini": 0.50,       # SoC inicial
    "bat_eficiencia": 0.96,    # eficiência por sentido (carga e descarga)
    "ev_max_kw": 7.4,          # GW7K-HCA: 7 kW nominal, 7,4 kW por ponto de recarga
    "ev_limite_bateria": 0.35, # SoC mínimo para a bateria alimentar o carro
    "tarifa_fora_ponta": 0.85, # R$/kWh (ilustrativa)
    "tarifa_ponta": 1.80,      # R$/kWh, 18h-21h (ilustrativa)
    "credito_injecao": 0.50,   # R$/kWh injetado na rede (ilustrativo)
    "fe_rede_kg_kwh": 0.0385,  # kgCO2/kWh: média 2023 do SIN (38,5 kg/MWh, MCTI)
    "km_por_kwh": 6.0,         # eficiência do VE
    "km_por_litro": 12.0,      # carro a combustão equivalente
    "kg_co2_litro": 2.2,       # kgCO2/litro (SIMPLIFICAÇÃO p/ gasolina pura; a gasolina C emite menos CO2 fóssil)
}


@dataclass
class Sessao:
    """Sessão de recarga (mesma ideia da classe Sessao do projeto das sprints anteriores)."""
    id: int
    veiculo: str
    chegada: float   # hora decimal
    saida: float     # hora decimal
    energia_kwh: float
    entregue_kwh: float = 0.0

    @property
    def restante(self):
        return max(self.energia_kwh - self.entregue_kwh, 0.0)

    def ativa(self, h):
        return self.chegada <= h < self.saida and self.restante > 1e-6


def sessoes_do_dia():
    return [
        Sessao(1, "Carro A (home office)", 8.5, 12.5, 10.0),
        Sessao(2, "Carro B (visita)", 13.0, 17.5, 12.0),
        Sessao(3, "Carro C (morador)", 19.0, 23.75, 9.0),
    ]


# --------------------------------------------------------------------------
# MODELOS DE GERAÇÃO E CONSUMO
# --------------------------------------------------------------------------
def geracao_fv(h):
    """Curva solar em sino (6h-18h) com leve variação e uma nuvem à tarde."""
    base = max(0.0, math.sin(math.pi * (h - 6.0) / 12.0)) ** 1.3
    variacao = 0.95 + 0.05 * math.sin(h * 5.0)
    nuvem = 0.55 if 13.5 <= h < 14.25 else 1.0
    return CONFIG["pv_kwp"] * base * variacao * nuvem


def consumo_casa(h):
    """Consumo base do condomínio/residência (kW)."""
    return (0.35
            + 0.9 * math.exp(-((h - 7.2) / 1.0) ** 2)
            + 1.8 * math.exp(-((h - 19.5) / 1.6) ** 2))


def tarifa(h):
    return CONFIG["tarifa_ponta"] if 18 <= h < 21 else CONFIG["tarifa_fora_ponta"]


# --------------------------------------------------------------------------
# DESPACHO DE ENERGIA (inversor híbrido + bateria)
# --------------------------------------------------------------------------
def despachar(pv, carga, soc_kwh):
    """Balanço de potência. Retorna (import_kw, export_kw, novo_soc_kwh, fluxo_bateria_kw)."""
    c = CONFIG
    dt, eff = c["dt_h"], c["bat_eficiencia"]
    liquido = pv - carga
    if liquido >= 0:
        carga_bat = min(liquido, c["bat_max_kw"], (c["bat_kwh"] - soc_kwh) / (dt * eff))
        soc_kwh += carga_bat * dt * eff
        return 0.0, liquido - carga_bat, soc_kwh, carga_bat
    falta = -liquido
    desc = min(falta, c["bat_max_kw"], max(soc_kwh - c["bat_reserva"] * c["bat_kwh"], 0) * eff / dt)
    soc_kwh -= desc * dt / eff
    return falta - desc, 0.0, soc_kwh, -desc


# --------------------------------------------------------------------------
# ALGORITMO DE RECARGA INTELIGENTE
# --------------------------------------------------------------------------
def potencia_ev(estrategia, sessao, pv, casa, soc_kwh, h):
    c = CONFIG
    if sessao is None:
        return 0.0
    dt = c["dt_h"]
    if estrategia == "imediata":
        return min(c["ev_max_kw"], sessao.restante / dt)

    # --- inteligente ---
    tempo_restante = sessao.saida - h
    # "hora limite": se só dá tempo de terminar na potência máxima, a rede entra
    forcado = c["ev_max_kw"] if (tempo_restante - dt) * c["ev_max_kw"] <= sessao.restante else 0.0
    excedente_solar = max(pv - casa, 0.0)
    bateria_disp = (c["bat_max_kw"] * c["bat_eficiencia"]
                    if soc_kwh > c["ev_limite_bateria"] * c["bat_kwh"] else 0.0)
    alvo = min(c["ev_max_kw"], excedente_solar + bateria_disp)
    return min(max(forcado, alvo), sessao.restante / dt)


def simular(estrategia):
    c = CONFIG
    dt = c["dt_h"]
    passos = int(24 / dt)
    soc = c["bat_soc_ini"] * c["bat_kwh"]
    sessoes = sessoes_do_dia()
    serie = []
    tot = dict(pv=0, casa=0, ev=0, imp=0, exp=0, custo=0, imp_ponta=0, ev_rede=0)

    for i in range(passos):
        h = i * dt
        pv, casa = geracao_fv(h), consumo_casa(h)
        sess = next((s for s in sessoes if s.ativa(h)), None)
        p_ev = potencia_ev(estrategia, sess, pv, casa, soc, h)
        if sess:
            sess.entregue_kwh += p_ev * dt
        imp, exp, soc, bat = despachar(pv, casa + p_ev, soc)

        # parcela da recarga atendida pela rede (proporcional à demanda do instante)
        if p_ev > 0 and (casa + p_ev) > 0:
            tot["ev_rede"] += p_ev * dt * min(1.0, imp / (casa + p_ev))
        tot["pv"] += pv * dt
        tot["casa"] += casa * dt
        tot["ev"] += p_ev * dt
        tot["imp"] += imp * dt
        tot["exp"] += exp * dt
        tot["custo"] += imp * dt * tarifa(h) - exp * dt * c["credito_injecao"]
        if 18 <= h < 21:
            tot["imp_ponta"] += imp * dt
        serie.append(dict(hora=round(h, 2), pv_kw=round(pv, 3), casa_kw=round(casa, 3),
                          ev_kw=round(p_ev, 3), rede_kw=round(imp, 3), injecao_kw=round(exp, 3),
                          bateria_kw=round(bat, 3), soc_pct=round(100 * soc / c["bat_kwh"], 1)))

    concluidas = sum(1 for s in sessoes if s.restante < 0.05)
    autoconsumo = (tot["pv"] - tot["exp"]) / tot["pv"] * 100 if tot["pv"] else 0
    autossuf = (1 - tot["imp"] / (tot["casa"] + tot["ev"])) * 100
    frac_solar_ev = (1 - tot["ev_rede"] / tot["ev"]) * 100 if tot["ev"] else 0
    km = tot["ev"] * c["km_por_kwh"]
    co2_comb = km / c["km_por_litro"] * c["kg_co2_litro"]
    co2_rede = tot["imp"] * c["fe_rede_kg_kwh"]
    res = {
        "estrategia": estrategia,
        "geracao_fv_kwh": round(tot["pv"], 1),
        "consumo_casa_kwh": round(tot["casa"], 1),
        "energia_recarga_kwh": round(tot["ev"], 1),
        "sessoes_concluidas": f"{concluidas}/{len(sessoes)}",
        "importado_rede_kwh": round(tot["imp"], 1),
        "importado_na_ponta_kwh": round(tot["imp_ponta"], 1),
        "injetado_rede_kwh": round(tot["exp"], 1),
        "autoconsumo_fv_pct": round(autoconsumo, 1),
        "autossuficiencia_pct": round(autossuf, 1),
        "fracao_solar_da_recarga_pct": round(frac_solar_ev, 1),
        "custo_liquido_rs": round(tot["custo"], 2),
        "km_rodados_equivalentes": round(km, 0),
        "co2_evitado_vs_combustao_kg": round(co2_comb - co2_rede, 1),
        "co2_emitido_rede_kg": round(co2_rede, 2),
    }
    return res, serie


# --------------------------------------------------------------------------
# GRÁFICOS E SAÍDAS
# --------------------------------------------------------------------------
def grafico_fluxos(serie, caminho, titulo):
    h = [s["hora"] for s in serie]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                                 gridspec_kw={"height_ratios": [3, 1.3]})
    a1.fill_between(h, [s["pv_kw"] for s in serie], color="#f5b82e", alpha=.45, label="Geração FV")
    a1.plot(h, [s["casa_kw"] for s in serie], color="#2b6cb0", lw=2, label="Consumo da casa")
    a1.plot(h, [s["ev_kw"] for s in serie], color="#2f9e44", lw=2.2, label="Recarga do VE")
    a1.plot(h, [s["rede_kw"] for s in serie], color="#c92a2a", lw=1.8, ls="--", label="Importação da rede")
    a1.set_ylabel("Potência (kW)")
    a1.set_title(titulo)
    a1.legend(loc="upper left", ncol=2)
    a1.grid(alpha=.3)
    a2.plot(h, [s["soc_pct"] for s in serie], color="#7048e8", lw=2)
    a2.axhline(20, color="gray", ls=":", lw=1)
    a2.set_ylabel("SoC bateria (%)")
    a2.set_xlabel("Hora do dia")
    a2.set_ylim(0, 105)
    a2.set_xticks(range(0, 25, 2))
    a2.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(caminho, dpi=140)
    plt.close(fig)


def grafico_comparacao(r_a, r_b, caminho):
    itens = [("importado_rede_kwh", "Importado da rede (kWh)"),
             ("importado_na_ponta_kwh", "Importado na ponta (kWh)"),
             ("custo_liquido_rs", "Custo líquido (R$)"),
             ("fracao_solar_da_recarga_pct", "Recarga solar (%)")]
    fig, eixos = plt.subplots(1, 4, figsize=(13, 3.8))
    for ax, (k, nome) in zip(eixos, itens):
        v = [r_a[k], r_b[k]]
        barras = ax.bar(["Imediata", "Inteligente"], v, color=["#868e96", "#2f9e44"])
        ax.set_title(nome, fontsize=10)
        for b, x in zip(barras, v):
            ax.text(b.get_x() + b.get_width() / 2, x, f"{x:.1f}", ha="center", va="bottom", fontsize=9)
        ax.grid(axis="y", alpha=.3)
    fig.tight_layout()
    fig.savefig(caminho, dpi=140)
    plt.close(fig)


def diagrama_arquitetura(caminho):
    fig, ax = plt.subplots(figsize=(12, 6.2))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6.2)
    ax.axis("off")

    def caixa(x, y, w, h, txt, cor):
        ax.add_patch(plt.Rectangle((x, y), w, h, fc=cor, ec="#333", lw=1.4, zorder=2))
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", fontsize=9.5, zorder=3)

    def seta(x1, y1, x2, y2, txt="", cor="#333"):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", lw=1.6, color=cor), zorder=1)
        if txt:
            ax.text((x1 + x2) / 2, (y1 + y2) / 2 + .12, txt, ha="center", fontsize=8, color=cor)

    caixa(.2, 4.3, 2.2, 1.2, "Painéis solares\n(geração FV)", "#ffe8a3")
    caixa(3.6, 4.3, 2.6, 1.2, "Inversor híbrido\nGoodWe GW8K-ET", "#b8d8ff")
    caixa(3.6, 2.2, 2.6, 1.2, "Bateria\nGoodWe Lynx Home F Plus+", "#d9c9ff")
    caixa(7.4, 4.3, 2.2, 1.2, "Carga da\ncasa/condomínio", "#d3f0d8")
    caixa(7.4, 2.2, 2.2, 1.2, "Carregador VE\nGoodWe GW7K-HCA", "#b2f2bb")
    caixa(.2, 2.2, 2.2, 1.2, "Rede elétrica\n+ smart meter", "#ffc9c9")
    caixa(3.2, .1, 3.4, 1.2, "Backend Python\n(simulador + algoritmo\nde recarga inteligente)", "#fff3bf")
    caixa(7.2, .1, 2.6, 1.2, "Dashboard web\n+ assistente virtual\n(estilo SEMS)", "#e5dbff")
    caixa(10.2, 2.2, 1.6, 1.2, "Motorista\n(VE)", "#dee2e6")

    seta(2.4, 4.9, 3.6, 4.9, "DC")
    seta(4.9, 4.3, 4.9, 3.4, "carga/descarga")
    seta(6.2, 4.9, 7.4, 4.9, "AC")
    seta(6.2, 4.6, 7.4, 2.9, "AC")
    seta(2.4, 2.8, 3.6, 4.5, "import/export")
    seta(9.6, 2.8, 10.2, 2.8)
    seta(4.9, 2.2, 4.9, 1.3, "telemetria", "#555")
    seta(8.2, 2.2, 6.6, 1.0, "", "#555")
    ax.text(8.6, 1.55, "telemetria", fontsize=8, color="#555")
    seta(6.6, .7, 7.2, .7, "dados", "#555")
    seta(5.4, 1.3, 7.7, 2.2, "", "#2f9e44")
    ax.text(5.35, 1.85, "comando de potência", fontsize=8, color="#2f9e44")
    ax.set_title("Arquitetura da solução - geração, armazenamento, uso e monitoramento", fontsize=12)
    fig.tight_layout()
    fig.savefig(caminho, dpi=140)
    plt.close(fig)


def salvar_csv(serie, caminho):
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(serie[0].keys()))
        w.writeheader()
        w.writerows(serie)


# --------------------------------------------------------------------------
# ASSISTENTE VIRTUAL (regras simples sobre os resultados da simulação)
# --------------------------------------------------------------------------
def _normalizar(texto):
    t = unicodedata.normalize("NFD", texto.lower())
    return "".join(ch for ch in t if unicodedata.category(ch) != "Mn")


def responder(pergunta, r):
    """Assistente por regras: reconhece radicais de palavras (ex.: econom -> economia/economizei)."""
    p = _normalizar(pergunta)
    if re.search(r"co2|carbono|ambient|emiss|sustent", p):
        return (f"A recarga evitou cerca de {r['co2_evitado_vs_combustao_kg']} kg de CO2 em comparação "
                f"com rodar {int(r['km_rodados_equivalentes'])} km com um carro a combustão.")
    if re.search(r"econom|custo|gast|dinheiro|reais|conta|pag", p):
        return f"O custo líquido de energia do dia foi R$ {r['custo_liquido_rs']:.2f} (tarifas ilustrativas)."
    if re.search(r"bateria|soc|armazen", p):
        return ("A bateria carrega com o excedente solar e alimenta a casa e o carro à noite, "
                "respeitando a reserva mínima de 20%.")
    if re.search(r"recarga|carro|carreg|veicul|ev\b", p):
        return (f"Foram entregues {r['energia_recarga_kwh']} kWh ({r['sessoes_concluidas']} sessões concluídas), "
                f"sendo {r['fracao_solar_da_recarga_pct']}% de origem solar/bateria.")
    if re.search(r"rede|import|ponta", p):
        return (f"Importamos {r['importado_rede_kwh']} kWh da rede, dos quais "
                f"{r['importado_na_ponta_kwh']} kWh no horário de ponta.")
    if re.search(r"ger|solar|painel|paine|sol\b", p):
        return f"Hoje os painéis geraram {r['geracao_fv_kwh']} kWh e {r['autoconsumo_fv_pct']}% foi usado no local."
    return "Posso responder sobre geração solar, bateria, recarga, custo/economia, rede e CO2. O que você quer saber?"


def modo_assistente(r):
    print("Assistente do sistema (digite 'sair' para encerrar)")
    while True:
        try:
            q = input("Você: ").strip()
        except EOFError:
            break
        if q.lower() in ("sair", "exit", "quit"):
            break
        print("Assistente:", responder(q, r))


def main():
    os.makedirs("resultados", exist_ok=True)
    os.makedirs("docs", exist_ok=True)
    r_imed, s_imed = simular("imediata")
    r_int, s_int = simular("inteligente")

    with open("resultados/resultados.json", "w", encoding="utf-8") as f:
        json.dump({"parametros": CONFIG, "imediata": r_imed, "inteligente": r_int},
                  f, ensure_ascii=False, indent=2)
    salvar_csv(s_imed, "resultados/serie_imediata.csv")
    salvar_csv(s_int, "resultados/serie_inteligente.csv")
    grafico_fluxos(s_imed, "docs/fluxos_recarga_imediata.png", "Recarga imediata (sem gestão)")
    grafico_fluxos(s_int, "docs/fluxos_recarga_inteligente.png", "Recarga inteligente (prioriza sol e bateria)")
    grafico_comparacao(r_imed, r_int, "docs/comparacao_estrategias.png")
    diagrama_arquitetura("docs/arquitetura.png")
    from dashboard import gerar_dashboard
    gerar_dashboard(r_imed, s_imed, r_int, s_int, "dashboard.html")

    print(f"{'Métrica':38}{'Imediata':>12}{'Inteligente':>14}")
    for k in r_imed:
        if k != "estrategia":
            print(f"{k:38}{str(r_imed[k]):>12}{str(r_int[k]):>14}")
    if "--assistente" in sys.argv:
        modo_assistente(r_int)


if __name__ == "__main__":
    main()
