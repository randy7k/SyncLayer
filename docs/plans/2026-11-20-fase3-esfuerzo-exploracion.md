# Fase 3: esfuerzo configurable. Resultado de la exploración

> Estado: **exploración cerrada, pendiente de decisiones del propietario**. Sin código. Salida de la
> etapa 1 del backlog ([`2026-11-19-backlog-configuracion-y-reportes.md`](2026-11-19-backlog-configuracion-y-reportes.md),
> Fase 3). Fuentes: consulta de `scout` a la documentación oficial (leída el 2026-11-20; las páginas
> de Claude Code no traen fecha propia, sólo notas «requiere vX») y mapa de `oracle` sobre el
> instalador. Lo marcado «hipótesis» o «inferido» no está verificado.

## 1. Qué se pidió y qué decidió el propietario

Subir o bajar el consumo según los tokens que queden; ejemplo: que `atlas` pase de
`claude-fable-5-2` a `opus`. Decisiones ya tomadas (2026-11-20):

1. La Fase 3 se explora sola; el archivo de configuración se diseña para que la Fase 4 (nombres)
   lo reutilice, sin explorarla ahora.
2. **Seguridad y revisión fijas:** los niveles bajos sólo tocan `atlas`, `forge`, `scribe`,
   `sentinel`, `oracle` y `scout`. `auditor`, `shield` y `debugger` no bajan nunca de modelo.
3. **Mecanismo:** el instalador escribe en el destino el `model:` (y el `effort:` si aplica) según
   el nivel elegido; cambiar de nivel = volver a instalar.

## 2. Hallazgo principal: Claude Code ya trae cinco niveles de esfuerzo

El campo `effort:` del frontmatter de un subagente existe y acepta cinco niveles oficiales:
`low`, `medium`, `high`, `xhigh`, `max` (los disponibles dependen del modelo). Los cinco están
disponibles en Fable, Opus 5.5, Sonnet 5.5 y Haiku 5.5. Es probable que los «5 niveles» del
propietario coincidan con ellos, pero **modelo y esfuerzo son dos palancas distintas**:

| | Qué cambia | Precio por token | Qué dice la documentación |
|---|---|---|---|
| **Modelo** | capacidad y precio por token | cambia | Haiku para tareas simples, Sonnet para la mayoría, Opus para razonamiento más complejo |
| **Esfuerzo** | cuántos tokens gasta el mismo modelo (texto, herramientas y razonamiento) | no cambia | bajar el nivel da «ahorro significativo de tokens con alguna reducción de capacidad»; con `low`, Haiku 5.5 tiene más probabilidad de saltarse una búsqueda, parar antes o saltarse una comprobación |

La documentación no da cifras de ahorro ni de pérdida de calidad por nivel; pide medirlo con
pruebas propias. Por eso **nada de lo que escriba el proyecto puede prometer un ahorro**. Precios
por millón de tokens (entrada/salida), de la página oficial de precios: Fable 5.2 8/40, Opus 5.5
4/20, Sonnet 5.5 2/10, Haiku 5.5 0,10/0,50 (hasta 100 000 tokens de prompt). Comparar precio por
token entre generaciones no es comparar costo por tarea: los tokenizadores nuevos producen cerca de
un 30 % más de tokens para el mismo texto.

## 3. Hechos verificados que condicionan el diseño

| Hecho | Fuente |
|---|---|
| `model:` acepta alias (`sonnet`, `opus`, `haiku`, `fable`), id completo o `inherit`. Sin `model:`, el subagente usa el de la conversación que lo lanza | sub-agents |
| Los alias apuntan a «la versión recomendada» y **cambian con el tiempo** (hoy `opus`=Opus 5.5, `sonnet`=Sonnet 5.5, `haiku`=Haiku 5.5, `fable`=Fable 5.2). Explica el `fable` viejo que se vio en 2.1.310 (cambió en 2.1.257 y 2.1.321). Para fijar versión: id completo | model-config |
| Un alias o id desconocido en `model:` **no está documentado** (ni error ni aviso ni fallback) | sin confirmar |
| Precedencia de modelo: parámetro `model` de la llamada a Agent > `model:` del frontmatter > `CLAUDE_CODE_SUBAGENT_MODEL` > modelo de la sesión | sub-agents |
| `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` ignora el `model:` del frontmatter | sub-agents, env-vars |
| `effort:` del frontmatter sobrescribe el de la sesión, **pero no** a `CLAUDE_CODE_EFFORT_LEVEL`; un tope `maxEffortLevel` gestionado también lo limita | sub-agents, model-config |
| Un nivel no soportado por el modelo baja al más alto soportado igual o inferior | model-config |
| Un `.claude/agents/X.md` de proyecto gana al `~/.claude/agents/X.md` del usuario (incluido su `model:` y su `effort:`) | sub-agents (ámbitos) |
| Claude Code vigila `~/.claude/agents/` y detecta un cambio «en unos segundos»: la siguiente delegación usa la definición nueva **sin reiniciar**. Contradice la nota actual de `CLAUDE.md` («las sesiones ya abiertas no ven agentes modificados») | sub-agents |
| Los valores por defecto de esfuerzo difieren entre dos páginas oficiales para Sonnet 5.5 (`medium` o `high`); conviene escribir el `effort:` explícito | model-config vs API |

