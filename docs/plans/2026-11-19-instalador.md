# Plan: instalador `install.ps1` con manifiesto SHA-256

Fecha: 2026-11-19. Estado: pendiente de aprobación del propietario.

## 1. Objetivo

Sustituir el bloque manual de «Instalación» del `README.md` por un instalador PowerShell,
`install.ps1`, en la raíz del repositorio. El instalador copia a `~/.claude/` sólo los doce
archivos de SyncLayer que Claude Code lee, guiado por un manifiesto con el SHA-256 de cada
uno, con respaldo previo, modo `-DryRun` y verificación de hashes antes y después de copiar.

Archivos gestionados (doce):

- `agents/*.md` (nueve): `atlas`, `auditor`, `debugger`, `forge`, `oracle`, `scout`,
  `scribe`, `sentinel`, `shield`.
- `rules/agentes.md`
- `hooks/agent_guard.py`
- `docs/agentes.md`

### Fuera de alcance

- No instala `docs/brand/`, `assets/`, `tests/`, `tools/` ni el propio manifiesto del repo.
- No sincroniza automáticamente. No toca `~/.claude/settings.json` ni `~/.claude/CLAUDE.md`.
- No borra nada en el destino, ni siquiera archivos que una versión anterior instaló.
- No hace rollback automático si falla a mitad de la copia (deja el respaldo e informa).
- No usa Pester (ver 3.6).
- La sección «Línea de tiempo y avance» del README no aplica: este plan no es un plan
  extenso por fases que se implemente por etapas.

### Siguientes (decidido: no se diseñan aquí)

- Comando `status` que compare por hash el destino con el manifiesto.
- Copia inversa `~/.claude` -> repositorio automatizada. Hasta entonces sigue vigente la
  regla manual del README (por archivo, con `git ls-files`, nunca con comodines).

## 2. Supuestos

1. Entorno principal: Windows PowerShell 5.1. `install.ps1` debe correr igual en pwsh 7.
   Otros sistemas operativos no se verifican y no se documentan como soportados.
2. El instalador no depende de git ni de Python. El generador del manifiesto y las pruebas
   sí usan Python 3.12 (biblioteca estándar) y git, como el resto del repositorio.
3. Los doce archivos son texto. El hash se calcula sobre el contenido con `CRLF` convertido
   a `LF` («hash canónico», ver 3.2).
4. El instalador puede dejar un archivo propio en el destino,
   `~/.claude/synclayer-manifest.json`, con lo último que instaló. Sin él no se distingue
   «versión anterior de SyncLayer» de «editado a mano» (pregunta abierta P2).
5. Los frontmatter de los agentes apuntan a `$HOME/.claude/hooks/agent_guard.py`. Por eso
   `-Target` sirve para pruebas; el instalador no honra `CLAUDE_CONFIG_DIR`.
6. El trabajo se hace en una rama (`feat/instalador`), con commits sin etiquetas de
   coautoría, y sin nada personal en archivos, mensajes ni fixtures (usar `~`).

## 3. Diseño

### 3.1 Piezas

| Pieza | Ruta | Lenguaje | Papel |
|---|---|---|---|
| Generador del manifiesto | `tools/build_manifest.py` | Python stdlib | Lista los archivos gestionados y escribe el manifiesto. `--check` compara sin escribir |
| Manifiesto | `install-manifest.json` | JSON | Qué se instala y con qué hash canónico |
| Instalador | `install.ps1` | PowerShell 5.1+ | Verifica, respalda, copia, verifica |
| Estado instalado | `<Target>/synclayer-manifest.json` | JSON | Copia del manifiesto de la última instalación correcta |
| Pruebas | `tests/test_manifest.py`, `tests/test_install.py` | unittest | Sincronía del manifiesto y comportamiento del instalador |

`tools/` es una carpeta nueva. Se prefiere a `assets/brand/src/` porque esa carpeta es de
marca, y a `hooks/` porque todo lo que hay ahí se instala.

### 3.2 Finales de línea y hash canónico

Problema: en este equipo git convierte a `CRLF` al hacer checkout («LF will be replaced by
CRLF»). Un hash sobre los bytes del árbol de trabajo cambia según la configuración de git de
cada máquina.

