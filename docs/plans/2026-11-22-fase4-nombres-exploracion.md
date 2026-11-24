# Fase 4: nombres de agentes configurables. Resultado de la exploración

> Estado: **exploración cerrada, pendiente de decisiones del propietario**. Sin código. Salida de la
> etapa 1 del backlog ([`2026-11-19-backlog-configuracion-y-reportes.md`](2026-11-19-backlog-configuracion-y-reportes.md),
> Fase 4). Fuentes: mapa de `oracle` sobre el repositorio y consulta de `scout` a la documentación
> oficial de Claude Code (leída el 2026-11-22; las páginas no traen fecha propia). Lo marcado
> «inferido» o «no documentado» no está verificado.

## 1. Qué se pidió y qué decidió el propietario

Que el nombre de un agente no sea fijo (por ejemplo, «el amigo QA»). Decisiones ya tomadas (2026-11-22):

1. **Alcance:** los nueve agentes, cada uno opcional. `synclayer-config.json` acepta una tabla de alias
   opcional (rol a nombre); el agente que no figura conserva su nombre. El rol sigue siendo el id
   estable interno.
2. **Textos:** el instalador reemplaza el nombre del rol por el alias en lo que escribe en el destino
   (archivo, `name:`, descripciones y los textos gestionados). El repositorio conserva los nombres
   originales.
3. **Archivo viejo:** si ya había un agente instalado con el nombre anterior, el instalador lo informa
   como huérfano y no lo toca (nunca borra).

## 2. Hechos verificados que condicionan el diseño

| Hecho | Fuente |
|---|---|
| La identidad de un subagente es el campo `name:` del frontmatter, no el nombre del archivo; si difieren, manda `name:`. Máximo 256 caracteres | sub-agents |
| Un `name:` que empieza por `-`, contiene `:` o pasa de 256 caracteres hace que el archivo se omita, con el motivo sólo en el log de `--debug` | sub-agents |
| Mismo `name` en distintos ámbitos: gana el de mayor prioridad (gestionado, `--agents`, proyecto, usuario, plugin). Un agente de usuario llamado como uno integrado (`Explore` está documentado) lo sobrescribe | sub-agents |
| Referencias por nombre que se resuelven por `name:` y se romperían al renombrar: `Agent(nombre)` en `tools:`, `permissions.deny`, matchers de hooks `SubagentStart`/`SubagentStop`, `--agent` y `agent` en `settings.json` | sub-agents, hooks |
| Un matcher de hook con sólo letras, dígitos, `_`, `-`, espacios, `,` o `\|` es una cadena exacta; con cualquier otro carácter pasa a expresión regular sin anclar | hooks |
| Con dos archivos de distinto `name:` cargan como dos agentes distintos (inferido). La delegación automática se guía por la `description`; con dos agentes casi idénticos el desempate no está definido | sub-agents |
| Recarga en caliente: documentada para altas y ediciones; **renombrar un archivo no está documentado** | sub-agents |

**No documentado:** mayúsculas y minúsculas en `name:`, en el matcher y en `subagent_type`; espacios,
unicode y nombres reservados; el esquema de `agent-<id>.meta.json` y si `agentType` es el `name:` vigente
al invocar (inferido: sí, y las transcripciones antiguas conservan el nombre antiguo); cómo se muestran
las colisiones en `/agents` y `/tasks`; si un agente de plugin se invoca sin prefijo.

## 3. Cómo está hoy el repositorio (mapa de `oracle`)

- **El hook no depende del nombre.** `hooks/agent_guard.py` recibe `tool_name`, `tool_input` y `cwd`; el
  modo se enlaza desde el frontmatter, no por nombre ni por ruta del agente.
- **El problema central es estructural:** `install.ps1` usa una sola clave, `$rel = agents/<rol>.md`, para
  el origen, el destino, el estado, el respaldo, la verificación y `$LevelAgents`. Un alias obliga a separar
  **rol** (clave del manifiesto y de la tabla de niveles) de **ruta de destino** (la del alias). Afecta a
  clasificación, respaldo, Pasos 7 y 8, estado y mensajes.
