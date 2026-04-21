param(
    [ValidateSet("dry_run", "fill_only", "review_first", "auto_submit_safe")]
    [string]$Mode = "fill_only"
)

python -m app.main apply --mode $Mode