Opciones:

| Opción | A favor | En contra |
|---|---|---|
| A. `.gitattributes` con `eol=lf` y hash de bytes crudos | Hash simple (`Get-FileHash`) | Obliga a renormalizar el árbol; un checkout viejo o un editor que guarde `CRLF` rompe el hash; depende de la configuración de git |
| B. Hash canónico: SHA-256 de los bytes con cada `CRLF` sustituido por `LF` | Independiente de `autocrlf`, de `.gitattributes` y de zip frente a clon | Dos implementaciones (Python y PowerShell) que deben coincidir |
| C. Hash del blob de git (`git hash-object`) | Lo calcula git | El instalador dependería de git y no serviría para el destino |

Se elige **B**. Reglas exactas:

- Hash canónico = SHA-256, en hexadecimal minúsculas, de los bytes del archivo tras sustituir
  cada par `0D 0A` por `0A`. Un `0D` suelto no se toca. No se quita BOM ni se recodifica.
- Se usa el mismo hash para el origen, para el destino antes de copiar y para el destino
  después de copiar.
- El instalador **escribe en el destino los bytes canónicos (`LF`)**, no los del árbol de
  trabajo. El destino queda idéntico venga de donde venga el origen (pregunta abierta P3).
- Sugerencia de implementación en PowerShell para que sea exacto y rápido: leer bytes,
  decodificar con ISO-8859-1 (un byte, un carácter), sustituir, volver a codificar con
  ISO-8859-1. No usar `Get-Content`/`Set-Content` ni `Get-FileHash` sobre el archivo crudo.
- Coincidencia entre implementaciones: una prueba instala desde un origen con `CRLF` contra
  un manifiesto generado por Python y comprueba que termina con exit 0 y que el destino
  queda en `LF`.

### 3.3 Manifiesto

Archivo `install-manifest.json`, en la raíz, versionado. Formato:

```json
{
  "schema": 1,
  "algorithm": "sha256",
  "eol": "lf",
  "files": [
    {"path": "agents/atlas.md", "sha256": "<64 hex>"}
  ]
}
```

- `files` ordenado por `path`. Rutas relativas con `/`. Salida determinista: sangría de 2
  espacios, sólo ASCII, `LF`, salto de línea final. Sin fecha, sin commit, sin nombre de
  máquina (el repo es público y el archivo debe ser reproducible).
- Lista de archivos: salida de `git ls-files -z -- agents rules hooks docs/agentes.md`,
  filtrada por la lista permitida:

  ```
  ^(agents/[a-z0-9_-]+\.md|rules/agentes\.md|hooks/agent_guard\.py|docs/agentes\.md)$
  ```

  Si `git ls-files` devuelve bajo `agents/`, `rules/` o `hooks/` una ruta que no cumple la
  lista permitida, el generador falla con un mensaje claro: alguien agregó un archivo y hay
  que decidir si se instala.
- Quién lo regenera: quien cambie cualquiera de los doce archivos, con
  `python -B tools/build_manifest.py`, en el mismo commit. No hay hook de git.
- Cómo se evita que quede desactualizado: `tests/test_manifest.py` falla si (a) las rutas del
  manifiesto no son exactamente las de `git ls-files` filtradas, o (b) algún hash canónico
  del árbol de trabajo no coincide. El mensaje de fallo incluye el comando para regenerar.
  La suite ya se corre en cada cambio, así que un manifiesto viejo no pasa el cierre.

Interfaz de `tools/build_manifest.py` (la usan las pruebas; firmas exactas):

```python
ALLOWED: re.Pattern                              # la lista permitida de arriba
def canonical_sha256(data: bytes) -> str
def managed_files(root: str) -> list[str]        # git ls-files filtrado y ordenado
def build_manifest(root: str, paths: list[str]) -> dict
def render(manifest: dict) -> str                # texto JSON determinista
def main(argv: list[str]) -> int                 # sin args: escribe; --check: 0 al dia, 1 si no
```

Límite que debe quedar escrito en la documentación: el manifiesto vive en el mismo
repositorio que los archivos. Detecta deriva, corrupción y ediciones sin regenerar. **No
autentica el origen**: quien puede cambiar un archivo puede cambiar también el manifiesto.