**No confirmado:** qué pasa con un `model:` desconocido; si hay cambios de alias entre 2.1.322 y
2.1.328; si `effort: max` tiene restricciones en el frontmatter; la recarga en caliente en la práctica
(una prueba local lo zanja).

## 4. Cómo está hoy el repositorio (mapa de `oracle`)

- El modelo de cada agente está escrito a mano en la línea 5 de los nueve `agents/*.md` y
  **repetido** en `rules/agentes.md`, `docs/agentes.md`, `README.md`, `assets/brand/src/agents_data.py`
  (y los SVG de catálogo) y en las pruebas. No hay ningún `effort:` en el repositorio.
- El instalador copia bytes fijos. El manifiesto (`install-manifest.json`) guarda el hash canónico
  del **origen** y el estado (`<Target>/synclayer-manifest.json`) es una copia del manifiesto.
- **Problema central:** si el instalador reescribe el `model:` o añade `effort:` en el destino, el
  hash del destino deja de coincidir con el del manifiesto. En la siguiente instalación casi todo
  saldría `MODIFICADO` (exit 3) y el instalador **no puede distinguir** un cambio de nivel de una
  edición manual del usuario, porque el estado sólo guarda el hash del origen.
- Con el nivel por defecto (nivel 5 = bytes del repositorio, sin tocar nada) no cambia nada y las
  instalaciones existentes siguen siendo `ACTUALIZAR`.
- `install.ps1` no está en el manifiesto: una tabla de niveles dentro del script no tiene hash ni
  validación de origen; una tabla en un archivo aparte tendría que ser un archivo gestionado
  (número trece, que rompe `TWELVE` y los conteos de las pruebas).
- Pruebas que se rompen o hay que adaptar: casos 3, 7 y 18 de `tests/test_install.py` (estado igual
  byte a byte al manifiesto), `test_manifest.py` (`TWELVE`, `RealRepo`), `test_brand_agents.py` y
  `agents_data.py` si cambia el nivel por defecto, y las pruebas que inyectan código por texto
  exacto de las líneas de `install.ps1`.
- Restricciones vivas: `install.ps1` sólo ASCII y sin BOM, PowerShell 5.1 (sin `-AsHashtable`),
  los `# Paso N:` son contrato con las pruebas, las pruebas de powershell.exe 5.1 sí corren aquí y
  las de pwsh se saltan.

## 5. Opciones y recomendación

### 5.1 Qué controlan los niveles

| Opción | Descripción | Veredicto |
|---|---|---|
| **A. Modelo y esfuerzo** | Cada nivel asigna `model:` y `effort:` a los seis agentes modificables | **Recomendada**: es lo que pide el ejemplo (atlas fable a opus) y a la vez usa el control oficial |
| B. Sólo modelo | Cada nivel cambia `model:` | Más simple; ignora el control oficial de esfuerzo |
| C. Sólo esfuerzo | Cada nivel cambia `effort:` y el modelo no se toca | No cubre el ejemplo del propietario |

### 5.2 Dónde vive la configuración del usuario

| Opción | Implicación |
|---|---|
| **B. `<Target>/synclayer-config.json`**, junto al estado | **Recomendada.** Coherente con `-Target` y con las pruebas (todo bajo la carpeta temporal); `-DryRun` lo lee sin escribir; un archivo inválido sale con exit 1 antes de escribir |
| A. `~/.claude/synclayer-config.json` fijo | Con `-Target` temporal el instalador leería el HOME real: dos fuentes de verdad |
| C. Parámetro `-Effort` | Sin persistencia: reinstalar sin el parámetro vuelve en silencio al nivel 5 |

Contenido mínimo: un único campo `level` (1 a 5), validado contra lista cerrada. Sin sobreescrituras por
agente en esta fase (la Fase 4 puede añadir su tabla de alias al mismo archivo).

### 5.3 Cómo se escribe sin romper el manifiesto (recomendación)

1. El **repositorio sigue siendo el nivel 5**: `agents/*.md` no cambia, el manifiesto y sus pruebas
   siguen valiendo, y quien no configura nada no nota ningún cambio.
