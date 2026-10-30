param(
    [Parameter(Mandatory=$true)][string]$ModulesRepository,
    [string]$PawnCompiler = 'pawncc.exe'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $root 'AtomManEC.p'
$includes = Join-Path $ModulesRepository 'include'
$outbase = Join-Path $root 'AtomManEC'
if (-not (Test-Path (Join-Path $includes 'pawnio.inc'))) { throw 'PawnIO.Modules/include/pawnio.inc not found' }
if (-not (Get-Command $PawnCompiler -ErrorAction SilentlyContinue)) { throw 'pawncc.exe not found; use Pawn compiler recommended by PawnIO.Modules' }
& $PawnCompiler $source '-C64' "-i$includes" "-o$outbase" '-p'
if ($LASTEXITCODE -ne 0) { throw "Pawn compiler failed: exit $LASTEXITCODE" }
Write-Host 'Compiled source only: AtomManEC.amx'
Write-Warning 'AtomManEC.amx is UNSIGNED and cannot load in official PawnIO. Do not disable Secure Boot or HVCI.'