### 3.4 Comportamiento de `install.ps1`

Parámetros:

| Parámetro | Tipo | Por defecto | Efecto |
|---|---|---|---|
| `-Target` | string | `~/.claude` (`Join-Path $HOME '.claude'`) | Carpeta de destino. Permite probar contra una carpeta temporal |
| `-BackupDir` | string | `<Target>-backup-<yyyyMMdd-HHmmss>` (con el destino por defecto: `~/.claude-backup-<fecha>`) | Dónde se guardan los archivos que se van a sobrescribir |
| `-DryRun` | switch | apagado | Muestra el plan y no escribe nada |
| `-Force` | switch | apagado | Permite sobrescribir archivos con cambios locales (siempre con respaldo) |

El origen es siempre `$PSScriptRoot`. No hay parámetro `-Source`: las pruebas copian
`install.ps1` a una carpeta temporal con sus fixtures.

Secuencia. Los pasos 1 a 4 no escriben nada.

1. **Cargar el manifiesto** `install-manifest.json` junto al script. Validar `schema` igual
   a 1, `algorithm` igual a `sha256`, y que cada `path` cumpla la misma lista permitida de
   3.3, escrita también dentro del script. Rutas duplicadas, absolutas, con `..`, con `\` o
   con `:` se rechazan. Fallo: exit 1.
2. **Verificar el origen**: cada archivo existe y su hash canónico coincide con el
   manifiesto. Fallo: exit 2, con la lista de archivos y sin escribir nada.
3. **Leer el estado previo** `<Target>/synclayer-manifest.json` si existe. Si no se puede
   leer o no valida, se trata como ausente y se avisa.
4. **Clasificar** cada archivo del manifiesto según el hash canónico del destino:

   | Estado | Condición | Acción |
   |---|---|---|
   | `NUEVO` | El destino no existe | Copiar |
   | `IGUAL` | Hash del destino = hash del manifiesto | Nada: ni respaldo ni escritura |
   | `ACTUALIZAR` | Distinto, y hash del destino = hash del estado previo | Respaldar y copiar |
   | `MODIFICADO` | Distinto, y sin estado previo o con hash distinto al del estado previo | Sin `-Force`: abortar toda la ejecución. Con `-Force`: respaldar y copiar |
   | `HUERFANO` | Está en el estado previo y ya no en el manifiesto | Sólo avisar. No se borra |

   Si hay algún `MODIFICADO` sin `-Force`: exit 3, antes de escribir un solo byte. El mensaje
   lista los archivos y explica las dos salidas: llevar el cambio al repositorio (regla de
   copia inversa del README) o repetir con `-Force`.

   Si un archivo de destino, o una de las carpetas `agents`, `rules`, `hooks`, `docs` del
   destino, es un punto de reanálisis (enlace simbólico o junction): exit 1. `-Target` en sí
   también se rechaza si es un punto de reanálisis (decisión del propietario: exit 1). Los
   ancestros de `-Target` (p. ej. `~` o `~/.claude` bajo un enlace) no se comprueban: riesgo
   residual documentado.
5. **Mostrar el plan**: una línea por archivo, `ESTADO  ruta`, y un resumen con los conteos.
   Con `-DryRun` termina aquí: exit 0, o el 1, 2 o 3 que habría dado la ejecución real. Con
   `-DryRun` no se crea `Target`, ni `BackupDir`, ni ningún archivo.
6. **Respaldar** en `BackupDir`, con la misma ruta relativa, cada archivo que se va a
   sobrescribir (`ACTUALIZAR`, y `MODIFICADO` con `-Force`), más el estado previo si existe.
   `BackupDir` no se crea si no hay nada que respaldar. Nunca se sobrescribe un respaldo: si
   el archivo de respaldo ya existe, exit 1. El respaldo se verifica (mismo hash que el
   archivo original) antes de seguir.
7. **Copiar**, primero `hooks/agent_guard.py` y después el resto, para que ningún agente con
   `hooks:` quede instalado sin su guarda. Por archivo: crear la carpeta si falta, escribir
   los bytes canónicos en un temporal dentro de la misma carpeta, y moverlo sobre el destino.
   Una escritura directa que se corte dejaría un `agent_guard.py` truncado, y un hook que
   termina con un código distinto de 0 o 2 deja pasar la llamada.
8. **Verificar el destino**: recalcular el hash canónico de cada archivo escrito. Si falla
   la copia o la verificación: exit 4, se detiene, informa qué se escribió y dónde está el
   respaldo. No hay rollback.
9. **Escribir el estado** `<Target>/synclayer-manifest.json` (copia del manifiesto), sólo si
   todo lo anterior pasó. Si todos los archivos estaban `IGUAL` y el estado no existía o es
   distinto, se escribe igual.
10. **Mensaje final**: conteos, ruta del respaldo si lo hubo, y tres recordatorios: reiniciar
    las sesiones de Claude Code abiertas; el instalador no toca `settings.json` ni
    `~/.claude/CLAUDE.md`, que debe apuntar a `~/.claude/rules/agentes.md`; no hay
    sincronización automática. Si `-Target` no es `~/.claude`, avisa de que los `hooks:` de
    los agentes apuntan a `$HOME/.claude/hooks/agent_guard.py`.

Códigos de salida:

| Código | Significado | ¿Se escribió algo? |
|---|---|---|
| 0 | Correcto, incluido «nada que hacer» y `-DryRun` sin problemas | Sólo en ejecución real |
| 1 | Uso o entorno: manifiesto ausente o inválido, ruta no permitida, punto de reanálisis, respaldo que ya existe, destino no escribible, error no previsto | No, salvo fallo de E/S en el respaldo |
| 2 | El origen no coincide con el manifiesto | No |
| 3 | Cambios locales en el destino y falta `-Force` | No |
| 4 | Falló la copia o la verificación posterior | Sí, parcial; el respaldo queda |

Reglas de compatibilidad con Windows PowerShell 5.1:

- `install.ps1` va en ASCII puro: 5.1 lee como ANSI un archivo sin BOM. Los mensajes van en
  español sin acentos, como la cabecera de `hooks/agent_guard.py`. Hay una prueba.
- `Set-StrictMode -Version 2`, `$ErrorActionPreference = 'Stop'`, y un `try/catch` global
  que convierte cualquier error no previsto en exit 1.
- Sólo cmdlets y tipos .NET disponibles en 5.1. Nada de operador ternario, `??`, `&&`,
  `-AsHashtable` ni `Join-Path` con más de dos segmentos.
- E/S de archivos con `-LiteralPath` o con `[System.IO.File]`, nunca con `-Path` y comodines.
  Ninguna ruta se construye con `*`.
- Sin `Invoke-Expression`, sin red, sin módulos externos, sin elevar privilegios.

### 3.5 Garantía «no toca archivos ajenos»

El instalador sólo abre para escritura: los doce destinos del manifiesto (limitados además por
la lista permitida del script), sus temporales, `<Target>/synclayer-manifest.json` y lo que
hay bajo `BackupDir`. No enumera carpetas del destino. No borra. La prueba coloca archivos
ajenos (por ejemplo `hooks/otro-statusline.ps1`, `agents/ajeno.md`, `settings.json`,
`CLAUDE.md`) y comprueba que sus bytes y su fecha de modificación no cambian.

### 3.6 Estrategia de pruebas

- Todo con `unittest` de la biblioteca estándar: `python -B -m unittest discover -s tests`.
- `tests/test_install.py` lanza el script con `subprocess.run`, sin shell y con `timeout`:
  `[exe, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', script, ...]`
  (`-ExecutionPolicy` sólo en Windows).
- Intérpretes: `shutil.which('powershell')` y `shutil.which('pwsh')`. Cada caso corre con
  todos los que existan (`subTest`). Si no hay ninguno, la clase se salta con el motivo
  «no hay powershell.exe ni pwsh en el PATH: pruebas de install.ps1 omitidas». El salto debe
  verse en la salida; el cierre exige al menos una ejecución sin saltos en este equipo.
- Origen de las pruebas: una carpeta temporal con una copia de `install.ps1`, archivos
  ficticios pequeños en las rutas permitidas y un manifiesto generado con
  `tools/build_manifest.py` (`build_manifest` + `render`). Así no dependen del contenido real.
  Una prueba aparte usa el repositorio real como origen contra un destino temporal.
- Las carpetas temporales llevan un espacio en el nombre
  (`tempfile.TemporaryDirectory(prefix='sync layer ')`).
- Ninguna prueba usa el destino por defecto: todas pasan `-Target`. Como segunda barrera, el
  subproceso recibe `USERPROFILE`, `HOMEDRIVE`/`HOMEPATH` y `HOME` apuntando a una carpeta
  temporal. Esto no es garantía (pwsh no siempre deriva `$HOME` de esas variables); la
  garantía es que `-Target` siempre va explícito.
- Pester: descartado. Windows PowerShell 5.1 trae Pester 3.4, con sintaxis incompatible con
  la 5.x; usarlo exigiría instalar una versión, que sería una dependencia nueva.

Casos mínimos (los siete pedidos más los del diseño):

| # | Caso | Se comprueba |
|---|---|---|
| 1 | `-DryRun` sobre destino con archivos | Exit 0; ningún archivo creado ni modificado (bytes y mtime); sin `BackupDir`; salida con los estados |
| 2 | `-DryRun` con destino inexistente | Exit 0; todos `NUEVO`; el destino sigue sin existir |
| 3 | Destino inexistente, ejecución real | Exit 0; los archivos del manifiesto existen con el hash correcto; estado escrito; sin `BackupDir` |
| 4 | Respaldo creado | Tras cambiar el origen y regenerar el manifiesto: `ACTUALIZAR`, `BackupDir` contiene la versión anterior con su ruta relativa |
| 5 | Archivos ajenos intactos | Bytes y mtime de los ajenos sin cambio; ninguno aparece en el respaldo |
| 6 | Hash del origen alterado | Exit 2; destino sin cambios; el mensaje nombra el archivo |
| 7 | Reejecución idempotente | Segunda ejecución: exit 0, todos `IGUAL`, sin `BackupDir` nuevo, mtime de los destinos sin cambio |
| 8 | Rutas con espacios | `-Target` y `-BackupDir` con espacios funcionan |
| 9 | Cambio local sin `-Force` | Exit 3; nada escrito; ningún otro archivo se actualiza |
| 10 | Cambio local con `-Force` | Exit 0; la versión local queda en el respaldo |
| 11 | Destino preexistente sin estado y distinto | `MODIFICADO` (exit 3) |
| 12 | Destino preexistente sin estado e idéntico | `IGUAL`; se escribe el estado; sin respaldo |
| 13 | Origen con `CRLF` | Exit 0; el destino queda en `LF`; un destino con `CRLF` y mismo contenido es `IGUAL` |
| 14 | Manifiesto con ruta fuera de la lista (`../x`, `docs/brand/a.md`, `C:/x`, `settings.json`) | Exit 1; nada escrito |
| 15 | Manifiesto ausente o JSON inválido | Exit 1 |
| 16 | `HUERFANO` | Se avisa; el archivo sigue en el destino |
| 17 | Respaldo que ya existe | Exit 1; el respaldo anterior no cambia |
| 18 | Repositorio real como origen | Exit 0; doce archivos; no existe `docs/brand` ni `tests` en el destino |
| 19 | `install.ps1` es ASCII puro | Lectura de bytes desde Python |
| 20 | Punto de reanálisis en un destino | Exit 1. Se salta con motivo claro si el sistema no deja crear el enlace sin privilegios |

## 4. Tareas

Todas son secuenciales: T3, T4 y T5 tocan los mismos dos archivos, y T2 a T6 dependen de lo
anterior. No hay tareas paralelizables. Cada una sigue el ciclo `forge` + `auditor`. Regla
para todas: primero la prueba que falla, después la implementación; Python siempre con `-B`.

### Fase 1: manifiesto

#### T1. Generador del manifiesto

- **Objetivo:** `tools/build_manifest.py` con la interfaz de 3.3.
- **Archivos:** crear `tools/build_manifest.py`, `tests/test_manifest.py`.
- **Pasos:** escribir las pruebas unitarias; implementar `canonical_sha256`, `ALLOWED`,
  `managed_files`, `build_manifest`, `render` y `main` (escribir y `--check`). `managed_files`
  llama a `git ls-files -z` sin shell.
- **Pruebas:** `canonical_sha256(b'a\r\nb') == canonical_sha256(b'a\nb')`; un `\r` suelto
  cambia el hash; valor conocido para `b''`; `ALLOWED` acepta las doce rutas y rechaza
  `docs/brand/x.md`, `agents/x.txt`, `agents/sub/x.md`, `../x`, `hooks/otro.ps1`; `render` es
  determinista, ASCII, con `LF` y salto final; `build_manifest` sobre una carpeta temporal;
  un archivo no permitido bajo `agents/` hace fallar el generador.
- **Aceptación:** la suite pasa; `test_manifest.py` usa sólo la biblioteca estándar; las
  pruebas que necesitan git se saltan con motivo claro si git no está.
- **Dependencias:** ninguna.

#### T2. Manifiesto versionado y prueba de sincronía

- **Objetivo:** `install-manifest.json` en el repo y una prueba que falle si queda viejo.
- **Archivos:** crear `install-manifest.json`; modificar `tests/test_manifest.py`.
- **Pasos:** agregar la prueba de sincronía (falla: no hay manifiesto); generar el manifiesto
  con `python -B tools/build_manifest.py`.
- **Pruebas:** rutas del manifiesto = `managed_files(ROOT)`; son doce, nueve de ellas
  `agents/*.md`; cada hash = hash canónico del árbol de trabajo; el archivo en disco es igual
  a `render(build_manifest(...))` salvo finales de línea; el fallo muestra el comando para
  regenerar.
- **Aceptación:** la suite pasa. Comprobación manual que el `forge` debe ejecutar y reportar:
  agregar un espacio a `rules/agentes.md` hace fallar la prueba; `--check` sale con 1;
  revertir el cambio vuelve todo a verde. El manifiesto no contiene rutas absolutas ni datos
  de la máquina.
- **Dependencias:** T1.

### Fase 2: instalador

#### T3. `install.ps1`: validación, verificación del origen, plan y `-DryRun` — revisión de seguridad

- **Objetivo:** pasos 1 a 5 de 3.4. Todavía no escribe nada en ningún modo: sin `-DryRun`
  termina con exit 1 y el mensaje «instalacion no implementada» (se reemplaza en T4).
- **Archivos:** crear `install.ps1`, `tests/test_install.py`.
- **Pasos:** en `tests/test_install.py`, los auxiliares de 3.6 (descubrir intérpretes, armar
  el origen ficticio, ejecutar y devolver código, stdout y stderr, fotografiar un árbol con
  bytes y mtime). En `install.ps1`: parámetros, carga y validación del manifiesto, hash
  canónico, verificación del origen, lectura del estado previo, clasificación, salida del
  plan, códigos 0, 1, 2 y 3.
- **Pruebas:** casos 1, 2, 6, 8 (en `-DryRun`), 9 y 11 (en `-DryRun`), 13 (clasificación),
  14, 15, 16, 19.
- **Aceptación:** la suite pasa con `powershell.exe` y, si existe, con `pwsh`; el reporte
  dice con cuál corrió. `install.ps1` no contiene `Invoke-Expression`, ni `*` en rutas, ni
  rutas personales. Ningún caso deja archivos fuera de las carpetas temporales.
- **Dependencias:** T1 (las pruebas generan manifiestos con el módulo), T2.

#### T4. `install.ps1`: respaldo, copia, verificación y estado — revisión de seguridad

- **Objetivo:** pasos 6 a 10 de 3.4 para `NUEVO`, `IGUAL` y `ACTUALIZAR`.
- **Archivos:** modificar `install.ps1`, `tests/test_install.py`.
- **Pasos:** respaldo verificado; copia con `agent_guard.py` primero, temporal en la misma
  carpeta y movimiento sobre el destino; verificación posterior; escritura del estado;
  mensaje final con los recordatorios; código 4.
- **Pruebas:** casos 3, 4, 5, 7, 8, 12, 13 (bytes `LF` en el destino), 17, 18. Además: el
  orden de copia (el hook antes que los agentes) se comprueba con la salida; tras una
  ejecución correcta no queda ningún temporal en el destino.
- **Aceptación:** la suite pasa; `-DryRun` sigue sin escribir (los casos 1 y 2 siguen en
  verde); el mensaje final nombra el reinicio de sesiones y no afirma sincronización.
- **Dependencias:** T3.

#### T5. `install.ps1`: cambios locales, `-Force` y puntos de reanálisis — revisión de seguridad

- **Objetivo:** cerrar el paso 4 de 3.4 en ejecución real.
- **Archivos:** modificar `install.ps1`, `tests/test_install.py`.
- **Pasos:** aborto con exit 3 antes de cualquier escritura; `-Force` con respaldo; estado
  previo ilegible tratado como ausente con aviso; rechazo de puntos de reanálisis.
- **Pruebas:** casos 9, 10 y 11 en ejecución real, 16 en ejecución real, 20. Además: con un
  `MODIFICADO` y un `ACTUALIZAR` a la vez y sin `-Force`, no se escribe ninguno de los dos.
- **Aceptación:** la suite pasa; con exit 3 el destino es idéntico byte a byte y no existe
  `BackupDir`; con `-Force` la versión local está en el respaldo y coincide en hash.
- **Dependencias:** T4.

### Fase 3: documentación

#### T6. Documentación y manifiesto final

- **Objetivo:** dejar la documentación al día en el mismo cambio.
- **Archivos:** modificar `README.md`, `CLAUDE.md`, `HISTORY.md`, `docs/agentes.md`,
  `install-manifest.json`.
- **Pasos:**
  - `README.md`, «Instalación»: sustituir el bloque manual por el uso del instalador:
    `-DryRun` primero, después la ejecución real. Incluir la invocación para equipos donde la
    política de ejecución bloquea scripts
    (`powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -DryRun`), aclarando
    que sólo afecta a ese proceso (P4). Documentar parámetros, estados, códigos de salida,
    dónde queda el respaldo y el archivo `~/.claude/synclayer-manifest.json`. Mantener el
    fragmento de `~/.claude/CLAUDE.md` y el aviso de reiniciar sesiones.
  - `README.md`, «Dos copias, sin sincronización automática»: mantener la regla de copia
    inversa manual tal cual. Cambiar «Repositorio -> `~/.claude`» para que remita al
    instalador. Decir que el manifiesto detecta deriva y no autentica el origen.
  - `README.md`: «Estructura» (`install.ps1`, `install-manifest.json`, `tools/`, pruebas
    nuevas), «Pruebas» (conteo nuevo, tomado de la salida real de la suite, y que las de
    `install.ps1` se saltan sin PowerShell), «Mantenimiento» (tras cambiar un archivo
    gestionado: regenerar el manifiesto y reinstalar).
  - `CLAUDE.md`: comandos (`python -B tools/build_manifest.py`, `--check`, instalación contra
    una carpeta temporal con `-Target`); arquitectura (cuarta pieza); convención (todo cambio
    en `install.ps1` empieza con una prueba que falla; `install.ps1` en ASCII); no obvios
    (hash canónico con `LF`; el destino se escribe en `LF`; `MODIFICADO` aborta sin `-Force`;
    el hook se copia primero; `-Target` distinto de `~/.claude` no sirve para uso real por
    los `hooks:`; nunca se borra); «Cierre de un cambio» (regenerar el manifiesto).
  - `HISTORY.md`, `[Sin publicar]`: sección «Añadido (instalador)» y la lista «Siguientes».
  - `docs/agentes.md`: fila «Copias previas» (el instalador respalda lo que sobrescribe y no
    toca `CLAUDE.md` ni `settings.json`), fila nueva para `synclayer-manifest.json`, y «Cómo
    revertir» (restaurar desde el respaldo y borrar el archivo de estado). Mantener el voseo
    del archivo.
  - Al final, regenerar el manifiesto: `docs/agentes.md` es un archivo gestionado.
- **Pruebas:** suite completa.
- **Aceptación:** la suite pasa (la prueba de sincronía confirma el manifiesto regenerado);
  ningún documento afirma sincronización automática, soporte de otros sistemas, autenticación
  del origen ni rollback; no quedan en el README los bucles `Copy-Item ".\$d\*"`; el conteo de
  pruebas del README coincide con la salida de la suite; nada personal en los textos.
- **Dependencias:** T5.

### Cierre (lo coordina la sesión principal)

- **C1. `sentinel`:** suite completa con `powershell.exe` y con `pwsh` si existe; salida a la
  vista y sin saltos en los casos del instalador.
- **C2. `shield`:** revisión de T3, T4 y T5. Aplica: escribe en `~/.claude`, construye rutas
  a partir de un archivo, ejecuta un script y la documentación recomienda una invocación con
  `-ExecutionPolicy Bypass`. Focos: validación de rutas del manifiesto, enlaces y junctions,
  carrera entre clasificar y escribir, temporales, colisión de respaldos, ventana en la que
  `agent_guard.py` falta o está incompleto, y que la documentación no prometa autenticidad.
- **C3. `auditor`** sobre el cambio completo.
- **C4. Verificación en el equipo real (propietario):** `install.ps1 -DryRun` contra
  `~/.claude`, revisar el plan, instalar, reiniciar sesiones. No se automatiza.

## 5. Riesgos

| Riesgo | Mitigación |
|---|---|
| `autocrlf` cambia los bytes del árbol de trabajo y con ellos el hash | Hash canónico (3.2); caso 13; prueba unitaria en T1 |
| El hash de Python y el de PowerShell divergen | Regla única por bytes; el caso 13 cruza las dos implementaciones |
| Manifiesto desactualizado | Prueba de sincronía (T2) y `--check`; el instalador aborta con exit 2 |
| Primera ejecución sobre una instalación manual: sin estado previo, todo lo distinto es `MODIFICADO` | Mensaje con las dos salidas; `-DryRun` primero; documentado en el README (P1) |
| `agent_guard.py` truncado o ausente deja la guarda sin efecto | Copia mediante temporal y movimiento; el hook va primero; verificación posterior; exit 4 |
| Un manifiesto manipulado dirige escrituras fuera de los doce archivos | Lista permitida dentro del script, además de la del generador; caso 14 |
| Falsa sensación de autenticidad | Límite escrito en README y CLAUDE.md: integridad, no autenticidad |
| Las pruebas tocan el `~/.claude` real | `-Target` siempre explícito; variables de entorno redirigidas; revisión de `auditor` |
| La política de ejecución bloquea `install.ps1` | Invocación documentada con `-ExecutionPolicy Bypass -File`, limitada al proceso |
| Windows PowerShell 5.1 lee mal un script con acentos sin BOM | Script en ASCII; caso 19 |
| Las pruebas del instalador se saltan sin que nadie lo note | Motivo de salto explícito; C1 exige ejecución sin saltos |
| Archivo de destino bloqueado por otro proceso o por antivirus | Exit 4 con el archivo afectado; el respaldo queda; reejecutar es seguro |
| Fallo a mitad de la copia deja versiones mezcladas | Sin rollback: se informa qué se escribió y dónde está el respaldo; reejecutar completa |
| `tools/` o el manifiesto acaban instalados por error | La lista permitida no los incluye; caso 18 |

## 6. Preguntas abiertas

Cada una tiene un valor por defecto, que es el que el plan implementa si no hay respuesta.

- **P1. Cambios locales en el destino.** Por defecto: abortar con exit 3 y exigir `-Force`.
  Alternativa: sobrescribir siempre, con respaldo y aviso. La alternativa simplifica la
  primera instalación sobre una copia manual, pero un cambio hecho en vivo y no llevado al
  repo sólo quedaría en la carpeta de respaldo.
- **P2. Archivo de estado en el destino.** Por defecto: se crea
  `~/.claude/synclayer-manifest.json`. Sin él, todo archivo distinto se trata como
  `MODIFICADO` y cada actualización exigiría `-Force`.
- **P3. Finales de línea en el destino.** Por defecto: siempre `LF`. Alternativa: copiar los
  bytes del árbol de trabajo tal cual (`CRLF` en este equipo). Con cualquiera de las dos la
  comparación por hash funciona.
- **P4. Invocación documentada.** Por defecto: el README muestra `.\install.ps1` y, aparte,
  la forma con `-ExecutionPolicy Bypass -File` para equipos con política restrictiva.
  Alternativa: documentar sólo `.\install.ps1` y dejar la política al usuario.
