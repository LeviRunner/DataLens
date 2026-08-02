"""
base.py — O CONTRATO comum de todos os conectores.
Ideia (sem código): definir a "interface" que toda fonte deve cumprir — essencialmente
um método `carregar()` que devolve os dados num formato único (DataFrame). Assim o resto
do sistema não precisa saber se veio de CSV, Excel, SQL ou API (ports & adapters, versão simples).
Construído na Fase 1 (semana 4).
"""
