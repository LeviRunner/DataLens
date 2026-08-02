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
