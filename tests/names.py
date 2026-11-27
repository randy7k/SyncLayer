"""Nombres de los agentes de SyncLayer: la unica fuente para las pruebas (Fase 6, T2). No es un test_*.py.

Referencia escrita a mano e independiente de install.ps1: las pruebas comparan contra estas constantes las
listas del script ($AliasRoles, $LevelAgents, ...), el manifiesto, agents/ y la documentacion. Sin dependencias.
Hoy son los nombres vivos de agents/ (T2 no cambia comportamiento); el cambio de valores llega en T7.
"""

PLANNER, ANALYST, RESEARCHER, DEVELOPER, QA = "atlas", "oracle", "scout", "forge", "sentinel"
REVIEWER, SECURITY, DEBUGGER, WRITER = "auditor", "shield", "debugger", "scribe"
ROLES = sorted([PLANNER, ANALYST, RESEARCHER, DEVELOPER, QA, REVIEWER, SECURITY, DEBUGGER, WRITER])
LEVEL_ROLES = [PLANNER, DEVELOPER, QA, WRITER, RESEARCHER, ANALYST]
FIXED = [REVIEWER, SECURITY, DEBUGGER]
GUARDED = {QA: "tests-only", REVIEWER: "readonly --allow-temp", SECURITY: "readonly --allow-temp",
           DEBUGGER: "readonly --allow-temp"}
LEGACY = {}   # nombre anterior -> nombre actual; lo llena el cambio (T7)
