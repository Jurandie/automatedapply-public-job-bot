param(
    [Parameter(Mandatory=$true)]
    [string]$InventoryFile,

    [Parameter(Mandatory=$true)]
    [string]$JobFile,

    [Parameter(Mandatory=$true)]
    [string]$OutputFile
)

$inventory = Get-Content $InventoryFile -Raw
$job = Get-Content $JobFile -Raw

$result = claude -p @"
Voce ajuda a adaptar curriculos, mas deve seguir regras estritas.
Retorne apenas JSON valido, sem markdown.

Regras obrigatorias:
- Use somente fatos presentes no inventario de experiencias.
- Nao invente empresa, cargo, tempo de experiencia, resultado, tecnologia ou metrica.
- Cada bullet sugerido deve apontar source_id de uma experiencia/projeto do inventario.
- Se nao houver evidencia suficiente, retorne grounded=false.
- Nao crie respostas sobre visto, autorizacao de trabalho, salario, diversidade ou termos legais.

Formato:
{
  "grounded": true,
  "target_keywords": [],
  "summary": "",
  "bullets": [
    {"source_id": "", "text": ""}
  ],
  "missing_evidence": [],
  "risks": []
}

Inventario:
$inventory

Vaga:
$job
"@

$result | Out-File -FilePath $OutputFile -Encoding utf8

