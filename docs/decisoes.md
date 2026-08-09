<!--
docs/decisoes.md — Registro das decisões de projeto (ADR simplificado).
Deve conter, em texto uma linha por item.
------------------------------------------------------------------------------
-->

### 1. Por que Streamlit
**Contexto:** Precisamos de um framework Python ágil para construir a interface web sem gastar muito tempo com front-end.
**Decisão:** Escolhemos o Streamlit por sua simplicidade, integração com dados e facilidade de deploy gratuito.
**Consequência:** Ganhamos velocidade no desenvolvimento e facilidade no deploy, mas abrimos mão de controle fino sobre o design da UI.

### 2. Por que perfil automático como v1
**Contexto:** No MVP, é crucial entregar valor rápido ajudando o usuário a entender seus dados sem exigir configurações prévias.
**Decisão:** Focar na criação de um perfilamento automático que funcione "out-of-the-box" para qualquer conjunto de dados inserido.
**Consequência:** A ferramenta se torna altamente flexível e útil desde o primeiro uso, embora possa ter gargalos de performance em datasets massivos.

### 3. Por que config híbrida (auto-detecta + YAML + tela)
**Contexto:** Diferentes perfis de usuários precisam interagir com a ferramenta: iniciantes (auto), engenheiros (YAML) e analistas (tela).
**Decisão:** Adotar um modelo de configuração que autodetecta padrões, aceita sobrescrita via código (YAML) e ajustes manuais na interface.
**Consequência:** Excelente experiência de usuário atendendo a múltiplos casos de uso, porém com maior complexidade técnica para manter os três estados sincronizados.

### 4. Por que HTML antes de PDF
**Contexto:** O resultado das análises precisa ser exportado, compartilhado facilmente e rico em detalhes.
**Decisão:** Priorizar relatórios exportáveis em HTML (interativo) antes de PDFs (estáticos).
**Consequência:** Mantém a interatividade dos gráficos e reduz dependências pesadas de geração de PDF, entregando um relatório mais rico em um primeiro momento.

### 5. Por que o conector SQL roda a query do usuário
**Contexto:** Ao conectar com bancos relacionais, extrair tabelas inteiras pode ser ineficiente e pesado.
**Decisão:** Permitir e exigir que o conector SQL execute consultas customizadas escritas pelo próprio usuário.
**Consequência:** Dá total liberdade para o usuário filtrar o que precisa no próprio banco, economizando rede e memória, mas exige conhecimento de SQL.

### 6. Por que o Top 10 ordena por Sharpe geométrico, e não por retorno
**Contexto:** O terminal cruza o preço das ações com a Selic/CDI e precisa ordenar o resultado; "quem subiu mais" premia sempre o ativo mais alavancado, e uma soma ponderada de retorno, volatilidade, IFR e média móvel seria quatro pesos sem fonte produzindo uma nota com autoridade que nenhuma parte dela conquistou.
**Decisão:** Ordenar pelo excesso GEOMÉTRICO anualizado sobre o benchmark dividido pela volatilidade anualizada (Sharpe); a média móvel de 50 dias e o IFR de 14 dias são calculados, exibidos e explicados, mas nunca entram na nota — falam do hoje, e a nota é do período.
**Consequência:** A ordem da tabela é a mesma grandeza que a tabela mostra (prêmio negativo nunca aparece acima de prêmio maior, o que a média aritmética de excessos diários fazia), ao custo de o ranking ignorar valuation e fundamentos — ele responde "pagou bem pelo risco que correu", não "está barata".

### 7. Por que o benchmark é composto e pareado por data
**Contexto:** A Selic chega do SGS 11 em % ao DIA, e as séries de preço de B3 e NYSE têm feriados diferentes entre si e em relação ao calendário do BCB.
**Decisão:** Compor a taxa (`∏(1+i)−1`, nunca somar) e parear preço e taxa por `join` interno na data, de modo que cada ativo é julgado apenas nos dias que as duas séries têm em comum.
**Consequência:** O CDI acumulado exibido para um papel americano difere do exibido para um brasileiro — e isso é correto, não um bug: são períodos com pregões diferentes. Somar daria ~1 ponto percentual a menos em 252 dias, e parear por posição mediria a AAPL contra o juro de outro dia.

### 8. Por que a Home cabe em uma tela, e o que foi cortado para caber
**Contexto:** A referência visual é um painel lido de uma vez: marca e filtros à esquerda, uma faixa de rótulos, uma faixa de números e uma faixa de gráficos — tudo acima da dobra. O Streamlit gasta cerca de um terço de uma tela de 768px só em espaçamento padrão (6rem acima do título), e `st.title` sozinho custa o suficiente para empurrar a faixa de gráficos para fora.
**Decisão:** Navegação por rádio na barra lateral (uma página por vez, não abas), CSS em `app/theme.py` removendo o espaçamento do Streamlit, `st.title` substituído pelo bloco de marca na lateral mais o cabeçalho "Page: X", e exatamente três gráficos a 430px — linha (quando), barra horizontal (quem) e rosca (de quê).
**Consequência:** A Home responde na primeira renderização, sem upload, sem período e sem botão. O preço é que só cabem três perguntas ali: "por que" mora nas páginas Explore e Terminal, a um clique. Abas foram descartadas porque renderizam todos os painéis a cada re-execução — o ranking recalcularia enquanto alguém lê o perfil.

### 9. Por que 827 ações, e por que o banco saiu do Git
**Contexto:** Doze ativos escritos à mão bastavam para provar os conectores, mas não para testar um ranking: com doze linhas, "Top 10" é quase a lista inteira, e nenhum filtro de setor ou país tem o que filtrar.
**Decisão:** `--universo` no `download_data.py`, com o padrão continuando nos 12 curados e `tudo` trazendo ~324 ações ON/PN da B3 (lista da brapi, setor via busca do Yahoo) mais as 503 do S&P 500 (lista e setor GICS do mesmo CSV). Ficam de fora as terminações `11` (fundo imobiliário e ETF) e `32`–`39` (BDR). O banco e os CSVs saíram do versionamento.
**Consequência:** O clone deixou de vir com dado pronto — é preciso rodar um comando antes de abrir o app, e o app diz isso quando o arquivo não existe. Em troca, o histórico do Git para de carregar um binário de 134 MB que um comando reconstrói, e o ranking passa a ter universo suficiente para o filtro de setor significar alguma coisa. As exclusões são o ponto delicado: units legítimas (BPAC11, TAEE11) saem junto com os FIIs, porque não há como separá-las pelo código — e incluir 550 fundos para salvar 15 units é o lado errado da troca.
