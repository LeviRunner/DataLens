"""
config_loader.py — Lê o arquivo de configuração (YAML) do usuário.
Ideia (sem código): abrir o config.yaml, aplicar valores padrão quando algo faltar,
validar o mínimo necessário (tipo de fonte definido, query presente se for SQL) e
entregar essas opções para o resto do sistema. É o que torna o DataLens configurável.
Construído na Fase 3 (semana 12).
"""
