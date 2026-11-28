"""Nombres de los agentes de SyncLayer: la unica fuente para las pruebas (Fase 6, T2). No es un test_*.py.

Referencia escrita a mano e independiente de install.ps1: las pruebas comparan contra estas constantes las
listas del script ($AliasRoles, $LevelAgents, ...), el manifiesto, agents/ y la documentacion. Sin dependencias.
Son los nombres vivos de agents/ (desde T7 de la Fase 6, los nuevos); LEGACY guarda los anteriores.
"""

PLANNER, ANALYST, RESEARCHER, DEVELOPER, QA = "atlas", "heimdall", "hermes", "sindri", "anubis"
REVIEWER, SECURITY, DEBUGGER, WRITER = "salomon", "hector", "sherlock", "shakespeare"
ROLES = sorted([PLANNER, ANALYST, RESEARCHER, DEVELOPER, QA, REVIEWER, SECURITY, DEBUGGER, WRITER])
LEVEL_ROLES = [PLANNER, DEVELOPER, QA, WRITER, RESEARCHER, ANALYST]
FIXED = [REVIEWER, SECURITY, DEBUGGER]
GUARDED = {QA: "tests-only", REVIEWER: "readonly --allow-temp", SECURITY: "readonly --allow-temp",
           DEBUGGER: "readonly --allow-temp"}
# nombre anterior -> nombre actual (copia escrita a mano de $LegacyRoles; la prueba la compara con install.ps1)
LEGACY = {"oracle": ANALYST, "scout": RESEARCHER, "forge": DEVELOPER, "sentinel": QA, "auditor": REVIEWER,
          "shield": SECURITY, "debugger": DEBUGGER, "scribe": WRITER}
