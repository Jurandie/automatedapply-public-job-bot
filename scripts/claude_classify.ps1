param(
    [Parameter(Mandatory=$true)]
    [string]$InputFile,

    [Parameter(Mandatory=$true)]
    [string]$OutputFile
)

$prompt = Get-Content $InputFile -Raw

$result = claude -p @"
Voce e um classificador de vagas.
Retorne apenas JSON valido, sem markdown.

Criterios:
- is_job_post: true/false
- remote_allowed: true/false
- italy_or_ireland_allowed: true/false
- ireland_onsite_allowed: true/false
- currency_allowed: true/false
- is_recent_job_post: true/false
- seniority_allowed: true/false
- confidence: 0.0 a 1.0
- reason: string curta
- extracted_role: string|null
- extracted_company: string|null
- extracted_location: string|null
- extracted_currency: string|null
- application_links: array

Regras:
- Aceite apenas vagas com localizacao explicita na Italia ou Irlanda.
- Aceite vagas remotas na Italia ou Irlanda.
- Aceite vagas presenciais ou hibridas apenas na Irlanda.
- Rejeite Europa generica quando Italia ou Irlanda nao estiverem explicitas.
- Aceite apenas senioridade Junior/Jr/Entry-level/Associate ou Pleno/Mid-level/Mid.
- Rejeite Senior/Sr/Lead/Staff/Principal/Architect/Manager/Head/Director.
- Se a senioridade nao estiver explicita, marque seniority_allowed=false e explique.
- Aceite EUR ou USD; salario ausente pode ser incerto.
- Rejeite remote US only, Canada only, unpaid, volunteer e commission only.
- Nao invente informacoes.

Texto:
$prompt
"@

$result | Out-File -FilePath $OutputFile -Encoding utf8
