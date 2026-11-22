<#
.SYNOPSIS
Instala en ~/.claude los doce archivos de SyncLayer, guiado por install-manifest.json.

.DESCRIPTION
Valida el manifiesto, verifica el origen (hash canonico), lee el estado previo, clasifica cada
archivo y muestra el plan. Sin -DryRun respalda lo que va a sobrescribir (verificado), copia con
el hook primero (temporal en la misma carpeta + movimiento), verifica el destino y escribe el
estado <Target>/synclayer-manifest.json. Nunca borra. No hace rollback: si falla, informa.

Configuracion: <Target>/synclayer-config.json es opcional y tiene un solo campo, level (entero de 1 a 5;
sin archivo, o con un objeto vacio, el nivel es 5). Un archivo invalido, o una carpeta o un enlace con ese
nombre, detiene la instalacion con exit 1 antes de escribir nada (tambien con -DryRun). Con el nivel 1 a 4, el
instalador reescribe model: y effort: del frontmatter de los seis agentes modificables (atlas, forge, sentinel,
scribe, scout, oracle) con los valores de la tabla de niveles; auditor, shield, debugger, el hook y el resto
quedan como el origen. El nivel 5 es el repositorio tal cual. El instalador nunca escribe, respalda ni borra
el archivo de configuracion.

Estado: esquema 2, por archivo el hash del origen (sha256), el hash de lo escrito (written) y el
nivel de la instalacion (level). La clasificacion compara el destino con el hash escrito por la
instalacion previa (written) y el origen con el manifiesto. Lee tambien el esquema 1 (copia del
manifiesto, de la Fase 1) y lo migra al reinstalar (el estado viejo va al respaldo). Un estado
ilegible, invalido o de otro esquema se trata como ausente: nunca produce ACTUALIZAR.

Hash canonico: SHA-256 (hex minusculas) de los bytes del archivo con cada CRLF sustituido por
LF. Un CR suelto no se toca; no se quita BOM ni se recodifica.

El manifiesto detecta deriva, corrupcion y ediciones sin regenerar. No autentica el origen.

Codigos de salida: 0 correcto; 1 uso o entorno; 2 el origen no coincide con el manifiesto;
3 cambios locales en el destino y falta -Force; 4 fallo la copia o la verificacion.

.PARAMETER Target
Carpeta de destino. Por defecto ~/.claude.

.PARAMETER BackupDir
Carpeta de respaldo. Por defecto <Target>-backup-<yyyyMMdd-HHmmss>.

.PARAMETER DryRun
Muestra el plan y no escribe nada.

.PARAMETER Force
Permite sobrescribir archivos con cambios locales (siempre con respaldo).
#>
[CmdletBinding()]
param(
    [string]$Target = (Join-Path $HOME '.claude'),
    [string]$BackupDir = '',
    [switch]$DryRun,
    [switch]$Force
)

Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'

# Lista permitida: tres rutas fijas (rules/agentes.md, hooks/agent_guard.py, docs/agentes.md) y
# cualquier agents/<nombre>.md con nombre [a-z0-9_-]+. NO es una lista cerrada de doce nombres:
# hoy el repositorio instala doce archivos, pero el patron acepta cualquier agente nuevo. Misma
# regex que ALLOWED de tools/build_manifest.py, pero con \z: en .NET \Z y $ aceptan un salto de
# linea final. El lookahead excluye los nombres reservados de Windows (con, prn, aux, nul,
# com1-9, lpt1-9).
#
# Codigos de salida por fase (inconsistencia documentada, T6 la recoge en el README): un punto de
# reanalisis hallado al clasificar o al respaldar (antes de escribir en el destino) da exit 1; uno
# hallado al copiar, al verificar o al escribir el estado (ya se escribio algo, o se pudo escribir
# fuera) da exit 4. Igual con un archivo bloqueado: antes de escribir es exit 1; al escribir, 4.
$AllowedPattern = '^(agents/(?!(con|prn|aux|nul|com[1-9]|lpt[1-9])\.)[a-z0-9_-]+\.md|rules/agentes\.md|hooks/agent_guard\.py|docs/agentes\.md)\z'
$StateName = 'synclayer-manifest.json'
$ManifestName = 'install-manifest.json'
# Tamano maximo del estado previo que se interpreta (entrada no confiable): el de doce archivos son
# unos 3 KB; un estado mayor se trata como no valido.
$StateMaxBytes = 1048576
# Archivo de configuracion del nivel (Fase 3): <Target>/synclayer-config.json, lo escribe el usuario a mano.
# Es entrada no confiable: tope de tamano, validacion cerrada y el instalador solo lo lee (una vez).
$ConfigName = 'synclayer-config.json'
$ConfigMaxBytes = 65536

# Datos de los alias de agentes (Fase 4). Listas cerradas, una por linea, aun sin uso: la instalacion no
# cambia. Contrato con tests/test_aliases.py y tests/test_install.py: $AliasRoles son los nombres de
# los archivos de la carpeta agents; $ReservedAliases, los agentes integrados de Claude Code (en minuscula: la sensibilidad a
# mayusculas no esta documentada); $YamlWords, los escalares que YAML no lee como cadena en name:.
$AliasRoles = @('atlas', 'auditor', 'debugger', 'forge', 'oracle', 'scout', 'scribe', 'sentinel', 'shield')
$ReservedAliases = @('explore', 'plan', 'general-purpose', 'claude', 'statusline-setup', 'claude-code-guide', 'web-fetch')
$YamlWords = @('true', 'false', 'null', 'yes', 'no', 'on', 'off', 'y', 'n')

# Tabla de niveles (Fase 3). La usa el renderizado de los niveles 1 a 4 (ConvertTo-LevelBytes). Una fila
# por linea, nivel|agente|modelo|esfuerzo, con - para "sin effort:". El nivel 5 es el repositorio y
# no tiene filas. auditor, shield y debugger no estan: quedan fijos en todos los niveles. Contrato
# con tests/test_levels.py: la tabla documentada en el README (entre los marcadores de niveles) debe
# tener las mismas celdas. Es un orden razonado, no una medicion.
$LevelAgents = @('atlas', 'forge', 'sentinel', 'scribe', 'scout', 'oracle')
$AllowedModels = @('opus', 'sonnet', 'haiku')
$AllowedEfforts = @('-', 'low', 'medium', 'high', 'xhigh', 'max')
$LevelRows = @(
    '4|atlas|opus|-',
    '4|forge|sonnet|-',
    '4|sentinel|sonnet|-',
    '4|scribe|sonnet|-',
    '4|scout|sonnet|-',
    '4|oracle|haiku|-',
    '3|atlas|opus|medium',
    '3|forge|sonnet|-',
    '3|sentinel|sonnet|-',
    '3|scribe|sonnet|medium',
    '3|scout|sonnet|-',
    '3|oracle|haiku|-',
    '2|atlas|sonnet|medium',
    '2|forge|sonnet|medium',
    '2|sentinel|sonnet|-',
    '2|scribe|sonnet|low',
    '2|scout|sonnet|medium',
    '2|oracle|haiku|-',
    '1|atlas|sonnet|medium',
    '1|forge|sonnet|low',
    '1|sentinel|sonnet|medium',
    '1|scribe|haiku|medium',
    '1|scout|sonnet|low',
    '1|oracle|haiku|-'
)

# Devuelve el primer problema de la tabla de niveles (texto) o $null si es coherente: 24 filas
# unicas (niveles 1 a 4 por los seis agentes), agente en $LevelAgents, modelo y esfuerzo en las
# listas cerradas.
function Get-LevelTableProblem {
    if ($LevelRows.Count -ne 24) {
        return ('se esperaban 24 filas y hay ' + $LevelRows.Count)
    }
    $seen = @{}
    foreach ($row in $LevelRows) {
        $parts = ([string]$row).Split('|')
        if ($parts.Count -ne 4) {
            return ('fila mal formada: ' + (Format-Safe ([string]$row)))
        }
        if ($parts[0] -cnotmatch '^[1-4]$') {
            return ('nivel fuera de 1 a 4 en la fila ' + (Format-Safe ([string]$row)))
        }
        if ($LevelAgents -cnotcontains $parts[1]) {
            return ('agente fuera de la lista en la fila ' + (Format-Safe ([string]$row)))
        }
        if ($AllowedModels -cnotcontains $parts[2]) {
            return ('modelo fuera de la lista en la fila ' + (Format-Safe ([string]$row)))
        }
        if ($AllowedEfforts -cnotcontains $parts[3]) {
            return ('esfuerzo fuera de la lista en la fila ' + (Format-Safe ([string]$row)))
        }
        $key = $parts[0] + '|' + $parts[1]
        if ($seen.ContainsKey($key)) {
            return ('fila repetida: nivel ' + $parts[0] + ' agente ' + $parts[1])
        }
        $seen[$key] = $true
    }
    return $null
}

# Canales de salida: stdout lleva el plan y las notas informativas (p. ej. HUERFANO); stderr lleva
# los avisos (algo anomalo que no detiene) y los errores. Los mensajes con rutas o textos externos
# pasan por Format-Safe: solo ASCII imprimible, el resto como \uXXXX.
function Write-Out([string]$Text) {
    [Console]::Out.WriteLine($Text)
}

function Write-Err([string]$Text) {
    [Console]::Error.WriteLine($Text)
}

function Stop-Install([int]$Code, [string]$Message) {
    Write-Err $Message
    exit $Code
}

