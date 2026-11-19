<#
.SYNOPSIS
Instala en ~/.claude los doce archivos de SyncLayer, guiado por install-manifest.json.

.DESCRIPTION
Valida el manifiesto, verifica el origen (hash canonico), lee el estado previo, clasifica cada
archivo y muestra el plan. Sin -DryRun respalda lo que va a sobrescribir (verificado), copia con
el hook primero (temporal en la misma carpeta + movimiento), verifica el destino y escribe el
estado <Target>/synclayer-manifest.json. Nunca borra. No hace rollback: si falla, informa.

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

# Lista permitida: los doce archivos que SyncLayer instala. Misma lista que ALLOWED de
# tools/build_manifest.py, pero con \z: en .NET \Z y $ aceptan un salto de linea final. El
# lookahead excluye los nombres reservados de Windows (con, prn, aux, nul, com1-9, lpt1-9).
$AllowedPattern = '^(agents/(?!(con|prn|aux|nul|com[1-9]|lpt[1-9])\.)[a-z0-9_-]+\.md|rules/agentes\.md|hooks/agent_guard\.py|docs/agentes\.md)\z'
$StateName = 'synclayer-manifest.json'
$ManifestName = 'install-manifest.json'

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
    return Format-Safe $ex.Message
}

# Busca la propiedad distinguiendo mayusculas (PSObject.Properties[nombre] no las distingue).
function Get-PropRaw($Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    foreach ($p in $Object.PSObject.Properties) {
        if ($p.Name -ceq $Name) { return $p }
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

# Crea un archivo nuevo (CreateNew: nunca pisa uno existente) y lo vuelca a disco.
function Write-NewFile([string]$Path, [byte[]]$Bytes) {
    $fs = New-Object System.IO.FileStream($Path, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
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
# El temporal propio se borra si algo falla; nunca queda un destino a medias.
function Write-Atomic([string]$Dest, [byte[]]$Bytes, [bool]$Existing) {
    $dir = [System.IO.Path]::GetDirectoryName($Dest)
    [void][System.IO.Directory]::CreateDirectory($dir)
    $tmp = Join-Path $dir ('.synclayer-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        Write-NewFile $tmp $Bytes
        if ($Existing) {
            [System.IO.File]::Replace($tmp, $Dest, [NullString]::Value)
        }
        else {
            [System.IO.File]::Move($tmp, $Dest)
        }
    }
    finally {
        if ([System.IO.File]::Exists($tmp)) { [System.IO.File]::Delete($tmp) }
    }
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
    if ((Get-Prop $m 'algorithm') -cne 'sha256') {
        throw 'algorithm debe ser sha256'
    }
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
            throw ('ruta no permitida (absoluta, con .., \ o :): ' + (Format-Safe $path))
        }
        if ($path -cnotmatch $AllowedPattern) {
            throw ('ruta fuera de la lista permitida: ' + (Format-Safe $path))
        }
        if ($hashes.ContainsKey($path)) { throw ('ruta duplicada: ' + (Format-Safe $path)) }
        if (-not ($hash -is [string]) -or $hash -cnotmatch '^[0-9a-f]{64}\z') {
            throw ('sha256 invalido para ' + (Format-Safe $path))
        }
        $hashes[$path] = $hash
        $order.Add($path)
    }
    return @{ Order = $order; Hashes = $hashes; Bytes = $bytes }
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
            "`nRegenera el manifiesto con: python -B tools/build_manifest.py")
    }

    # Paso 3: estado previo del destino.
    $prev = $null
    $statePath = Join-Path $TargetFull $StateName
    if ([System.IO.File]::Exists($statePath)) {
        try {
            $prev = Read-Manifest $statePath
        }
        catch {
            $prev = $null
            Write-Err ('aviso: ' + (Format-Safe $statePath) + ' no se pudo leer o no es valido (' +
                (Get-ErrorText $_) + '). Se trata como ausente.')
        }
    }

    # Paso 4: clasificar.
    $rows = New-Object System.Collections.Generic.List[object]
    $counts = @{ NUEVO = 0; IGUAL = 0; ACTUALIZAR = 0; MODIFICADO = 0; HUERFANO = 0 }
    foreach ($rel in $manifest.Order) {
        $dest = ConvertTo-LocalPath $TargetFull $rel
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
            $destHash = Get-CanonicalHash $dest
            if ($destHash -ceq $manifest.Hashes[$rel]) {
                $state = 'IGUAL'
            }
            elseif ($null -ne $prev -and $prev.Hashes.ContainsKey($rel) -and ($prev.Hashes[$rel] -ceq $destHash)) {
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

    # Paso 5: mostrar el plan.
    Write-Out ('Destino: ' + (Format-Safe $TargetFull))
    Write-Out ('Respaldo: ' + (Format-Safe $BackupFull))
    if ($DryRun) { Write-Out 'Modo: -DryRun (no se escribe nada)' }
    foreach ($row in $rows) {
        Write-Out ($row.State.PadRight(10) + '  ' + $row.Path)
    }
    Write-Out ('Resumen: NUEVO=' + $counts['NUEVO'] + ' IGUAL=' + $counts['IGUAL'] +
        ' ACTUALIZAR=' + $counts['ACTUALIZAR'] + ' MODIFICADO=' + $counts['MODIFICADO'] +
        ' HUERFANO=' + $counts['HUERFANO'])
    if ($counts['HUERFANO'] -gt 0) {
        Write-Out 'nota: los HUERFANO los instalo una version anterior y ya no estan en el manifiesto. No se borran.'
    }

    if ($counts['MODIFICADO'] -gt 0 -and -not $Force) {
        $mod = @($rows | Where-Object { $_.State -eq 'MODIFICADO' } | ForEach-Object { $_.Path })
        Stop-Install 3 ("error: hay cambios locales en el destino (MODIFICADO):`n  " + ($mod -join "`n  ") +
            "`nNo se escribio nada. Opciones: lleva el cambio al repositorio (regla de copia inversa del README)" +
            " o repite con -Force (se respalda lo que se sobrescribe).")
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
    $stateBytes = ConvertTo-CanonicalBytes $manifest.Bytes
    $stateHash = Get-Sha256Hex $stateBytes
    $stateExists = [System.IO.File]::Exists($statePath)
    $stateDestHash = $null
    if ($stateExists) { $stateDestHash = Get-CanonicalHash $statePath }
    $stateNeedsWrite = (-not $stateExists) -or ($stateDestHash -cne $stateHash)

    $backupItems = New-Object System.Collections.Generic.List[object]
    foreach ($row in $writeRows) {
        if ($row.State -ceq 'ACTUALIZAR' -or $row.State -ceq 'MODIFICADO') {
            $backupItems.Add(@{ Rel = $row.Path; From = (ConvertTo-LocalPath $TargetFull $row.Path); Hash = $row.DestHash })
        }
    }
    if ($stateExists -and $stateNeedsWrite) {
        $backupItems.Add(@{ Rel = $StateName; From = $statePath; Hash = $stateDestHash })
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
            $bpath = ConvertTo-LocalPath $BackupFull $item.Rel
            if ([System.IO.File]::Exists($bpath) -or [System.IO.Directory]::Exists($bpath)) {
                Stop-Install 1 ('error: ya existe el respaldo ' + (Format-Safe $bpath) + '. No se pisa; usa otro -BackupDir.')
            }
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

    # Paso 6: respaldar y verificar cada respaldo antes de tocar el destino.
    foreach ($item in $backupItems) {
        $orig = [System.IO.File]::ReadAllBytes($item.From)
        if ((Get-Sha256Hex (ConvertTo-CanonicalBytes $orig)) -cne $item.Hash) {
            Stop-Install 1 ('error: ' + (Format-Safe $item.Rel) + ' cambio en el destino durante la ejecucion. No se escribio nada en el destino; repite.')
        }
        $bpath = ConvertTo-LocalPath $BackupFull $item.Rel
        [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($bpath))
        $backupMade = $true
        Write-NewFile $bpath $orig
        if ((Get-Sha256Hex ([System.IO.File]::ReadAllBytes($bpath))) -cne (Get-Sha256Hex $orig)) {
            Stop-Install 1 ('error: el respaldo de ' + (Format-Safe $item.Rel) + ' no coincide con el original. No se escribio nada en el destino.')
        }
        Write-Out ('Respaldado: ' + $item.Rel)
    }

    # Paso 7: copiar los bytes canonicos ya verificados en memoria; cada uno se verifica al instante.
    foreach ($row in $writeRows) {
        $rel = $row.Path
        $dest = ConvertTo-LocalPath $TargetFull $rel
        $existing = ($row.State -cne 'NUEVO')
        try {
            if ($existing -and ((Get-CanonicalHash $dest) -cne $row.DestHash)) {
                throw 'el archivo cambio en el destino despues de clasificarlo'
            }
            Write-Atomic $dest $canonSrc[$rel] $existing
            $written.Add($rel)
            Write-Out ('Copiado: ' + $rel)
            if ((Get-CanonicalHash $dest) -cne $manifest.Hashes[$rel]) {
                throw 'el hash del archivo escrito no coincide con el manifiesto'
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
            if ((Get-CanonicalHash $dest) -cne $manifest.Hashes[$rel]) { $badDest.Add($rel) }
        }
        catch {
            $badDest.Add($rel + ' (no se pudo leer)')
        }
    }
    if ($badDest.Count -gt 0) {
        Stop-CopyFailed ("la verificacion posterior fallo:`n  " + ($badDest -join "`n  "))
    }
    Write-Out ('Verificado: ' + $written.Count + ' archivo(s) escritos coinciden con el manifiesto.')

    # Paso 9: estado, solo si todo lo anterior paso.
    if ($stateNeedsWrite) {
        try {
            Write-Atomic $statePath $stateBytes $stateExists
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
    Write-Out 'Recordatorio: reinicia las sesiones de Claude Code abiertas; no ven agentes nuevos o modificados.'
    Write-Out 'Recordatorio: este instalador no toca settings.json ni CLAUDE.md; ~/.claude/CLAUDE.md debe apuntar a ~/.claude/rules/agentes.md.'
    Write-Out 'Recordatorio: no hay sincronizacion automatica; repite la instalacion cuando cambien los archivos del repositorio.'
    $defaultTarget = (Join-Path $HOME '.claude').TrimEnd('\', '/')
    if ($TargetFull.TrimEnd('\', '/') -ine $defaultTarget) {
        Write-Out 'aviso: -Target no es ~/.claude y los hooks: de los agentes apuntan a $HOME/.claude/hooks/agent_guard.py.'
    }
    exit 0
}
catch {
    Write-Err ('error: ' + (Get-ErrorText $_))
    exit 1
}