- **Fallo silencioso grave si se hace mal:** si `$rel` pasa a ser la ruta del alias, el renderizado de
  niveles no reconoce al agente (extrae el rol de la ruta) y lo deja sin el `model:` ni el `effort:` del
  nivel, sin error ni línea `Ajuste:`.
- **El archivo viejo nunca sale `HUERFANO` hoy:** el huérfano se decide por pertenencia al manifiesto, y el
  manifiesto tiene la ruta del rol. Hace falta lógica nueva.
- **Textos que se instalan** (`rules/agentes.md`, `docs/agentes.md`, `name:`, `description:` y cuerpo de los
  nueve agentes). Cada nombre aparece en cuatro formas: minúscula en comillas y listas, capitalizada en las
  etiquetas de delegación («Forge (Sonnet): …»), en mayúsculas en tablas, `description:` y cuerpo («You are
  FORGE»), y `@agent-<nombre>`. **«scribe» es subcadena de «escribe», «describe», «reescribe» y
  «sobrescribe»:** el reemplazo exige límite de palabra. Los otros ocho nombres sólo aparecen como agente.
  `HISTORY.md`, `README.md`, `docs/plans/` y `docs/brand/` no se instalan y conservan los nombres.
- **Cruces entre agentes:** `agents/atlas.md` («ORACLE report»), `agents/auditor.md` («SHIELD review»),
  `agents/forge.md` («ATLAS plan») y `agents/debugger.md` («implemented by FORGE») nombran a otros roles.
- **Reporte de uso (Fase 2):** `tools/usage_report.py` clasifica por `agentType` contra una lista cerrada de
  los nueve roles (`SYNCLAYER_AGENTS`); un agente con alias saldría como `(otro agente)` y dejaría de
  atribuirse.
- **Pruebas que fijan 9 agentes y 12 archivos:** `TWELVE` y otras constantes de `test_manifest.py`, la lista
  de nueve de `test_install.py`, las tablas de `test_levels.py`, `SYNCLAYER_AGENTS`, `agents_data.py`. Con
  el repositorio sin cambios y sin alias configurados todas siguen valiendo.
- **Restricciones vivas:** `install.ps1` sólo ASCII, sin BOM y sin el carácter `*`; Windows PowerShell 5.1;
  los `# Paso N:` son contrato con las pruebas; `AllowedPattern` sólo admite `agents/[a-z0-9_-]+.md`
  (**«el amigo QA» no es un alias válido** sin relajarla); el manifiesto da integridad, no autenticidad.

## 4. Riesgos de los alias y cómo restringirlos

| Riesgo | Efecto | Restricción propuesta |
|---|---|---|
| Alias con `:`, `-` inicial o de más de 256 caracteres | El archivo se omite en silencio (sólo `--debug`) | Lista cerrada de caracteres, longitud acotada, sin `-` inicial |
| Alias con `.`, `+` u otros caracteres de regex | Cambia el significado de un matcher de hook de quien lo use | Sólo `[a-z0-9_-]` |
| Mayúsculas, espacios o unicode | Sensibilidad a mayúsculas no documentada; ancho de `AllowedPattern` | Sólo minúsculas |
| Alias igual a un agente integrado (`Explore`, `Plan`, `general-purpose`, `claude`, `statusline-setup`, `claude-code-guide`, `web-fetch`) | Sobrescribe al integrado | Lista cerrada de nombres prohibidos |
| Alias igual al rol de otro agente, duplicado o ciclo A a B y B a A | Dos agentes en la misma ruta; `exit 4` con escritura parcial; clasificación errónea | Validar la tabla entera antes de escribir: alias únicos, distintos de los nueve roles salvo el propio, sin ciclos |
| Alias igual a un agente de proyecto del usuario | Gana el de proyecto (prioridad 3 frente a 4) | Documentarlo; no se puede comprobar desde el instalador |
| Referencias por nombre del usuario (`Agent(nombre)`, `permissions.deny`, matchers, `--agent`) | Se rompen al renombrar | Documentarlo; SyncLayer no instala `settings.json` |
| Un `.claude/agents/<nombre-viejo>.md` de proyecto | Deja de reemplazar al global | Documentarlo |
| Archivo viejo con descripción casi idéntica al nuevo | Dos agentes activos que se solapan | Informar el huérfano con una advertencia explícita |

