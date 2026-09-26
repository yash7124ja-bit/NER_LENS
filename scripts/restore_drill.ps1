# Isolated PostgreSQL/PostGIS backup and restore check at the current Alembic head.
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$suffix = [Guid]::NewGuid().ToString('N').Substring(0, 12)
$source = "ner-lens-drill-source-$suffix"
$target = "ner-lens-drill-target-$suffix"
$archive = Join-Path ([IO.Path]::GetTempPath()) "ner-lens-restore-$suffix.fernet"
$password = [Guid]::NewGuid().ToString('N')
$containers = @()

try {
    foreach ($item in @(@($source, 'ner_lens_source'), @($target, 'postgres'))) {
        $null = docker run --detach --rm --name $item[0] --env "POSTGRES_PASSWORD=$password" --env "POSTGRES_DB=$($item[1])" --publish '127.0.0.1::5432' postgis/postgis:17-3.5
        $containers += $item[0]
        $ready = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            $port = ((docker port $item[0] 5432/tcp) -split ':')[-1]
            $client = [Net.Sockets.TcpClient]::new()
            try { $client.Connect('127.0.0.1', [int]$port); $ready = $true; break }
            catch { Start-Sleep -Seconds 1 }
            finally { $client.Dispose() }
        }
        if (-not $ready) { throw "Database container $($item[0]) did not open its port" }
        Start-Sleep -Seconds 2
        if ($item[0] -eq $source) { $sourcePort = $port }
        else {
            $targetPort = $port
            docker exec $target createdb --username postgres --template template0 ner_lens_restore_check | Out-Null
        }
    }

    $env:NER_LENS_ENV_FILE = ''
    $env:PGHOST = '127.0.0.1'
    $env:PGUSER = 'postgres'
    $env:PGPASSWORD = $password
    $env:PGPORT = $sourcePort
    $env:DATABASE_URL = "postgresql+psycopg://postgres:$password@127.0.0.1:$sourcePort/ner_lens_source"
    uv run alembic upgrade head | Out-Null
    $revision = (psql --no-password --tuples-only --no-align --dbname ner_lens_source --command 'SELECT version_num FROM alembic_version').Trim()
    $jurisdiction = [Guid]::NewGuid().ToString()
    $event = [Guid]::NewGuid().ToString()
    $request = [Guid]::NewGuid().ToString()
    psql --no-password --dbname ner_lens_source --command "INSERT INTO jurisdiction (id, code, name) VALUES ('$jurisdiction', 'restore_drill', 'Restore drill'); INSERT INTO audit_event (id, actor_id, action, target_type, target_id, request_id, occurred_at, jurisdiction_id, outcome) VALUES ('$event', NULL, 'restore_drill', 'jurisdiction', '$jurisdiction', '$request', now(), '$jurisdiction', 'allowed')" | Out-Null
    $sourceCounts = (psql --no-password --tuples-only --no-align --dbname ner_lens_source --command 'SELECT (SELECT count(*) FROM jurisdiction), (SELECT count(*) FROM audit_event)').Trim()

    $env:BACKUP_FERNET_KEY = (uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())').Trim()
    uv run python scripts/backup_restore.py backup --source-db ner_lens_source --output $archive | Out-Null
    $env:PGPORT = $targetPort
    $relations = (psql --no-password --tuples-only --no-align --dbname ner_lens_restore_check --command "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind IN ('r','p','v','m','f','S') AND n.nspname NOT IN ('pg_catalog','information_schema') AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e')").Trim()
    if ($relations -ne '0') { throw "Fresh restore target contains $relations user relations" }
    uv run python scripts/backup_restore.py restore --archive $archive --target-db ner_lens_restore_check | Out-Null
    $targetRevision = (psql --no-password --tuples-only --no-align --dbname ner_lens_restore_check --command 'SELECT version_num FROM alembic_version').Trim()
    $targetCounts = (psql --no-password --tuples-only --no-align --dbname ner_lens_restore_check --command 'SELECT (SELECT count(*) FROM jurisdiction), (SELECT count(*) FROM audit_event)').Trim()
    if ($targetRevision -ne $revision -or $targetCounts -ne $sourceCounts -or $targetCounts -ne '1|1') {
        throw "Restore mismatch: revision or record counts differ"
    }
    Write-Output "Restore drill passed at $revision (jurisdictions=1, audit_events=1)"
}
finally {
    Remove-Item -LiteralPath $archive -ErrorAction SilentlyContinue
    foreach ($container in $containers) { docker stop $container | Out-Null }
    Remove-Item Env:DATABASE_URL, Env:PGPASSWORD, Env:BACKUP_FERNET_KEY -ErrorAction SilentlyContinue
}
