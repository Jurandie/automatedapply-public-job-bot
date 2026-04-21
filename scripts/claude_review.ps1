param(
    [Parameter(Mandatory=$true)]
    [string]$InputFile,

    [Parameter(Mandatory=$true)]
    [string]$OutputFile
)

$prompt = Get-Content $InputFile -Raw

$result = claude -p @"
Revise esta aplicacao antes do envio.
Retorne apenas JSON valido, sem markdown.

Campos:
- approve: true/false
- risks: array
- missing_fields: array
- suggested_answer_fixes: object
- reason: string curta

Nao aprove se houver campo obrigatorio desconhecido, resposta inventada,
vaga fora dos criterios ou baixa confianca.

Dados:
$prompt
"@

$result | Out-File -FilePath $OutputFile -Encoding utf8

