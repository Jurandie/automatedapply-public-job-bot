# Automated Apply Public

Bot local e auditavel para descobrir vagas em sites publicos de empresas, filtrar oportunidades elegiveis na Italia e Irlanda e apoiar o preenchimento assistido de formularios com revisao humana.

## Escopo

- busca vagas em paginas publicas e ATS conhecidos;
- aceita vagas remotas na Italia ou Irlanda;
- aceita vagas presenciais ou hibridas apenas na Irlanda;
- restringe moedas a EUR ou USD quando a pagina informar pagamento;
- gera curriculos adaptados apenas com base em evidencia local do candidato;
- bloqueia envio automatico quando houver baixa confianca, campo desconhecido ou falta de revisao humana.

## Publicacao Segura

Esta copia publica nao inclui:

- perfil real do candidato;
- inventario real de experiencias;
- lista operacional de empresas-alvo;
- notas locais de reputacao;
- links coletados em runtime;
- curriculos, anexos, banco local, caches e perfis de navegador.

Os arquivos mutaveis do usuario devem ser criados localmente a partir dos templates em `data/`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m playwright install chromium
```

## Configuracao

Crie localmente estes arquivos a partir dos templates:

- `data/candidate_profile.yaml`
- `data/experience_inventory.yaml`
- `data/target_sources.yaml`
- `data/company_ratings.yaml`
- `data/blacklist.yaml`
- `data/sample_posts.json`

## Comandos

```powershell
python -m app.main init-db
python -m app.main scan-company-sites --max-jobs 50
python -m app.main review-jobs
python -m app.main tailor-resumes --limit 1
python -m app.main apply --mode fill_only
python -m unittest discover -s tests
```

## Estrutura

- `app/`: automacao, extracao, classificacao, preenchimento e persistencia.
- `scripts/`: atalhos locais para scan, aplicacao e uso do Claude CLI.
- `tests/`: cobertura de regras deterministicas, extracao e runtime seguro.
- `data/`: somente templates publicos; arquivos reais ficam ignorados pelo Git.
