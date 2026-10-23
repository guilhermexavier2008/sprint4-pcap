"""Gera o dashboard web (dashboard.html): um único arquivo, sem dependências externas.

Abre direto no navegador (duplo clique). Mostra os fluxos de energia do dia, KPIs
comparando recarga imediata x inteligente e um assistente virtual para perguntas.
"""
import json

HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Estação de Recarga Solar Inteligente - Dashboard</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--tx:#1f2328;--mut:#6b7280;--bd:#e3e6ea;--pv:#f5b82e;--casa:#2b6cb0;--ev:#2f9e44;--rede:#c92a2a;--soc:#7048e8}
@media (prefers-color-scheme:dark){:root{--bg:#14161a;--card:#1d2026;--tx:#e8eaed;--mut:#9aa1ab;--bd:#2c313a}}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--tx)}
header{padding:18px 20px 6px}
h1{margin:0;font-size:1.25rem}
.sub{color:var(--mut);font-size:.85rem;margin-top:4px}
main{padding:12px 20px 28px;display:grid;gap:14px;max-width:1100px;margin:auto}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px}
.tabs{display:flex;gap:8px}
.tabs button{border:1px solid var(--bd);background:var(--card);color:var(--tx);padding:8px 14px;border-radius:8px;cursor:pointer;font-size:.9rem}
.tabs button.on{background:var(--ev);color:#fff;border-color:var(--ev)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.kpi{border:1px solid var(--bd);border-radius:10px;padding:10px}
.kpi b{display:block;font-size:1.35rem}
.kpi span{color:var(--mut);font-size:.78rem}
.kpi i{font-style:normal;font-size:.78rem;color:var(--ev)}
canvas{width:100%;display:block}
#c1{height:300px}#c2{height:120px;margin-top:6px}
.leg{display:flex;flex-wrap:wrap;gap:14px;font-size:.82rem;color:var(--mut);margin:6px 0}
.leg em{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px}
#hover{font-size:.82rem;color:var(--mut);min-height:1.3em}
table{width:100%;border-collapse:collapse;font-size:.88rem}
th,td{padding:7px 6px;border-bottom:1px solid var(--bd);text-align:right}
th:first-child,td:first-child{text-align:left}
#log{height:190px;overflow:auto;border:1px solid var(--bd);border-radius:8px;padding:8px;font-size:.88rem;background:var(--bg)}
.u{color:var(--casa);margin:4px 0}.a{margin:4px 0 10px}
.row{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}
.row input{flex:1;min-width:180px;padding:9px;border-radius:8px;border:1px solid var(--bd);background:var(--card);color:var(--tx)}
.row button,.chips button{padding:8px 12px;border-radius:8px;border:1px solid var(--bd);background:var(--card);color:var(--tx);cursor:pointer}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.note{font-size:.78rem;color:var(--mut)}
</style>
</head>
<body>
<header>
  <h1>Estação de Recarga Solar Inteligente</h1>
  <div class="sub">Simulação de 1 dia &middot; FV 8 kWp + inversor híbrido GW8K-ET + bateria Lynx Home F Plus+ + carregador GW7K-HCA &middot; dados simulados</div>
</header>
<main>
  <div class="card">
    <div class="tabs">
      <button id="b-int" class="on">Recarga inteligente</button>
      <button id="b-imed">Recarga imediata (sem gestão)</button>
    </div>
  </div>
  <div class="card"><div class="kpis" id="kpis"></div></div>
  <div class="card">
    <div class="leg">
      <span><em style="background:var(--pv)"></em>Geração FV</span>
      <span><em style="background:var(--casa)"></em>Consumo da casa</span>
      <span><em style="background:var(--ev)"></em>Recarga do VE</span>
      <span><em style="background:var(--rede)"></em>Importação da rede</span>
      <span><em style="background:var(--soc)"></em>Bateria (SoC %)</span>
    </div>
    <canvas id="c1"></canvas>
    <canvas id="c2"></canvas>
    <div id="hover">Passe o mouse sobre o gráfico para ver os valores de cada horário.</div>
  </div>
  <div class="card">
    <b>Comparação das estratégias</b>
    <table id="tab"></table>
    <p class="note">Tarifas, fator de emissão e consumo do veículo são valores ilustrativos definidos em CONFIG (simulador_goodwe.py).</p>
  </div>
  <div class="card">
    <b>Assistente virtual</b>
    <div id="log"></div>
    <div class="chips" id="chips"></div>
    <div class="row"><input id="q" placeholder="Pergunte: quanto gerei hoje? quanto economizei?"><button id="send">Perguntar</button></div>
  </div>
</main>
<script>
const D = __DATA__;
let est = "inteligente";
const $ = id => document.getElementById(id);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const norm = s => s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
const fmt = (v, d = 1) => Number(v).toLocaleString("pt-BR", {minimumFractionDigits: d, maximumFractionDigits: d});

function resposta(q) {
  const r = D[est].res, p = norm(q);
  if (/co2|carbono|ambient|emiss|sustent/.test(p))
    return `A recarga evitou cerca de ${fmt(r.co2_evitado_vs_combustao_kg)} kg de CO2 em comparação com rodar ${Math.round(r.km_rodados_equivalentes)} km com um carro a combustão.`;
  if (/econom|custo|gast|dinheiro|reais|conta|pag/.test(p))
    return `O custo líquido de energia do dia foi R$ ${fmt(r.custo_liquido_rs, 2)} (tarifas ilustrativas).`;
  if (/bateria|soc|armazen/.test(p))
    return "A bateria carrega com o excedente solar e alimenta a casa e o carro à noite, respeitando a reserva mínima de 20%.";
  if (/recarga|carro|carreg|veicul|\bev\b/.test(p))
    return `Foram entregues ${fmt(r.energia_recarga_kwh)} kWh (${r.sessoes_concluidas} sessões concluídas), sendo ${fmt(r.fracao_solar_da_recarga_pct)}% de origem solar/bateria.`;
  if (/rede|import|ponta/.test(p))
    return `Importamos ${fmt(r.importado_rede_kwh)} kWh da rede, dos quais ${fmt(r.importado_na_ponta_kwh)} kWh no horário de ponta.`;
  if (/\bger|solar|painel|paine|\bsol\b/.test(p))
    return `Hoje os painéis geraram ${fmt(r.geracao_fv_kwh)} kWh e ${fmt(r.autoconsumo_fv_pct)}% foi usado no local.`;
  return "Posso responder sobre geração solar, bateria, recarga, custo/economia, rede e CO2. O que você quer saber?";
}

function perguntar(q) {
  q = q.trim(); if (!q) return;
  const log = $("log");
  log.insertAdjacentHTML("beforeend", `<div class="u"></div><div class="a"></div>`);
  const els = log.querySelectorAll(".u"), ans = log.querySelectorAll(".a");
  els[els.length - 1].textContent = "Você: " + q;
  ans[ans.length - 1].textContent = "Assistente: " + resposta(q);
  log.scrollTop = log.scrollHeight;
}

function kpis() {
  const r = D[est].res, o = D[est === "inteligente" ? "imediata" : "inteligente"].res;
  const itens = [
    ["Geração solar", fmt(r.geracao_fv_kwh) + " kWh", ""],
    ["Autossuficiência", fmt(r.autossuficiencia_pct) + " %", ""],
    ["Importado da rede", fmt(r.importado_rede_kwh) + " kWh", ""],
    ["Importado na ponta", fmt(r.importado_na_ponta_kwh) + " kWh", ""],
    ["Custo líquido do dia", "R$ " + fmt(r.custo_liquido_rs, 2), ""],
    ["CO2 evitado (vs combustão)", fmt(r.co2_evitado_vs_combustao_kg) + " kg", ""],
    ["Sessões concluídas", r.sessoes_concluidas, ""],
  ];
  $("kpis").innerHTML = itens.map(i => `<div class="kpi"><span>${i[0]}</span><b>${i[1]}</b></div>`).join("");
}

function tabela() {
  const a = D.imediata.res, b = D.inteligente.res;
  const linhas = [
    ["Importado da rede (kWh)", "importado_rede_kwh", 1], ["Importado na ponta (kWh)", "importado_na_ponta_kwh", 1],
    ["Autoconsumo FV (%)", "autoconsumo_fv_pct", 1], ["Autossuficiência (%)", "autossuficiencia_pct", 1],
    ["Parcela solar da recarga (%)", "fracao_solar_da_recarga_pct", 1], ["Custo líquido (R$)", "custo_liquido_rs", 2],
  ];
  let h = "<tr><th>Métrica</th><th>Imediata</th><th>Inteligente</th><th>Variação</th></tr>";
  for (const [nome, k, d] of linhas) {
    const pp = k.endsWith("_pct");
    const v = pp ? b[k] - a[k] : (a[k] ? (b[k] - a[k]) / a[k] * 100 : 0);
    h += `<tr><td>${nome}</td><td>${fmt(a[k], d)}</td><td>${fmt(b[k], d)}</td><td>${v > 0 ? "+" : ""}${fmt(v)}${pp ? " p.p." : " %"}</td></tr>`;
  }
  $("tab").innerHTML = h;
}

function prep(c) {
  const dpr = window.devicePixelRatio || 1, W = c.clientWidth, H = c.clientHeight;
  c.width = W * dpr; c.height = H * dpr;
  const x = c.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, W, H);
  return {x, W, H};
}

function plot(c, series, ymax, unit, hoverX) {
  const {x, W, H} = prep(c), m = {l: 40, r: 8, t: 8, b: 22};
  const pw = W - m.l - m.r, ph = H - m.t - m.b;
  const X = h => m.l + h / 24 * pw, Y = v => m.t + ph - v / ymax * ph;
  x.font = "11px system-ui"; x.fillStyle = css("--mut"); x.strokeStyle = css("--bd"); x.lineWidth = 1;
  const passo = ymax > 20 ? 25 : 2;
  for (let v = 0; v <= ymax; v += passo) {
    x.beginPath(); x.moveTo(m.l, Y(v)); x.lineTo(W - m.r, Y(v)); x.stroke();
    x.textAlign = "right"; x.fillText(v, m.l - 5, Y(v) + 4);
  }
  x.textAlign = "center";
  for (let h = 0; h <= 24; h += 4) x.fillText(h + "h", X(h), H - 6);
  x.save(); x.translate(10, m.t + ph / 2); x.rotate(-Math.PI / 2); x.fillText(unit, 0, 0); x.restore();
  for (const s of series) {
    const pts = s.d.map((v, i) => [X(i * 0.25), Y(v)]);
    x.beginPath(); pts.forEach((p, i) => i ? x.lineTo(p[0], p[1]) : x.moveTo(p[0], p[1]));
    if (s.fill) {
      x.lineTo(X(23.75), Y(0)); x.lineTo(X(0), Y(0)); x.closePath();
      x.globalAlpha = .35; x.fillStyle = s.cor; x.fill(); x.globalAlpha = 1;
      x.beginPath(); pts.forEach((p, i) => i ? x.lineTo(p[0], p[1]) : x.moveTo(p[0], p[1]));
    }
    x.strokeStyle = s.cor; x.lineWidth = s.w || 2; x.setLineDash(s.dash || []); x.stroke(); x.setLineDash([]);
  }
  if (hoverX != null) {
    x.strokeStyle = css("--mut"); x.lineWidth = 1; x.beginPath();
    x.moveTo(X(hoverX), m.t); x.lineTo(X(hoverX), m.t + ph); x.stroke();
  }
}

let idx = null;
function desenhar() {
  const s = D[est].serie, h = idx == null ? null : s[idx].hora;
  plot($("c1"), [
    {d: s.map(a => a.pv_kw), cor: css("--pv"), fill: true},
    {d: s.map(a => a.casa_kw), cor: css("--casa")},
    {d: s.map(a => a.ev_kw), cor: css("--ev"), w: 2.4},
    {d: s.map(a => a.rede_kw), cor: css("--rede"), dash: [5, 4]},
  ], 9, "kW", h);
  plot($("c2"), [{d: s.map(a => a.soc_pct), cor: css("--soc")}], 100, "SoC %", h);
}

function atualizar() { kpis(); desenhar(); }
function trocar(e) {
  est = e;
  $("b-int").classList.toggle("on", e === "inteligente");
  $("b-imed").classList.toggle("on", e === "imediata");
  atualizar();
}

for (const id of ["c1", "c2"]) {
  $(id).addEventListener("mousemove", ev => {
    const r = ev.target.getBoundingClientRect(), W = r.width;
    const h = Math.min(23.75, Math.max(0, (ev.clientX - r.left - 40) / (W - 48) * 24));
    idx = Math.round(h / 0.25);
    const a = D[est].serie[idx], hh = Math.floor(a.hora), mm = Math.round((a.hora - hh) * 60);
    $("hover").textContent = `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}  |  FV ${fmt(a.pv_kw, 2)} kW  |  Casa ${fmt(a.casa_kw, 2)} kW  |  Recarga ${fmt(a.ev_kw, 2)} kW  |  Rede ${fmt(a.rede_kw, 2)} kW  |  Bateria ${fmt(a.soc_pct)} %`;
    desenhar();
  });
  $(id).addEventListener("mouseleave", () => { idx = null; desenhar(); });
}
$("b-int").onclick = () => trocar("inteligente");
$("b-imed").onclick = () => trocar("imediata");
$("send").onclick = () => { perguntar($("q").value); $("q").value = ""; };
$("q").addEventListener("keydown", e => { if (e.key === "Enter") $("send").click(); });
for (const t of ["Quanto gerei hoje?", "Quanto economizei?", "Quanto CO2 evitei?", "Como está a bateria?", "Como foi a recarga?"]) {
  const b = document.createElement("button"); b.textContent = t; b.onclick = () => perguntar(t); $("chips").appendChild(b);
}
window.addEventListener("resize", desenhar);
tabela(); atualizar();
perguntar("Quanto gerei hoje?");
</script>
</body>
</html>
"""


def gerar_dashboard(r_imed, s_imed, r_int, s_int, caminho):
    dados = {
        "imediata": {"res": r_imed, "serie": s_imed},
        "inteligente": {"res": r_int, "serie": s_int},
    }
    html = HTML.replace("__DATA__", json.dumps(dados, ensure_ascii=False))
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(html)