function Format-Safe([string]$Text) {
    $sb = New-Object System.Text.StringBuilder
    foreach ($ch in $Text.ToCharArray()) {
        $code = [int]$ch
        if ($code -ge 0x20 -and $code -le 0x7E) {
            [void]$sb.Append($ch)
        }
        else {
            [void]$sb.Append('\u' + $code.ToString('x4'))
        }
    }
    return $sb.ToString()
}

# Mensaje de la causa original (sin el envoltorio de PowerShell), ya escapado.
function Get-ErrorText($ErrorRecord) {
    $ex = $ErrorRecord.Exception
    while ($null -ne $ex.InnerException) { $ex = $ex.InnerException }
    return Format-Safe $ex.Message.Trim()
}

# Igualdad ORDINAL de cadenas: -ceq compara segun la cultura e ignora caracteres como NUL (U+0000) o el
# guion blando (U+00AD), asi que no vale para texto no confiable (claves y valores de un JSON).
function Test-OrdinalEqual($A, $B) {
    return (($A -is [string]) -and ($B -is [string]) -and [string]::Equals($A, $B, [System.StringComparison]::Ordinal))
}

# Pertenencia ordinal a una lista cerrada de cadenas.
function Test-OrdinalIn($List, $Item) {
    foreach ($candidate in $List) {
        if (Test-OrdinalEqual $candidate $Item) { return $true }
    }
    return $false
}

# Busca la propiedad distinguiendo mayusculas y de forma ordinal (PSObject.Properties[nombre] no las distingue).
function Get-PropRaw($Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    foreach ($p in $Object.PSObject.Properties) {
        if (Test-OrdinalEqual $p.Name $Name) { return $p }
    }
    return $null
}

function Get-Prop($Object, [string]$Name) {
    $prop = Get-PropRaw $Object $Name
    if ($null -eq $prop) { return $null }
    return $prop.Value
}

# Ruta absoluta del sistema de archivos. Rechaza otros proveedores (HKCU:\...) y rutas no absolutas.
function Resolve-FsPath([string]$Path, [string]$What) {
    $provider = $null
    $drive = $null
    $full = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path, [ref]$provider, [ref]$drive)
    if ($null -eq $provider -or $provider.Name -ne 'FileSystem' -or -not [System.IO.Path]::IsPathRooted($full)) {
        Stop-Install 1 ('error: ' + $What + ' debe ser una ruta del sistema de archivos: ' + (Format-Safe $Path))
    }
    return $full
}

function Get-Sha256Hex([byte[]]$Bytes) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha.ComputeHash($Bytes)
    }
    finally {
        $sha.Dispose()
    }
    $sb = New-Object System.Text.StringBuilder
    foreach ($b in $hash) { [void]$sb.Append($b.ToString('x2')) }
    return $sb.ToString()
}

# Bytes canonicos: cada CRLF pasa a LF (ISO-8859-1: un byte, un caracter). Son los que se escriben.
function ConvertTo-CanonicalBytes([byte[]]$Bytes) {
    $latin1 = [System.Text.Encoding]::GetEncoding(28591)
    $text = $latin1.GetString($Bytes).Replace("`r`n", "`n")
    return , $latin1.GetBytes($text)
}

function Get-CanonicalHash([string]$FilePath) {
    $canon = ConvertTo-CanonicalBytes ([System.IO.File]::ReadAllBytes($FilePath))
    return Get-Sha256Hex $canon
}

