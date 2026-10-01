# Inicia o Checklist Pós-Venda nesta máquina e abre o navegador. Chamado pelo iniciar.cmd (duplo clique).
# Só para uso local; no servidor o sistema roda pela tarefa agendada (instalar\LEIAME.md).

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "Checklist Pós-Venda (desenvolvimento)"
Set-Location (Split-Path -Parent $PSScriptRoot)

$porta = if ($env:PORTA) { [int]$env:PORTA } else { 5000 }
$endereco = "http://localhost:$porta"
$env:FLASK_APP = "wsgi"
$teste = [bool]$env:CHECKLIST_NAO_ABRIR  # usado nos testes: não abre navegador nem espera tecla

function Parar([string]$mensagem) {
    Write-Host ""
    Write-Host $mensagem -ForegroundColor Red
    if (-not $teste) { Read-Host "Pressione Enter para fechar" | Out-Null }
    exit 1
}

if (Get-NetTCPConnection -LocalPort $porta -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "O sistema já está rodando. Abrindo o navegador..."
    if (-not $teste) { Start-Process $endereco; Start-Sleep -Seconds 2 }
    exit 0
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Parar "Python não encontrado. Instale o Python 3.12 ou mais novo em python.org, marcando a opção `"Add python.exe to PATH`", e tente de novo."
}

& python -c "import flask, flask_sqlalchemy, flask_migrate, waitress" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Instalando as dependências, só desta vez..."
    & python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Parar "Não foi possível instalar as dependências. Veja a mensagem acima." }
}

Write-Host "Preparando o banco de dados..."
$saida = & python -m flask db upgrade 2>&1
if ($LASTEXITCODE -ne 0) {
    $saida | Out-Host
    Parar "Não foi possível atualizar o banco de dados. Veja a mensagem acima."
}
& python -m flask catalogo carregar 2>&1 | Out-Null

Write-Host ""
Write-Host "==============================================================="
Write-Host "  Checklist Pós-Venda rodando em $endereco" -ForegroundColor Green
Write-Host "  Para parar, feche esta janela."
Write-Host "==============================================================="
Write-Host ""

if (-not $teste) {
    # Abre o navegador assim que o sistema responder.
    $abrir = "for (`$i = 0; `$i -lt 40; `$i++) { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '$endereco/entrar' | Out-Null; break } catch { Start-Sleep -Milliseconds 500 } }; Start-Process '$endereco'"
    Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoProfile", "-Command", $abrir
}

& python -m flask run --port $porta
if ($LASTEXITCODE -ne 0) { Parar "O sistema parou com erro. Veja a mensagem acima." }