2. Para los niveles 1 a 4 el instalador toma los bytes canónicos del origen y **sólo reemplaza la
   línea `model:` e inserta la línea `effort:`** dentro del frontmatter de los seis agentes
   modificables, con valores de una lista cerrada. No toca `auditor`, `shield` ni `debugger`, ni el
   cuerpo, ni el hook.
3. El **estado pasa a guardar, además del hash del origen, el hash de lo escrito y el nivel**, por
   archivo. La clasificación compara el destino con lo escrito por la última instalación:
   - igual a lo escrito: cambio de nivel o actualización normal, `ACTUALIZAR`;
   - distinto de lo escrito: edición manual del usuario, `MODIFICADO` (exit 3 sin `-Force`).
4. La tabla de niveles vive en `install.ps1` con lista cerrada de valores y una prueba que la
   compara con la tabla documentada. (Alternativa: un archivo gestionado número trece; cuesta tocar
   `TWELVE`, `ALLOWED`, `$AllowedPattern` y los conteos. Se descarta para esta fase.)
5. El instalador **avisa** (lectura, sin cambiar nada) si detecta `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`
   o `CLAUDE_CODE_EFFORT_LEVEL` en el entorno, porque anulan el frontmatter; el README documenta
   además que un `.claude/agents/<nombre>.md` de proyecto, un `maxEffortLevel` o un `availableModels`
   gestionado también lo anulan.
6. Para los agentes que bajan de nivel se usa un **alias** (`opus`, `sonnet`, `haiku`), no un id
   completo, salvo que el propietario prefiera fijar versión: `atlas` en el nivel 5 sigue con
   `claude-fable-5-2` por el problema del alias `fable`.

### 5.4 Tabla nivel × agente (hipótesis, para que `atlas` la afine y el propietario la apruebe)

Fijos en todos los niveles (modelo actual, sin `effort:`): `auditor`, `shield`, `debugger`.

| Agente | Nivel 5 (actual) | Nivel 4 | Nivel 3 | Nivel 2 | Nivel 1 |
|---|---|---|---|---|---|
| `atlas` | `claude-fable-5-2` | `opus` | `opus`, `effort: medium` | `sonnet` | `sonnet`, `effort: low` |
| `forge` | `sonnet` | `sonnet` | `sonnet` | `sonnet`, `effort: medium` | `sonnet`, `effort: low` |
| `sentinel` | `sonnet` | `sonnet` | `sonnet` | `sonnet`, `effort: medium` | `sonnet`, `effort: low` |
| `scribe` | `sonnet` | `sonnet` | `sonnet`, `effort: medium` | `sonnet`, `effort: low` | `haiku`, `effort: low` |
| `scout` | `sonnet` | `sonnet` | `sonnet`, `effort: medium` | `sonnet`, `effort: low` | `haiku`, `effort: low` |
| `oracle` | `haiku` | `haiku` | `haiku` | `haiku`, `effort: low` | `haiku`, `effort: low` |

Es una propuesta de orden, no una medición: la documentación avisa que `low` en Haiku tiende a
saltarse comprobaciones, y que el esfuerzo se debe barrer con evaluaciones propias. El README dirá
sin rodeos que **bajar el nivel cambia la calidad esperada** y que no se ha medido el ahorro. Una
extensión posible, fuera de esta fase: que el reporte de uso (Fase 2) compare tokens por nivel con
datos reales del propietario, que es el único modo honesto de afirmar algo.

## 6. Riesgos y preguntas abiertas

| Riesgo | Mitigación |
|---|---|
| El estado con hash de lo escrito cambia el formato del estado y rompe los casos 3, 7 y 18 | Estado versionado (`schema`): el esquema viejo se lee igual y se migra al reinstalar; pruebas nuevas por nivel |
| Un nivel bajo debilita revisiones | `auditor`, `shield` y `debugger` fijos por diseño (decisión del propietario); aviso en README |
| Variables de entorno o un agente de proyecto anulan el nivel sin avisar | Aviso del instalador y documentación; no se puede arreglar desde el repositorio |
| Un `model:` desconocido no tiene comportamiento documentado | El instalador sólo escribe valores de una lista cerrada; prueba local antes de implementar |
| La edición manual de `model:` (documentada en `docs/agentes.md`) choca con el instalador | Sale como `MODIFICADO` (exit 3), igual que hoy |
| Doble fuente de verdad del modelo (tablas del README, `rules/agentes.md`, `agents_data.py`) | Las tablas dicen que el valor es el del nivel 5; el nivel lo decide el archivo de configuración |
| La nota de `CLAUDE.md` sobre reiniciar sesiones podría ser innecesaria | Comprobarlo con una prueba local antes de cambiar el texto |

Preguntas abiertas para el propietario: ver el mensaje de cierre de la exploración (qué controlan
los niveles, dónde vive la configuración y si se afina la tabla antes del plan).