## 5. Opciones y recomendación

### 5.1 Dónde vive la tabla de alias

| Opción | Descripción | Veredicto |
|---|---|---|
| **A. Clave `aliases` en `synclayer-config.json`** | Objeto rol a alias, junto a `level`; ambas claves opcionales; clave desconocida sigue dando error | **Recomendada**: el archivo ya existe, ya tiene validación cerrada y la Fase 3 reservó el hueco. Evitar nombrar la clave `agents`, que una prueba usa como ejemplo de clave desconocida |
| B. Archivo aparte | `synclayer-aliases.json` | Otro archivo que validar y documentar, sin ventaja |

### 5.2 Cómo separar rol y ruta

1. El **rol** (`agents/<rol>.md`) sigue siendo la clave del manifiesto, de la tabla de niveles, de
   `outBytes`/`outHash` y de los mensajes; la **ruta de destino** (`agents/<alias>.md`) sólo se usa para
   leer, escribir, respaldar y verificar en el destino.
2. El estado necesita saber a qué ruta se escribió cada rol. Propuesta: estado con **esquema 3**, con un
   campo por entrada para la ruta real de destino; el esquema 2 se lee y se migra. Así el huérfano se
   detecta cuando la ruta anterior difiere de la actual y el archivo viejo se informa sin tocarlo.
3. **Generalizar el renderizado:** hoy sólo toca `model:` y `effort:` de seis agentes y su autocomprobación
   exige que todas las demás líneas sean idénticas. Con alias también cambian `name:`, el primer término de
   `description:` y el cuerpo, y se transforman también `rules/agentes.md` y `docs/agentes.md`. Hace falta
   una función de transformación por agente con reglas propias (límite de palabra, cuatro formas del nombre)
   y una autocomprobación que permita sólo esas diferencias, aplicada **antes** del renderizado de nivel o en
   un orden fijado.
4. Con alias y sin alias, `outHash` pasa a ser el hash de lo escrito para ese agente y ese conjunto de
   alias; el manifiesto sigue verificando sólo el origen.

### 5.3 Reemplazo de texto

Reemplazo con límite de palabra y cuatro formas por nombre, sólo en `agents/*.md`, `rules/agentes.md` y
`docs/agentes.md`, con alias de lista cerrada de caracteres. Los demás archivos no se transforman. Límite
reconocido: el reemplazo es textual, no semántico; una frase que mencione un rol como concepto y no como
agente también cambiaría.

### 5.4 Reporte de uso

Opciones: (a) dejarlo así y documentar que un agente con alias aparece como `(otro agente)`; (b) que el
reporte lea la tabla de alias y agrupe por rol. La (b) sale del alcance de esta fase y reabre la lectura
defensiva de la Fase 2.

## 6. Riesgos y preguntas abiertas

| Riesgo | Mitigación |
|---|---|
| Cambio profundo del instalador (rol y ruta separados) | Fases pequeñas, TDD, `auditor` por task y `shield` en las que escriben |
| Fallo silencioso del nivel al aliar un agente | Prueba específica: alias y nivel juntos |
| Escritura parcial por colisiones | Validar toda la tabla antes de escribir; `exit 1` |
| Las pruebas de PowerShell sólo corren con 5.1 (pwsh no instalado) | Igual que hoy |
| Sin G1, el efecto de renombrar en Claude Code real no está verificado (renombrar en caliente no documentado) | Compuerta del propietario antes de aplicar a su `~/.claude`; documentar |

Preguntas abiertas para el propietario: ver el mensaje de cierre de la exploración (conjunto de caracteres
del alias, cómo se capitalizan los nombres en los textos y qué hacer con el reporte de uso).