# Crea un archivo nuevo (CreateNew: nunca pisa uno existente) y lo vuelca a disco. Si se pasa Flag,
# Flag.Created pasa a $true justo al abrir el archivo: asi el llamador sabe que el archivo es suyo
# (si CreateNew falla porque el nombre ya existia, no es suyo y no debe borrarlo).
function Write-NewFile([string]$Path, [byte[]]$Bytes, [hashtable]$Flag = $null) {
    $fs = New-Object System.IO.FileStream($Path, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    if ($null -ne $Flag) { $Flag.Created = $true }
    try {
        $fs.Write($Bytes, 0, $Bytes.Length)
        $fs.Flush($true)
    }
    finally {
        $fs.Dispose()
    }
}

# Escritura atomica: temporal en la misma carpeta y movimiento sobre el destino. Un archivo
# existente se reemplaza con File.Replace; uno nuevo se mueve (Move falla si ya aparecio otro).
# El temporal propio se borra si algo falla (y solo si lo creamos nosotros); nunca queda un
# destino a medias. Excepcion: si File.Replace falla con ERROR_UNABLE_TO_MOVE_REPLACEMENT_2 (1177,
# el reemplazado pudo quedar con otro nombre) el temporal es la unica copia nueva: no se borra y su
# ruta va en el mensaje.
function Write-Atomic([string]$Dest, [byte[]]$Bytes, [bool]$Existing) {
    $dir = [System.IO.Path]::GetDirectoryName($Dest)
    [void][System.IO.Directory]::CreateDirectory($dir)
    $tmp = Join-Path $dir ('.synclayer-' + [guid]::NewGuid().ToString('N') + '.tmp')
    $flag = @{ Created = $false }
    $keepTmp = $false
    try {
        Write-NewFile $tmp $Bytes $flag
        if ($Existing) {
            try {
                [System.IO.File]::Replace($tmp, $Dest, [NullString]::Value)
            }
            catch {
                $ex = $_.Exception
                while ($null -ne $ex.InnerException) { $ex = $ex.InnerException }
                if (($ex.HResult -band 0xFFFF) -eq 1177) {
                    $keepTmp = $true
                    throw ('no se pudo completar el reemplazo (' + (Get-ErrorText $_) + '). El archivo a reemplazar pudo quedar con otro nombre; la copia nueva esta en ' + (Format-Safe $tmp) + ' y no se borra.')
                }
                throw
            }
        }
        else {
            [System.IO.File]::Move($tmp, $Dest)
        }
    }
    finally {
        if ($flag.Created -and -not $keepTmp -and [System.IO.File]::Exists($tmp)) { [System.IO.File]::Delete($tmp) }
    }
}

# Punto de reanalisis (junction, enlace simbolico, punto de montaje): atributo ReparsePoint del
# elemento mismo, sin seguir el enlace. Lo que no existe no lo es. Cualquier otro error se propaga.
function Test-IsReparse([string]$Path) {
    try {
        $attr = [System.IO.File]::GetAttributes($Path)
    }
    catch {
        $ex = $_.Exception
        while ($null -ne $ex.InnerException) { $ex = $ex.InnerException }
        if (@('FileNotFoundException', 'DirectoryNotFoundException') -contains $ex.GetType().Name) { return $false }
        throw
    }
    return (($attr -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)
}

# Primer punto de reanalisis en Root, en cada carpeta intermedia de Rel o en Rel mismo; $null si no hay.
function Find-Reparse([string]$Root, [string]$Rel) {
    $cur = $Root
    if (Test-IsReparse $cur) { return $cur }
    foreach ($part in $Rel.Split('/')) {
        $cur = Join-Path $cur $part
        if (Test-IsReparse $cur) { return $cur }
    }
    return $null
}

function Get-ReparseText([string]$Path) {
    return ((Format-Safe $Path) + ' es un punto de reanalisis (enlace simbolico, junction o punto de montaje). No se escribe a traves de enlaces.')
}

function Get-ReparseMessage([string]$Path) {
    return ('error: ' + (Get-ReparseText $Path))
}

# Problema para abrir un archivo existente con acceso de escritura sin bloquear a nadie (uso
# compartido o ACL); $null si se puede.
function Get-OpenProblem([string]$Path) {
    try {
        $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::ReadWrite)
        $fs.Dispose()
        return $null
    }
    catch {
        return (Get-ErrorText $_)
    }
}

# Entradas ACE explicitas (no heredadas) que permiten escribir, cambiar permisos o borrar a alguien que
# no sea el usuario actual, SYSTEM, Administradores ni CREATOR OWNER. Devuelve los SID. Es un aviso de
# mejor esfuerzo: si no se puede leer la ACL no se dice nada.
function Get-ForeignWriteAces([string]$Path) {
    $found = New-Object System.Collections.Generic.List[string]
    try {
        if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) { return , $found }
        $acl = Get-Acl -LiteralPath $Path
        $ok = @([System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value, 'S-1-5-18', 'S-1-5-32-544', 'S-1-3-0')
        $mask = [System.Security.AccessControl.FileSystemRights]'WriteData, AppendData, Delete, ChangePermissions, TakeOwnership'
        foreach ($rule in $acl.GetAccessRules($true, $false, [System.Security.Principal.SecurityIdentifier])) {
            if ($rule.AccessControlType -eq [System.Security.AccessControl.AccessControlType]::Allow -and
                (($rule.FileSystemRights -band $mask) -ne 0) -and ($ok -notcontains $rule.IdentityReference.Value)) {
                $found.Add($rule.IdentityReference.Value)
            }
        }
    }
    catch {
        return , (New-Object System.Collections.Generic.List[string])
    }
    return , $found
}

function Test-IsReadOnly([string]$Path) {
    return (([System.IO.File]::GetAttributes($Path) -band [System.IO.FileAttributes]::ReadOnly) -ne 0)
}

function ConvertTo-LocalPath([string]$Root, [string]$Relative) {
    return Join-Path $Root $Relative.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
}

# Lee y valida un manifiesto. Devuelve @{ Order = lista de rutas; Hashes = ruta -> hash }.
# Lanza una excepcion con un mensaje claro si algo no cumple.
function Read-Manifest([string]$FilePath) {
    $bytes = [System.IO.File]::ReadAllBytes($FilePath)
    $text = (New-Object System.Text.UTF8Encoding($false)).GetString($bytes).TrimStart([char]0xFEFF)
    try {
        $m = $text | ConvertFrom-Json
    }
    catch {
        throw 'JSON invalido (no se puede interpretar el archivo)'
    }
    $schema = Get-Prop $m 'schema'
    if (-not (($schema -is [int] -or $schema -is [long]) -and $schema -eq 1)) {
        throw 'schema debe ser 1'
    }
    if (-not (Test-OrdinalEqual (Get-Prop $m 'algorithm') 'sha256')) {
        throw 'algorithm debe ser sha256'
    }
    $entries = Get-ManifestEntries $m
    return @{ Order = $entries.Order; Hashes = $entries.Hashes }
}

# Valida la lista files de un manifiesto o de un estado (rutas de la lista permitida, sin duplicados,
# sha256 de 64 hex en minuscula). Devuelve @{ Order; Hashes; Files }. Lanza si algo no cumple.
function Get-ManifestEntries($m) {
    $filesProp = Get-PropRaw $m 'files'
    if ($null -eq $filesProp) { throw 'falta la lista files' }
    $files = $filesProp.Value
    if (-not ($files -is [object[]])) { throw 'files debe ser una lista' }
    if ($files.Count -eq 0) { throw 'la lista files esta vacia' }
    $order = New-Object System.Collections.Generic.List[string]
    $hashes = @{}
    foreach ($entry in $files) {
        $path = Get-Prop $entry 'path'
        $hash = Get-Prop $entry 'sha256'
        if (-not ($path -is [string])) { throw 'una entrada de files no tiene path de texto' }
        if ($path.Contains('..') -or $path.Contains('\') -or $path.Contains(':') -or $path.StartsWith('/')) {
            throw ('ruta no permitida (absoluta, con .., \ o :): ' + (Format-SafeShort $path))
        }
        if ($path -cnotmatch $AllowedPattern) {
            throw ('ruta fuera de la lista permitida: ' + (Format-SafeShort $path))
        }
        if ($hashes.ContainsKey($path)) { throw ('ruta duplicada: ' + (Format-Safe $path)) }
        if (-not ($hash -is [string]) -or $hash -cnotmatch '^[0-9a-f]{64}\z') {
            throw ('sha256 invalido para ' + (Format-Safe $path))
        }
        $hashes[$path] = $hash
        $order.Add($path)
    }
    return @{ Order = $order; Hashes = $hashes; Files = $files }
}

# $true si el texto contiene __type (busqueda ordinal), tambien escrito con escapes de la forma backslash-u y
# cuatro hex ya resueltos. Lo usan Read-State y Read-LevelConfig.
function Test-TextHasTypeKey([string]$Text) {
    $unescaped = [regex]::Replace($Text, '\\u([0-9a-fA-F]{4})', [System.Text.RegularExpressions.MatchEvaluator]{
        param($hit)
        return [string][char][System.Convert]::ToInt32($hit.Groups[1].Value, 16)
    })
    return ($unescaped.IndexOf('__type', [System.StringComparison]::Ordinal) -ge 0)
}

# Lee y valida el estado previo (<Target>/synclayer-manifest.json), que es entrada no confiable.
# Esquema 1 (instalador de la Fase 1, copia del manifiesto): written = sha256 y level = 5 por archivo,
# porque aquel instalador escribia los bytes canonicos del origen. Esquema 2: ademas written (hash de
# lo escrito, 64 hex minuscula) y level (entero de 1 a 5) por archivo, con claves de lista cerrada.
# Cualquier otro schema, un JSON ilegible o un campo invalido lanza: el llamador lo trata como ausente
# (nunca como ACTUALIZAR). Devuelve @{ Order; Hashes; Written; Levels; Bytes }. Levels da el nivel anterior
# (linea Nivel anterior:); no interviene en la clasificacion.
function Read-State([string]$FilePath) {
    # Lectura unica con tope sobre lo leido (no sobre una medida previa): se abre una vez, en solo lectura, y se
    # leen como maximo $StateMaxBytes mas uno. Mismo patron que Read-LevelConfig.
    try {
        $fs = [System.IO.File]::Open($FilePath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
    }
    catch {
        throw 'no se pudo abrir el archivo'
    }
    $buf = New-Object byte[] ($StateMaxBytes + 1)
    $count = 0
    try {
        while ($count -lt $buf.Length) {
            $got = $fs.Read($buf, $count, $buf.Length - $count)
            if ($got -le 0) { break }
            $count += $got
        }
    }
    catch {
        throw 'no se pudo leer el archivo'
    }
    finally {
        $fs.Dispose()
    }
    if ($count -gt $StateMaxBytes) { throw ('supera ' + $StateMaxBytes + ' bytes') }
    $bytes = New-Object byte[] $count
    [System.Array]::Copy($buf, $bytes, $count)
    $text = (New-Object System.Text.UTF8Encoding($false)).GetString($bytes).TrimStart([char]0xFEFF)
    # Mismo rechazo de __type que en la configuracion: el ConvertFrom-Json de 5.1 descarta esa clave antes de la
    # lista cerrada. Un estado legitimo (esquema 1 o 2) nunca la contiene.
    if (Test-TextHasTypeKey $text) { throw 'clave desconocida: __type' }
    try {
        $m = $text | ConvertFrom-Json
    }
    catch {
        throw 'JSON invalido (no se puede interpretar el archivo)'
    }
    $schema = Get-Prop $m 'schema'
    if (-not ($schema -is [int] -or $schema -is [long])) { throw 'schema no reconocido' }
    if ($schema -ne 1 -and $schema -ne 2) { throw 'schema no reconocido' }
    if (-not (Test-OrdinalEqual (Get-Prop $m 'algorithm') 'sha256')) {
        throw 'algorithm debe ser sha256'
    }
    $entries = Get-ManifestEntries $m
    $written = @{}
    $levels = @{}
    # Claves de lista cerrada en la raiz (los dos esquemas) y, en el esquema 1, tambien por entrada.
    foreach ($p in $m.PSObject.Properties) {
        if (-not (Test-OrdinalIn @('schema', 'algorithm', 'eol', 'files') $p.Name)) {
            throw ('clave desconocida: ' + (Format-SafeShort $p.Name))
        }
    }
    if ($schema -eq 1) {
        foreach ($entry in $entries.Files) {
            foreach ($p in $entry.PSObject.Properties) {
                if (-not (Test-OrdinalIn @('path', 'sha256') $p.Name)) {
                    throw ('clave desconocida en una entrada: ' + (Format-SafeShort $p.Name))
                }
            }
        }
        foreach ($rel in $entries.Order) {
            $written[$rel] = $entries.Hashes[$rel]
            $levels[$rel] = 5
        }
    }
    else {
        if (-not (Test-OrdinalEqual (Get-Prop $m 'eol') 'lf')) { throw 'eol debe ser lf' }
        foreach ($entry in $entries.Files) {
            foreach ($p in $entry.PSObject.Properties) {
                if (-not (Test-OrdinalIn @('path', 'sha256', 'written', 'level') $p.Name)) {
                    throw ('clave desconocida en una entrada: ' + (Format-SafeShort $p.Name))
                }
            }
            $rel = [string](Get-Prop $entry 'path')
            $w = Get-Prop $entry 'written'
            $lv = Get-Prop $entry 'level'
            if (-not ($w -is [string]) -or $w -cnotmatch '^[0-9a-f]{64}\z') {
                throw ('written invalido para ' + (Format-Safe $rel))
            }
            if (-not (($lv -is [int] -or $lv -is [long]) -and $lv -ge 1 -and $lv -le 5)) {
                throw ('level invalido para ' + (Format-Safe $rel))
            }
            $written[$rel] = $w
            $levels[$rel] = [int]$lv
        }
    }
    return @{ Order = $entries.Order; Hashes = $entries.Hashes; Written = $written; Levels = $levels; Bytes = $bytes }
}

# Texto no confiable para un mensaje: recortado a 40 caracteres y escapado (Format-Safe).
function Format-SafeShort([string]$Text) {
    if ($Text.Length -gt 40) { $Text = $Text.Substring(0, 40) + '...' }
    return Format-Safe $Text
}

# Lee y valida <Target>/synclayer-config.json (entrada no confiable) y devuelve el nivel (entero de 1 a 5;
# un objeto vacio es el nivel 5). Lectura unica: se abre una vez (solo lectura) y se leen como maximo
# $ConfigMaxBytes mas uno, asi el tope vale sobre lo leido y no sobre una medida previa. UTF-8 estricto, con
# o sin BOM. Raiz: un objeto. Claves: lista cerrada (solo level), comparadas de forma ordinal. level: entero
# de 1 a 5 (ni texto, ni decimal, ni bool, ni null). Lanza un motivo fijo y escapado: nunca el contenido del
# archivo ni el texto de .NET. El llamador comprueba antes que no sea carpeta ni punto de reanalisis.
function Read-LevelConfig([string]$FilePath) {
    try {
        $fs = [System.IO.File]::Open($FilePath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
    }
    catch {
        throw 'no se pudo abrir el archivo (bloqueado, sin permiso o desaparecio)'
    }
    $buf = New-Object byte[] ($ConfigMaxBytes + 1)
    $count = 0
    try {
        while ($count -lt $buf.Length) {
            $got = $fs.Read($buf, $count, $buf.Length - $count)
            if ($got -le 0) { break }
            $count += $got
        }
    }
    catch {
        throw 'no se pudo leer el archivo'
    }
    finally {
        $fs.Dispose()
    }
    if ($count -gt $ConfigMaxBytes) { throw ('supera ' + $ConfigMaxBytes + ' bytes') }
    $bytes = New-Object byte[] $count
    [System.Array]::Copy($buf, $bytes, $count)
    try {
        $text = (New-Object System.Text.UTF8Encoding($false, $true)).GetString($bytes)
    }
    catch {
        throw 'JSON invalido (no es UTF-8)'
    }
    if ($text.Length -gt 0 -and [int]$text[0] -eq 0xFEFF) { $text = $text.Substring(1) }
    if ([string]::IsNullOrWhiteSpace($text)) { throw 'JSON invalido (archivo vacio)' }
    # El ConvertFrom-Json de 5.1 (JavaScriptSerializer) descarta en silencio la clave __type, tambien escrita
    # con escapes de la forma backslash-u y cuatro hex, antes de que se pueda comprobar la lista cerrada de
    # claves. Un archivo valido solo tiene la clave level: cualquier aparicion de __type (comparacion ordinal,
    # con esos escapes ya resueltos) se rechaza.
    if (Test-TextHasTypeKey $text) {
        throw 'clave desconocida: __type (el instalador puede ser anterior al archivo)'
    }
    try {
        $m = $text | ConvertFrom-Json
    }
    catch {
        throw 'JSON invalido'
    }
    # ConvertFrom-Json de 5.1 desenrolla una lista de un elemento: la raiz debe empezar por llave.
    if (-not ($text.TrimStart().StartsWith('{', [System.StringComparison]::Ordinal)) -or -not ($m -is [System.Management.Automation.PSCustomObject])) {
        throw 'debe ser un objeto'
    }
    foreach ($p in $m.PSObject.Properties) {
        if (-not (Test-OrdinalEqual $p.Name 'level')) {
            throw ('clave desconocida: ' + (Format-SafeShort $p.Name) + ' (el instalador puede ser anterior al archivo)')
        }
    }
    $levelProp = Get-PropRaw $m 'level'
    if ($null -eq $levelProp) { return 5 }
    $lv = $levelProp.Value
    if (-not (($lv -is [int] -or $lv -is [long]) -and $lv -ge 1 -and $lv -le 5)) {
        throw 'level debe ser un entero de 1 a 5'
    }
    return [int]$lv
}

# Bytes del estado con esquema 2: ASCII, LF, sangria de dos espacios y salto final. Coinciden byte a
# byte con json.dumps(obj, indent=2, ensure_ascii=True) + LF de Python con este orden de claves
# (ConvertTo-Json de 5.1 da otro formato). Las rutas son [a-z0-9_/.-] por AllowedPattern: no se escapa nada.
# Funcion pura de manifiesto, hashes escritos y nivel: reinstalar sin cambios no reescribe el estado.
function ConvertTo-StateBytes($Manifest, [hashtable]$OutHashes, [int]$Level) {
    $lf = "`n"
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append('{' + $lf)
    [void]$sb.Append('  "schema": 2,' + $lf)
    [void]$sb.Append('  "algorithm": "sha256",' + $lf)
    [void]$sb.Append('  "eol": "lf",' + $lf)
    [void]$sb.Append('  "files": [' + $lf)
    $last = $Manifest.Order.Count - 1
    for ($i = 0; $i -le $last; $i++) {
        $rel = $Manifest.Order[$i]
        [void]$sb.Append('    {' + $lf)
        [void]$sb.Append('      "path": "' + $rel + '",' + $lf)
        [void]$sb.Append('      "sha256": "' + $Manifest.Hashes[$rel] + '",' + $lf)
        [void]$sb.Append('      "written": "' + $OutHashes[$rel] + '",' + $lf)
        [void]$sb.Append('      "level": ' + $Level.ToString([System.Globalization.CultureInfo]::InvariantCulture) + $lf)
        if ($i -lt $last) { [void]$sb.Append('    },' + $lf) } else { [void]$sb.Append('    }' + $lf) }
    }
    [void]$sb.Append('  ]' + $lf)
    [void]$sb.Append('}' + $lf)
    return , [System.Text.Encoding]::ASCII.GetBytes($sb.ToString())
}

# Celda (modelo, esfuerzo) de $LevelRows para un nivel de 1 a 4 y un agente de $LevelAgents. Lanza si no
# esta (la tabla ya se valido al arrancar: no deberia pasar).
function Get-LevelCell([int]$Level, [string]$Agent) {
    foreach ($row in $LevelRows) {
        $parts = ([string]$row).Split('|')
        if ((Test-OrdinalEqual $parts[0] ([string]$Level)) -and (Test-OrdinalEqual $parts[1] $Agent)) {
            return @{ Model = $parts[2]; Effort = $parts[3] }
        }
    }
    throw 'no hay celda en la tabla de niveles'
}

# Renderizado del frontmatter (Fase 3, 3.3 del plan): funcion PURA, sin E/S. Entrada: los bytes canonicos
# de un agente ya verificados contra el manifiesto (Paso 2) y una celda de $LevelRows. Salida: los bytes a
# escribir. Solo toca la linea model: y la linea effort: del frontmatter (columna 0, comparacion ordinal);
# todo lo demas pasa igual. Un effort de - no toca el esfuerzo (una effort: del origen se conserva). Lanza
# (falla cerrada) ante cualquiera de estas anomalias, todas sobre un origen que el manifiesto da por bueno:
#  - modelo o esfuerzo fuera de las listas cerradas;
#  - primera linea distinta de tres guiones, o frontmatter sin cierre (el cierre es la primera linea de tres
#    guiones exactos);
#  - regla 1: algun caracter del frontmatter fuera de ASCII imprimible (0x20 a 0x7E);
#  - regla 2: alguna linea sin sangria que no tiene la forma clave: seguida de espacio o de fin de linea (esto
#    cubre las lineas de tres guiones con texto o con espacios, las lineas de tres puntos y las claves raras);
#  - regla 3: algun valor de primer nivel que empieza por un indicador YAML (comillas, corchete, llave, barra,
#    mayor, ampersand, asterisco, exclamacion, porcentaje, arroba, acento grave);
#  - model: ausente, repetido o sin la forma simple (letras, digitos, punto, guion), y effort: repetido o sin
#    la forma simple (letras minusculas);
#  - la linea siguiente a model: o a effort: no es el cierre ni empieza por una letra (continuacion);
#  - alguna linea con sangria entre la linea 1 y la mayor de model: y effort: (hueco envolvente);
#  - autocomprobacion del resultado: mismo cierre, una sola linea model:, effort: solo si la celda lo pide,
#    todas las demas lineas identicas, y ninguna clave de primer nivel repetida o distinta.
# La proteccion del bloque hooks: son las reglas de forma, la comparacion linea a linea y el rechazo de
# claves repetidas; la comparacion de conjuntos de claves es defensa en profundidad.
function ConvertTo-LevelBytes([byte[]]$Canon, [string]$Model, [string]$Effort) {
    if (-not (Test-OrdinalIn $AllowedModels $Model)) { throw 'modelo fuera de la lista cerrada' }
    if (-not (Test-OrdinalIn $AllowedEfforts $Effort)) { throw 'esfuerzo fuera de la lista cerrada' }
    $ord = [System.StringComparison]::Ordinal
    $latin1 = [System.Text.Encoding]::GetEncoding(28591)
    $lines = $latin1.GetString($Canon).Split([char]10)
    if ($lines.Count -lt 2 -or -not [string]::Equals($lines[0], '---', $ord)) { throw 'la primera linea no es ---' }
    $close = -1
    for ($i = 1; $i -lt $lines.Count; $i++) {
        if ([string]::Equals($lines[$i], '---', $ord)) { $close = $i; break }
    }
    if ($close -lt 0) { throw 'frontmatter sin cierre' }
    # Falla cerrada ante un origen que el manifiesto no distingue de uno honesto (las tres reglas miran solo las
    # lineas entre los dos ---). Regla 1: nada fuera de 0x20 a 0x7E (sin retorno de carro, tabulador, NEL, U+2028,
    # NBSP, BOM interior...); el texto se decodifica en ISO-8859-1, asi que cualquier byte alto es un caracter alto.
    for ($i = 1; $i -lt $close; $i++) {
        if ($lines[$i] -cmatch '[^\x20-\x7e]') {
            throw 'el frontmatter tiene un caracter fuera de ASCII imprimible (retorno de carro, tabulador, NEL u otro)'
        }
    }
    # Regla 2: toda linea sin sangria tiene la forma clave: seguida de espacio o de fin de linea (rechaza
    # hooks : x, claves con comillas, listas con guion, llaves, lineas --- con texto y lineas ...). Las lineas con
    # sangria siguen siendo parte del bloque de la clave anterior.
    for ($i = 1; $i -lt $close; $i++) {
        if (-not $lines[$i].StartsWith(' ', $ord) -and $lines[$i] -cnotmatch '^[A-Za-z][A-Za-z0-9_-]{0,}:( |\z)') {
            throw 'una linea del primer nivel del frontmatter no tiene la forma clave: valor'
        }
    }
    # Regla 3: ningun valor de primer nivel empieza por un indicador YAML (comillas, corchete, llave, barra, mayor,
    # ampersand, asterisco, exclamacion, porcentaje, arroba o acento grave). El caracter de asterisco no se escribe
    # literal en este archivo: se construye con [char]42.
    $indicators = '"''\[{|>&' + [string][char]42 + '!%@`'
    $indicatorPattern = '^[A-Za-z][A-Za-z0-9_-]{0,}: {1,}[' + $indicators + ']'
    for ($i = 1; $i -lt $close; $i++) {
        if ($lines[$i] -cmatch $indicatorPattern) {
            throw 'un valor de primer nivel del frontmatter empieza por un indicador YAML'
        }
    }
    $modelIdx = New-Object System.Collections.Generic.List[int]
    $effortIdx = New-Object System.Collections.Generic.List[int]
    for ($i = 1; $i -lt $close; $i++) {
        if ($lines[$i].StartsWith('model:', $ord)) { $modelIdx.Add($i) }
        if ($lines[$i].StartsWith('effort:', $ord)) { $effortIdx.Add($i) }
    }
    if ($modelIdx.Count -ne 1) { throw 'debe haber exactamente una linea model: en el frontmatter' }
    if ($effortIdx.Count -gt 1) { throw 'hay mas de una linea effort: en el frontmatter' }
    # Forma simple de las dos lineas (sin comentario, comillas, anclas, bloques ni valor vacio) y sin
    # continuacion en la linea siguiente: asi sustituir una sola linea no deja texto suelto de un valor YAML.
    if ($lines[$modelIdx[0]] -cnotmatch '^model: [A-Za-z0-9][A-Za-z0-9._-]{0,}\z') {
        throw 'la linea model: del origen no tiene la forma esperada'
    }
    if ($effortIdx.Count -eq 1 -and $lines[$effortIdx[0]] -cnotmatch '^effort: [a-z]+\z') {
        throw 'la linea effort: del origen no tiene la forma esperada'
    }
    $nextChecks = New-Object System.Collections.Generic.List[int]
    $nextChecks.Add($modelIdx[0])
    if ($effortIdx.Count -eq 1) { $nextChecks.Add($effortIdx[0]) }
    foreach ($ix in $nextChecks) {
        $nextLine = $lines[$ix + 1]
        if (-not ([string]::Equals($nextLine, '---', $ord) -or $nextLine -cmatch '^[A-Za-z]')) {
            throw 'una linea model: o effort: del origen tiene continuacion en la linea siguiente'
        }
    }
    # Hueco envolvente: una linea con sangria antes de model: o de effort: (desde la 1 hasta la mayor de las dos)
    # podria ser la continuacion de un valor abierto (comilla, corchete, llave) que esa linea cierra, y sustituirla
    # dejaria YAML distinto. Se rechaza cualquier sangria ahi; despues de ambas se permite (el bloque hooks: va despues).
    $lastKey = $modelIdx[0]
    if ($effortIdx.Count -eq 1 -and $effortIdx[0] -gt $lastKey) { $lastKey = $effortIdx[0] }
    for ($i = 1; $i -lt $lastKey; $i++) {
        if ($lines[$i].StartsWith(' ', $ord)) {
            throw 'hay una linea con sangria antes de la linea model: o effort: del frontmatter'
        }
    }
    $out = New-Object System.Collections.Generic.List[string]
    $out.AddRange([string[]]$lines)
    $mi = $modelIdx[0]
    $out[$mi] = 'model: ' + $Model
    $inserted = $false
    if (-not (Test-OrdinalEqual $Effort '-')) {
        if ($effortIdx.Count -eq 1) {
            $out[$effortIdx[0]] = 'effort: ' + $Effort
        }
        else {
            $out.Insert($mi + 1, 'effort: ' + $Effort)
            $inserted = $true
        }
    }
    $result = $latin1.GetBytes([string]::Join([string][char]10, $out.ToArray()))

    # Autocomprobacion: se vuelve a leer el resultado y se compara con la entrada.
    $chk = $latin1.GetString($result).Split([char]10)
    if (-not [string]::Equals($chk[0], '---', $ord)) { throw 'autocomprobacion: cambio la primera linea' }
    $chkClose = -1
    for ($i = 1; $i -lt $chk.Count; $i++) {
        if ([string]::Equals($chk[$i], '---', $ord)) { $chkClose = $i; break }
    }
    $expectClose = $close
    if ($inserted) { $expectClose = $close + 1 }
    if ($chkClose -ne $expectClose) { throw 'autocomprobacion: cambio el cierre del frontmatter' }
    $chkModel = New-Object System.Collections.Generic.List[int]
    $chkEffort = New-Object System.Collections.Generic.List[int]
    for ($i = 1; $i -lt $chkClose; $i++) {
        if ($chk[$i].StartsWith('model:', $ord)) { $chkModel.Add($i) }
        if ($chk[$i].StartsWith('effort:', $ord)) { $chkEffort.Add($i) }
    }
    if ($chkModel.Count -ne 1 -or -not [string]::Equals($chk[$chkModel[0]], ('model: ' + $Model), $ord)) {
        throw 'autocomprobacion: la linea model: no es la esperada'
    }
    if (Test-OrdinalEqual $Effort '-') {
        if ($chkEffort.Count -ne $effortIdx.Count) { throw 'autocomprobacion: cambio la cantidad de lineas effort:' }
        if ($effortIdx.Count -eq 1 -and -not [string]::Equals($chk[$chkEffort[0]], $lines[$effortIdx[0]], $ord)) {
            throw 'autocomprobacion: cambio la linea effort: del origen'
        }
    }
    elseif ($chkEffort.Count -ne 1 -or -not [string]::Equals($chk[$chkEffort[0]], ('effort: ' + $Effort), $ord)) {
        throw 'autocomprobacion: la linea effort: no es la esperada'
    }
    $restIn = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($i -ne $mi -and -not $effortIdx.Contains($i)) { $restIn.Add($lines[$i]) }
    }
    $restOut = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $chk.Count; $i++) {
        if ($i -ne $chkModel[0] -and -not $chkEffort.Contains($i)) { $restOut.Add($chk[$i]) }
    }
    if ($restIn.Count -ne $restOut.Count) { throw 'autocomprobacion: cambio la cantidad de lineas' }
    for ($i = 0; $i -lt $restIn.Count; $i++) {
        if (-not [string]::Equals($restIn[$i], $restOut[$i], $ord)) { throw 'autocomprobacion: cambio una linea distinta de model: y effort:' }
    }
    # Estructural: ninguna clave de primer nivel se repite en la salida (esto si frena un segundo hooks:). La
    # igualdad del conjunto de claves con el de la entrada mas, como mucho, effort es REDUNDANTE con las reglas de
    # forma y la comparacion linea a linea de arriba: se deja como defensa en profundidad, no como la proteccion
    # de hooks:.
    $keyPattern = '^([A-Za-z_][A-Za-z0-9_-]{0,}):'
    $keysIn = New-Object System.Collections.Generic.HashSet[string]
    for ($i = 1; $i -lt $close; $i++) {
        $km = [regex]::Match($lines[$i], $keyPattern)
        if ($km.Success) { [void]$keysIn.Add($km.Groups[1].Value) }
    }
    if (-not (Test-OrdinalEqual $Effort '-')) { [void]$keysIn.Add('effort') }
    $keysOut = New-Object System.Collections.Generic.HashSet[string]
    for ($i = 1; $i -lt $chkClose; $i++) {
        $km = [regex]::Match($chk[$i], $keyPattern)
        if ($km.Success -and -not $keysOut.Add($km.Groups[1].Value)) {
            throw 'autocomprobacion: clave de primer nivel repetida en la salida'
        }
    }
    if (-not $keysOut.SetEquals($keysIn)) { throw 'autocomprobacion: cambio el conjunto de claves de primer nivel' }
    return , $result
}

try {
    $Source = $PSScriptRoot
    if ([string]::IsNullOrEmpty($Source)) {
        Stop-Install 1 'error: no se pudo determinar la carpeta del script. Ejecuta install.ps1 con -File.'
    }
    if ([string]::IsNullOrWhiteSpace($Target)) {
        Stop-Install 1 'error: -Target no puede estar vacio.'
    }
    $TargetFull = Resolve-FsPath $Target '-Target'
    # Ni -Target ni ninguna carpeta que lo contenga puede ser un archivo (-DryRun y la real coinciden).
    $walk = $TargetFull
    while (-not [string]::IsNullOrEmpty($walk)) {
        if ([System.IO.File]::Exists($walk)) {
            Stop-Install 1 ('error: -Target o una carpeta que lo contiene es un archivo: ' + (Format-Safe $walk))
        }
        $walk = [System.IO.Path]::GetDirectoryName($walk)
    }
    if ([string]::IsNullOrWhiteSpace($BackupDir)) {
        # Respaldo por defecto: hermano del destino (<Target>-backup-<fecha>). Si -Target es la raiz de
        # una unidad no hay hermano posible ("C:-backup-..." seria relativo a la unidad): se rechaza y
        # se pide -BackupDir explicito, en lugar de elegir en silencio otra ubicacion como %TEMP%.
        $trimmed = $TargetFull.TrimEnd('\', '/')
        $rootTrimmed = [System.IO.Path]::GetPathRoot($TargetFull).TrimEnd('\', '/')
        if ($trimmed -eq $rootTrimmed) {
            Stop-Install 1 'error: -Target es la raiz de una unidad; indica -BackupDir para el respaldo.'
        }
        $BackupFull = $trimmed + '-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    }
    else {
        $BackupFull = Resolve-FsPath $BackupDir '-BackupDir'
    }

    # El respaldo no puede estar dentro del destino (ni ser el destino): Claude Code podria cargar
    # agentes de subcarpetas de ~/.claude. Prefijo con separador: destino-x no esta dentro de destino.
    $targetPrefix = $TargetFull.TrimEnd('\', '/') + '\'
    $backupPrefix = $BackupFull.TrimEnd('\', '/') + '\'
    if ($backupPrefix.StartsWith($targetPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        Stop-Install 1 ('error: -BackupDir no puede estar dentro de -Target (ni ser -Target): ' + (Format-Safe $BackupFull))
    }

    # Validacion de la tabla de niveles: antes de leer el origen y sin escribir nada.
    $levelProblem = Get-LevelTableProblem
    if ($null -ne $levelProblem) {
        Stop-Install 1 ('error: la tabla de niveles de install.ps1 no es valida: ' + $levelProblem + '. No se escribio nada.')
    }

    # Paso 1: cargar y validar el manifiesto.
    $manifestPath = Join-Path $Source $ManifestName
    if (-not [System.IO.File]::Exists($manifestPath)) {
        Stop-Install 1 ('error: falta ' + $ManifestName + ' junto a install.ps1.')
    }
    try {
        $manifest = Read-Manifest $manifestPath
    }
    catch {
        Stop-Install 1 ('error: ' + $ManifestName + ' no es valido: ' + (Get-ErrorText $_))
    }

    # Paso 2: verificar el origen. No se escribe nada.
    # Se lee cada archivo UNA vez: los bytes canonicos verificados aqui son los que se escriben (no se
    # vuelve a leer el origen entre verificar y copiar).
    $bad = New-Object System.Collections.Generic.List[string]
    $canonSrc = @{}
    foreach ($rel in $manifest.Order) {
        $src = ConvertTo-LocalPath $Source $rel
        if (-not [System.IO.File]::Exists($src)) {
            $bad.Add($rel + ' (falta en el origen)')
        }
        else {
            $canon = ConvertTo-CanonicalBytes ([System.IO.File]::ReadAllBytes($src))
            if ((Get-Sha256Hex $canon) -cne $manifest.Hashes[$rel]) {
                $bad.Add($rel + ' (el hash no coincide con el manifiesto)')
            }
            else {
                $canonSrc[$rel] = $canon
            }
        }
    }
    if ($bad.Count -gt 0) {
        Stop-Install 2 ("error: el origen no coincide con " + $ManifestName + ":`n  " + ($bad -join "`n  ") +
            "`nRevisa con git status / git diff que cambio y restaura el archivo o vuelve a clonar el commit revisado." +
            "`nSi eres mantenedor y el cambio es intencional, regenera el manifiesto con: python -B tools/build_manifest.py")
    }

    # Configuracion: leer y validar <Target>/synclayer-config.json (solo lectura; nunca se escribe, respalda,
    # clasifica ni borra). Ausente: nivel 5. Carpeta, punto de reanalisis, ilegible o invalido: exit 1 antes
    # de escribir nada, tambien en -DryRun. El punto de reanalisis se vuelve a comprobar tras leer.
    $configPath = Join-Path $TargetFull $ConfigName
    $level = 5
    $levelFromFile = $false
    $badLink = Find-Reparse $TargetFull $ConfigName
    if ($null -ne $badLink) { Stop-Install 1 ((Get-ReparseMessage $badLink) + ' No se escribio nada.') }
    if ([System.IO.Directory]::Exists($configPath)) {
        Stop-Install 1 ('error: ' + $ConfigName + ' no es valido: es una carpeta, no un archivo. No se escribio nada.')
    }
    if ([System.IO.File]::Exists($configPath)) {
        try {
            $level = [int](Read-LevelConfig $configPath)
        }
        catch {
            Stop-Install 1 ('error: ' + $ConfigName + ' no es valido: ' + (Get-ErrorText $_) + '. No se escribio nada.')
        }
        $badLink = Find-Reparse $TargetFull $ConfigName
        if ($null -ne $badLink) { Stop-Install 1 ((Get-ReparseMessage $badLink) + ' No se escribio nada.') }
        $levelFromFile = $true
    }
    # Avisos de entorno (T6): con el nivel 1 a 4, dos variables anulan el model: y el effort: de los agentes
    # y el nivel no lo puede lograr. Solo lectura (GetEnvironmentVariable): el instalador no define, cambia ni
    # borra variables, y NUNCA imprime el valor, solo el nombre y un texto fijo. Salen por stderr, antes del
    # bloque Nivel y de la salida de -DryRun (asi se ven tambien en -DryRun), sin cambiar el codigo de
    # salida. Con el nivel 5 no hay aviso: quien no configuro nada no ve una linea nueva.
    if ($level -ne 5) {
        if (-not [string]::IsNullOrEmpty([System.Environment]::GetEnvironmentVariable('CLAUDE_CODE_SUBAGENT_MODEL_FORCE'))) {
            Write-Err ('aviso: CLAUDE_CODE_SUBAGENT_MODEL_FORCE esta definida: Claude Code ignora el model: de los agentes y el nivel ' + $level + ' no cambia el modelo.')
        }
        if (-not [string]::IsNullOrEmpty([System.Environment]::GetEnvironmentVariable('CLAUDE_CODE_EFFORT_LEVEL'))) {
            Write-Err 'aviso: CLAUDE_CODE_EFFORT_LEVEL esta definida: tiene prioridad sobre el effort: de los agentes.'
        }
    }

    # Nivel: bytes a escribir por archivo. Con el nivel 5 (el repositorio) son los bytes canonicos del origen
    # y NO se llama al renderizado. Con el nivel 1 a 4, los seis agentes de $LevelAgents que esten en el
    # manifiesto pasan por ConvertTo-LevelBytes con su celda de $LevelRows; el resto (auditor, shield,
    # debugger, el hook, las reglas, la guia) queda en los bytes del origen. Un error de renderizado es un
    # defecto del origen que el manifiesto no detecta: exit 1 antes de escribir, tambien en -DryRun.
    # $outHash (hash de $outBytes) es lo que clasifica, verifica y se guarda en el estado como written.
    # Con el nivel 5 los mensajes de verificacion dicen lo de siempre (el manifiesto): quien no configura
    # nada ve la misma salida que antes, salvo la linea Nivel:. Con el nivel 1 a 4 el hash esperado ya no es el del manifiesto.
    $verifyWhat = 'el manifiesto'
    if ($level -ne 5) { $verifyWhat = 'lo esperado para el nivel ' + $level }
    $outBytes = @{}
    $outHash = @{}
    $adjustLines = New-Object System.Collections.Generic.List[string]
    foreach ($rel in $manifest.Order) {
        $bytesOut = $canonSrc[$rel]
        if ($level -ne 5) {
            $agentMatch = [regex]::Match($rel, '^agents/([a-z0-9_-]+)\.md\z')
            if ($agentMatch.Success -and (Test-OrdinalIn $LevelAgents $agentMatch.Groups[1].Value)) {
                try {
                    $cell = Get-LevelCell $level $agentMatch.Groups[1].Value
                    $bytesOut = ConvertTo-LevelBytes $canonSrc[$rel] $cell.Model $cell.Effort
                }
                catch {
                    Stop-Install 1 ('error: no se puede aplicar el nivel ' + $level + ' a ' + $rel + ': ' + (Get-ErrorText $_) + '. No se escribio nada.')
                }
                $adjustLines.Add('Ajuste: ' + $rel + '  model: ' + $cell.Model + '  effort: ' + $cell.Effort)
            }
        }
        $outBytes[$rel] = $bytesOut
        $outHash[$rel] = Get-Sha256Hex $bytesOut
    }

    # Paso 3: estado previo del destino (las pruebas inyectan codigo justo despues de esta linea).
    # Ni -Target ni el estado pueden ser puntos de reanalisis. Un estado ilegible, invalido o de un
    # schema no reconocido se trata como ausente: aviso a stderr, no se hace hash de el ni se respalda,
    # y se reescribe al final. Un estado no reconocido nunca produce ACTUALIZAR.
    $statePath = Join-Path $TargetFull $StateName
    $badLink = Find-Reparse $TargetFull $StateName
    if ($null -ne $badLink) { Stop-Install 1 (Get-ReparseMessage $badLink) }
    if ([System.IO.Directory]::Exists($statePath)) {
        Stop-Install 1 ('error: el estado ' + (Format-Safe $statePath) + ' es una carpeta, no un archivo.')
    }
    $prev = $null
    $stateExists = [System.IO.File]::Exists($statePath)
    $stateDestHash = $null
    if ($stateExists) {
        try {
            $prev = Read-State $statePath
            $stateDestHash = Get-Sha256Hex (ConvertTo-CanonicalBytes $prev.Bytes)
        }
        catch {
            $prev = $null
            $stateDestHash = $null
            Write-Err ('aviso: ' + (Format-Safe $statePath) + ' no se pudo leer o no es valido (' +
                (Get-ErrorText $_) + '). Se trata como ausente: no se respalda.')
        }
    }
    # Nivel de la instalacion previa, solo para informar (linea "Nivel anterior:"): hay estado valido y todas sus
    # entradas dicen el mismo nivel (asi lo escribe este instalador). Un estado ausente, no valido o con niveles
    # mezclados no tiene nivel anterior. No interviene en la clasificacion.
    $prevLevel = $null
    if ($null -ne $prev) {
        $prevLevels = @{}
        foreach ($rel in $prev.Order) { $prevLevels[[string]$prev.Levels[$rel]] = $true }
        if ($prevLevels.Count -eq 1) { $prevLevel = [int]@($prevLevels.Keys)[0] }
    }

    # Paso 4: clasificar.
    $rows = New-Object System.Collections.Generic.List[object]
    $counts = @{ NUEVO = 0; IGUAL = 0; ACTUALIZAR = 0; MODIFICADO = 0; HUERFANO = 0 }
    foreach ($rel in $manifest.Order) {
        $dest = ConvertTo-LocalPath $TargetFull $rel
        $badLink = Find-Reparse $TargetFull $rel
        if ($null -ne $badLink) { Stop-Install 1 (Get-ReparseMessage $badLink) }
        $parts = $rel.Split('/')
        $cur = $TargetFull
        for ($i = 0; $i -lt $parts.Length - 1; $i++) {
            $cur = Join-Path $cur $parts[$i]
            if ([System.IO.File]::Exists($cur)) {
                Stop-Install 1 ('error: ' + (Format-Safe $cur) + ' es un archivo y deberia ser una carpeta.')
            }
        }
        if ([System.IO.Directory]::Exists($dest)) {
            Stop-Install 1 ('error: el destino ' + (Format-Safe $dest) + ' es una carpeta, no un archivo.')
        }
        $destHash = $null
        if (-not [System.IO.File]::Exists($dest)) {
            $state = 'NUEVO'
        }
        else {
            try {
                $destHash = Get-CanonicalHash $dest
            }
            catch {
                Stop-Install 1 ('error: no se pudo leer el destino ' + (Format-Safe $dest) + ' (' + (Get-ErrorText $_) + '). No se escribio nada en el destino.')
            }
            if ($destHash -ceq $outHash[$rel]) {
                $state = 'IGUAL'
            }
            elseif ($null -ne $prev -and $prev.Written.ContainsKey($rel) -and ($prev.Written[$rel] -ceq $destHash)) {
                $state = 'ACTUALIZAR'
            }
            else {
                $state = 'MODIFICADO'
            }
        }
        $counts[$state]++
        $rows.Add(@{ State = $state; Path = $rel; DestHash = $destHash })
    }
    if ($null -ne $prev) {
        foreach ($rel in $prev.Order) {
            if (-not $manifest.Hashes.ContainsKey($rel)) {
                $counts['HUERFANO']++
                $rows.Add(@{ State = 'HUERFANO'; Path = $rel })
            }
        }
    }

    # Que hay que escribir y respaldar. Primero el hook: ningun agente con hooks: puede quedar
    # instalado sin su guarda.
    $hookPath = 'hooks/agent_guard.py'
    $writeRows = New-Object System.Collections.Generic.List[object]
    foreach ($row in $rows) {
        if ($row.Path -ceq $hookPath -and ($row.State -ceq 'NUEVO' -or $row.State -ceq 'ACTUALIZAR' -or $row.State -ceq 'MODIFICADO')) {
            $writeRows.Add($row)
        }
    }
    foreach ($row in $rows) {
        if ($row.Path -cne $hookPath -and ($row.State -ceq 'NUEVO' -or $row.State -ceq 'ACTUALIZAR' -or $row.State -ceq 'MODIFICADO')) {
            $writeRows.Add($row)
        }
    }
    $stateBytes = ConvertTo-StateBytes $manifest $outHash $level
    $stateHash = Get-Sha256Hex $stateBytes
    # Un estado ilegible o invalido deja $stateDestHash en $null: se reescribe y no se respalda.
    $stateNeedsWrite = (-not $stateExists) -or ($stateDestHash -cne $stateHash)

    $backupItems = New-Object System.Collections.Generic.List[object]
    foreach ($row in $writeRows) {
        if ($row.State -ceq 'ACTUALIZAR' -or $row.State -ceq 'MODIFICADO') {
            $backupItems.Add(@{ Rel = $row.Path; From = (ConvertTo-LocalPath $TargetFull $row.Path); Hash = $row.DestHash })
        }
    }
    if ($stateExists -and $null -ne $stateDestHash -and $stateNeedsWrite) {
        $backupItems.Add(@{ Rel = $StateName; From = $statePath; Hash = $stateDestHash })
    }
    # Paso 5: mostrar el plan.
    Write-Out ('Destino: ' + (Format-Safe $TargetFull))
    if ($levelFromFile) {
        Write-Out ('Nivel: ' + $level + ' (' + $ConfigName + ')')
    }
    else {
        Write-Out ('Nivel: ' + $level + ' (por defecto; no hay ' + $ConfigName + ')')
    }
    if ($null -ne $prevLevel -and $prevLevel -ne $level) {
        Write-Out ('Nivel anterior: ' + $prevLevel)
    }
    if ($backupItems.Count -gt 0) { Write-Out ('Respaldo: ' + (Format-Safe $BackupFull)) }
    if ($DryRun) { Write-Out 'Modo: -DryRun (no se escribe nada)' }
    foreach ($row in $rows) {
        Write-Out ($row.State.PadRight(10) + '  ' + $row.Path)
    }
    Write-Out ('Resumen: NUEVO=' + $counts['NUEVO'] + ' IGUAL=' + $counts['IGUAL'] +
        ' ACTUALIZAR=' + $counts['ACTUALIZAR'] + ' MODIFICADO=' + $counts['MODIFICADO'] +
        ' HUERFANO=' + $counts['HUERFANO'])
    foreach ($adjustLine in $adjustLines) { Write-Out $adjustLine }
    if ($counts['HUERFANO'] -gt 0) {
        Write-Out 'nota: los HUERFANO los instalo una version anterior y ya no estan en el manifiesto. No se borran.'
    }

    if ($counts['MODIFICADO'] -gt 0 -and -not $Force) {
        $mod = @($rows | Where-Object { $_.State -eq 'MODIFICADO' } | ForEach-Object { $_.Path })
        Stop-Install 3 ("error: hay cambios locales en el destino (MODIFICADO):`n  " + ($mod -join "`n  ") +
            "`nNo se escribio nada. Opciones: lleva el cambio al repositorio (regla de copia inversa del README)" +
            " o repite con -Force (se respalda lo que se sobrescribe)." +
            "`nSi cambiaste model: o effort: a mano, usa synclayer-config.json.")
    }

    # Destino no escribible: archivo de solo lectura que hay que reemplazar (o el estado). Exit 1 en ambos modos.
    foreach ($row in $writeRows) {
        if ($row.State -cne 'NUEVO') {
            $d = ConvertTo-LocalPath $TargetFull $row.Path
            if (Test-IsReadOnly $d) {
                Stop-Install 1 ('error: el destino ' + (Format-Safe $d) + ' es de solo lectura (no escribible). No se escribio nada.')
            }
        }
    }
    if ($stateExists -and $stateNeedsWrite -and (Test-IsReadOnly $statePath)) {
        Stop-Install 1 ('error: el estado ' + (Format-Safe $statePath) + ' es de solo lectura (no escribible). No se escribio nada.')
    }

    # Archivo o estado a reemplazar bloqueado por otro proceso o sin permiso de escritura (ACL): se
    # detecta ahora, antes de escribir. Exit 1 en ambos modos; el exit 4 queda para fallos al escribir.
    foreach ($row in $writeRows) {
        if ($row.State -cne 'NUEVO') {
            $d = ConvertTo-LocalPath $TargetFull $row.Path
            $problem = Get-OpenProblem $d
            if ($null -ne $problem) {
                Stop-Install 1 ('error: el destino ' + (Format-Safe $d) + ' esta bloqueado o no se puede escribir (' + $problem + '). No se escribio nada.')
            }
        }
    }
    if ($stateExists -and $stateNeedsWrite) {
        $problem = Get-OpenProblem $statePath
        if ($null -ne $problem) {
            Stop-Install 1 ('error: el estado ' + (Format-Safe $statePath) + ' esta bloqueado o no se puede escribir (' + $problem + '). No se escribio nada.')
        }
    }

    # Un respaldo nunca se pisa: si algo ya existe en la ruta de respaldo, exit 1 (tambien en -DryRun).
    if ($backupItems.Count -gt 0) {
        $walkB = $BackupFull
        while (-not [string]::IsNullOrEmpty($walkB)) {
            if ([System.IO.File]::Exists($walkB)) {
                Stop-Install 1 ('error: -BackupDir o una carpeta que lo contiene es un archivo: ' + (Format-Safe $walkB))
            }
            $walkB = [System.IO.Path]::GetDirectoryName($walkB)
        }
        foreach ($item in $backupItems) {
            $badLink = Find-Reparse $BackupFull $item.Rel
            if ($null -ne $badLink) { Stop-Install 1 (Get-ReparseMessage $badLink) }
            $bpath = ConvertTo-LocalPath $BackupFull $item.Rel
            if ([System.IO.File]::Exists($bpath) -or [System.IO.Directory]::Exists($bpath)) {
                Stop-Install 1 ('error: ya existe el respaldo ' + (Format-Safe $bpath) + '. No se pisa; usa otro -BackupDir.')
            }
        }
        # Un respaldo va siempre en una carpeta NUEVA, aunque este vacia: el nombre por defecto lleva
        # fecha y hora y es predecible, y una carpeta ya existente pudo crearla otro con permisos propios.
        if ([System.IO.Directory]::Exists($BackupFull)) {
            Stop-Install 1 ('error: ya existe el respaldo ' + (Format-Safe $BackupFull) + '. El respaldo debe ir en una carpeta nueva; usa otro -BackupDir.')
        }
    }

    if ($DryRun) {
        exit 0
    }

    $written = New-Object System.Collections.Generic.List[string]
    $backupMade = $false

    # Falla la copia, la verificacion o el estado: exit 4, informa y no deshace nada.
    function Stop-CopyFailed([string]$Message) {
        $lines = 'error: ' + $Message
        if ($written.Count -gt 0) {
            $lines += "`nEscrito hasta ahora (no se deshace):`n  " + ($written -join "`n  ")
        }
        else {
            $lines += "`nNo se escribio ningun archivo del destino."
        }
        if ($backupMade) {
            $lines += "`nRespaldo de lo sobrescrito: " + (Format-Safe $BackupFull)
        }
        $lines += "`nNo se actualizo el estado " + $StateName + ". No hay rollback: corrige la causa y repite la instalacion (es segura)."
        Stop-Install 4 $lines
    }

    # Paso 6: respaldar y verificar (las pruebas inyectan codigo justo despues de esta linea).
    # Primero se leen y verifican TODOS los originales; el primer respaldo se crea despues.
    $backupData = New-Object System.Collections.Generic.List[object]
    foreach ($item in $backupItems) {
        try {
            $orig = [System.IO.File]::ReadAllBytes($item.From)
        }
        catch {
            Stop-Install 1 ('error: no se pudo leer ' + (Format-Safe $item.From) + ' para respaldarlo (' + (Get-ErrorText $_) + '). No se escribio nada en el destino.')
        }
        if ((Get-Sha256Hex (ConvertTo-CanonicalBytes $orig)) -cne $item.Hash) {
            Stop-Install 1 ('error: ' + (Format-Safe $item.Rel) + ' cambio en el destino durante la ejecucion. No se escribio nada en el destino; repite.')
        }
        $backupData.Add(@{ Item = $item; Bytes = $orig })
    }
    foreach ($bd in $backupData) {
        $item = $bd.Item
        $orig = $bd.Bytes
        # Se vuelve a comprobar justo antes de escribir: algo pudo convertirse en enlace tras clasificar.
        $badLink = Find-Reparse $BackupFull $item.Rel
        if ($null -ne $badLink) { Stop-Install 1 (Get-ReparseMessage $badLink) }
        # El primer respaldo exige una carpeta nueva (se vuelve a comprobar justo antes de crearla). Un
        # mkdir exclusivo no existe sin P/Invoke: queda una ventana minima, pero CreateNew por archivo
        # impide pisar un respaldo existente.
        if (-not $backupMade -and [System.IO.Directory]::Exists($BackupFull)) {
            Stop-Install 1 ('error: ya existe el respaldo ' + (Format-Safe $BackupFull) + '. El respaldo debe ir en una carpeta nueva; usa otro -BackupDir.')
        }
        # Carpeta de respaldo ya comprobada (las pruebas inyectan una carrera justo despues de esta linea).
        $bpath = ConvertTo-LocalPath $BackupFull $item.Rel
        try {
            [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($bpath))
            $backupMade = $true
            Write-NewFile $bpath $orig
        }
        catch {
            Stop-Install 1 ('error: no se pudo crear el respaldo ' + (Format-Safe $bpath) + ' (' + (Get-ErrorText $_) +
                '). Si ya existia, no se pisa: usa otro -BackupDir. No se escribio nada en el destino.')
        }
        if ((Get-Sha256Hex ([System.IO.File]::ReadAllBytes($bpath))) -cne (Get-Sha256Hex $orig)) {
            Stop-Install 1 ('error: el respaldo de ' + (Format-Safe $item.Rel) + ' no coincide con el original. No se escribio nada en el destino.')
        }
        Write-Out ('Respaldado: ' + $item.Rel)
    }

    # Paso 7: copiar los bytes de salida (las pruebas inyectan codigo justo despues de esta linea).
    # Son los canonicos ya verificados en memoria, o su renderizado por nivel; cada uno se verifica al instante.
    foreach ($row in $writeRows) {
        $rel = $row.Path
        $dest = ConvertTo-LocalPath $TargetFull $rel
        $existing = ($row.State -cne 'NUEVO')
        try {
            # TOCTOU basico: el punto de reanalisis se vuelve a comprobar justo antes de escribir cada archivo.
            $badLink = Find-Reparse $TargetFull $rel
            if ($null -ne $badLink) { throw (Get-ReparseText $badLink) }
            if ($existing -and ((Get-CanonicalHash $dest) -cne $row.DestHash)) {
                throw 'el archivo cambio en el destino despues de clasificarlo'
            }
            # Ultimo punto de escritura (las pruebas inyectan una carrera justo antes de esta linea).
            Write-Atomic $dest $outBytes[$rel] $existing
            $written.Add($rel)
            # La carrera no se cierra: si un enlace aparecio tras la comprobacion, el archivo ya pudo ir
            # fuera. Se detecta y se informa (exit 4); no se deshace.
            $badLink = Find-Reparse $TargetFull $rel
            if ($null -ne $badLink) { throw ((Get-ReparseText $badLink) + ' Aparecio mientras se escribia: el archivo pudo escribirse fuera del destino; revisalo.') }
            Write-Out ('Copiado: ' + $rel)
            if ((Get-CanonicalHash $dest) -cne $outHash[$rel]) {
                throw ('el hash del archivo escrito no coincide con ' + $verifyWhat)
            }
        }
        catch {
            Stop-CopyFailed ('fallo la copia de ' + $rel + ': ' + (Get-ErrorText $_))
        }
    }

    # Paso 8: verificar el destino (las pruebas inyectan fallos justo despues de esta linea).
    $badDest = New-Object System.Collections.Generic.List[string]
    foreach ($rel in $written) {
        $dest = ConvertTo-LocalPath $TargetFull $rel
        try {
            $badLink = Find-Reparse $TargetFull $rel
            if ($null -ne $badLink) {
                $badDest.Add($rel + ' (' + (Get-ReparseText $badLink) + ')')
            }
            elseif ((Get-CanonicalHash $dest) -cne $outHash[$rel]) { $badDest.Add($rel) }
        }
        catch {
            $badDest.Add($rel + ' (no se pudo leer)')
        }
    }
    if ($badDest.Count -gt 0) {
        Stop-CopyFailed ("la verificacion posterior fallo:`n  " + ($badDest -join "`n  "))
    }
    if ($written.Count -gt 0) {
        Write-Out ('Verificado: ' + $written.Count + ' archivo(s) escritos coinciden con ' + $verifyWhat + '.')
    }

    # Paso 9: estado, solo si todo lo anterior paso.
    if ($stateNeedsWrite) {
        try {
            $badLink = Find-Reparse $TargetFull $StateName
            if ($null -ne $badLink) { throw (Get-ReparseText $badLink) }
            # Ultimo punto de escritura del estado (las pruebas inyectan una carrera justo antes de esta linea).
            Write-Atomic $statePath $stateBytes $stateExists
            $badLink = Find-Reparse $TargetFull $StateName
            if ($null -ne $badLink) { throw ((Get-ReparseText $badLink) + ' Aparecio mientras se escribia: el estado pudo escribirse fuera del destino; revisalo.') }
            if ((Get-CanonicalHash $statePath) -cne $stateHash) { throw 'el estado escrito no coincide' }
        }
        catch {
            Stop-CopyFailed ('no se pudo escribir ' + $StateName + ': ' + (Get-ErrorText $_))
        }
        Write-Out ('Estado: ' + $StateName + ' actualizado.')
    }

    # Paso 10: mensaje final.
    Write-Out ('Instalacion terminada: escritos=' + $written.Count + ' IGUAL=' + $counts['IGUAL'] + '.')
    if ($backupMade) {
        Write-Out ('Respaldo de lo sobrescrito: ' + (Format-Safe $BackupFull))
    }
    if ($written.Count -gt 0) {
        Write-Out 'Recordatorio: reinicia las sesiones de Claude Code abiertas; no ven agentes nuevos o modificados.'
        Write-Out 'Recordatorio: este instalador no toca settings.json ni CLAUDE.md; ~/.claude/CLAUDE.md debe apuntar a ~/.claude/rules/agentes.md.'
        Write-Out 'Recordatorio: no hay sincronizacion automatica; repite la instalacion cuando cambien los archivos del repositorio.'
    }
    $defaultTarget = (Join-Path $HOME '.claude').TrimEnd('\', '/')
    if ($TargetFull.TrimEnd('\', '/') -ine $defaultTarget) {
        Write-Err 'aviso: -Target no es ~/.claude y los hooks: de los agentes apuntan a $HOME/.claude/hooks/agent_guard.py.'
    }
    # $HOME del shell que lance el hook: el aviso dice que copia de agent_guard.py correra en cada caso.
    $envHome = [System.Environment]::GetEnvironmentVariable('HOME')
    if (-not [string]::IsNullOrEmpty($envHome)) {
        $envHomeNorm = $envHome.Replace('/', '\').TrimEnd('\')
        $psHomeNorm = ([string]$HOME).Replace('/', '\').TrimEnd('\')
        if ($envHomeNorm -ine $psHomeNorm) {
            Write-Err ('aviso: la variable de entorno HOME (' + (Format-Safe $envHome) + ') difiere de $HOME de PowerShell (' + (Format-Safe ([string]$HOME)) +
                '). Los hooks: de los agentes usan $HOME del shell que los lanza: un shell con HOME=' + (Format-Safe $envHome) +
                ' correra ' + (Format-Safe $envHome) + '/.claude/hooks/agent_guard.py y uno con $HOME=' + (Format-Safe ([string]$HOME)) +
                ' correra ' + (Format-Safe ([string]$HOME)) + '/.claude/hooks/agent_guard.py. Esta instalacion escribio en ' + (Format-Safe $TargetFull) + '.')
        }
    }
    # Quien pueda escribir agent_guard.py cambia lo que corre antes de cada llamada de herramienta.
    $hookDest = ConvertTo-LocalPath $TargetFull $hookPath
    if ([System.IO.File]::Exists($hookDest)) {
        $foreign = Get-ForeignWriteAces $hookDest
        if ($foreign.Count -gt 0) {
            Write-Err ('aviso: ' + (Format-Safe $hookDest) + ' tiene permisos de escritura explicitos para otras cuentas (SID: ' + ($foreign -join ', ') +
                '). Quien lo pueda escribir cambia lo que se ejecuta antes de cada llamada de herramienta. Revisa los permisos con icacls.')
        }
    }
    exit 0
}
catch {
    Write-Err ('error: ' + (Get-ErrorText $_))
    exit 1
}
