# Roteiro do vídeo técnico (até 5 minutos)

Dica: gravem a tela com o terminal e os gráficos abertos. Todos os integrantes podem se revezar nos blocos.

| Tempo | Quem | O que mostrar | O que falar |
|-------|------|---------------|-------------|
| 0:00 – 0:30 | Integrante 1 | Slide/README com título e equipe | Apresentar o grupo e o desafio: integrar geração solar, armazenamento e uso de energia com monitoramento inteligente, na linha Goodwe. |
| 0:30 – 1:30 | Integrante 2 | `docs/arquitetura.png` | Explicar cada bloco: painéis, inversor híbrido GW8K-ET, bateria Lynx Home F Plus+, carregador GW7K-HCA, medidor, backend Python e dashboard. Justificar cada escolha: o inversor híbrido gerencia tudo, a bateria guarda o sol para a noite, o carregador entrega a energia ao carro. Avisar que o protótipo é simulado com parâmetros de referência. |
| 1:30 – 3:30 | Integrante 3 | Terminal: `python simulador_goodwe.py`, depois o `dashboard.html` no navegador | Mostrar a tabela imediata × inteligente aparecendo. Abrir o `dashboard.html`, alternar entre as abas "inteligente" e "imediata" e passar o mouse no gráfico: carros A e B carregam com sol, bateria sustenta a noite, rede só entra no prazo. Perguntar ao assistente do dashboard: "quanto gerei hoje?", "quanto economizei?", "quanto CO2 evitei?". |
| 3:30 – 4:30 | Integrante 1 ou 2 | Tabela de comparação do dashboard (ou `docs/comparacao_estrategias.png`) | Resultados: −60,9 % de importação na ponta, −68,3 % de custo, +3,2 p.p. de autossuficiência, 3 de 3 sessões concluídas. Explicar a lógica do algoritmo (prazo, sol, bateria, rede). |
| 4:30 – 5:00 | Todos | README no GitHub | Impacto: ~33,8 kg de CO2 evitados no dia frente a um carro a combustão; limitações (dados simulados) e próximos passos (telemetria real, previsão do tempo, interface web). |

Checklist antes de gravar:
- [ ] Rodar `python simulador_goodwe.py` e `python testes.py` uma vez para garantir que tudo funciona
- [ ] Deixar os gráficos já abertos em abas
- [ ] Vídeo com no máximo 5 minutos
- [ ] Publicar no YouTube como **não listado**
