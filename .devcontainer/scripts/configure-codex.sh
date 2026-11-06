#!/usr/bin/env bash
set -euo pipefail

export PATH="/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

config_dir="${HOME}/.codex"
config_file="${config_dir}/config.toml"
mkdir -p "${config_dir}"
if [ ! -e "${config_file}" ]; then
  (umask 077; touch "${config_file}")
fi

yq -p toml -o toml -i '
  .model_provider = "amazon-bedrock" |
  .model = "openai.gpt-5.6-luna" |
  .model_reasoning_effort = "xhigh" |
  .model_context_window = 1000000 |
  .model_auto_compact_token_limit = 900000 |
  .approvals_reviewer = "user" |
  .model_providers."amazon-bedrock".aws.region = "us-east-1"
' "${config_file}"
