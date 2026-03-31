# DataBaseLLM

MSSQL 데이터베이스에 읽기 전용으로 접속한 뒤, LLM이 SQL을 생성하고 결과를 한국어로 정리해 주는 Chat-style 앱입니다.

## What it does

- 사용자의 자연어 질문을 받습니다.
- 허용된 테이블 스키마를 읽어 LLM에 전달합니다.
- LLM이 `SELECT`/`WITH` 기반 읽기 전용 SQL을 생성합니다.
- 실제 DB 조회 결과를 다시 LLM에 전달해 최종 답변을 만듭니다.
- 같은 기능을 HTTP API와 MCP tool 둘 다로 노출합니다.

## Quick start

```bash
cd /home/check/workspace/DataBaseLLM
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
uvicorn database_llm_app.app:app --host 0.0.0.0 --port 8010 --reload
```

브라우저에서 `http://localhost:8010/chat` 으로 접속하면 됩니다.

## Cloud Run

기본 배포 파일이 포함되어 있습니다.

```bash
cd /home/check/workspace/DataBaseLLM
chmod +x scripts/deploy_cloud_run.sh
PROJECT_ID=your-gcp-project \
REGION=asia-northeast3 \
SERVICE_NAME=database-llm-app \
CONNECTOR_NAME=your-serverless-vpc-connector \
./scripts/deploy_cloud_run.sh
```

주의:

- DB allowlist에 등록된 고정 IP를 유지하려면 기존 서비스와 같은 VPC connector / NAT 경로를 사용해야 합니다.
- 민감한 값은 Cloud Run에선 `.env` 대신 Secret Manager 또는 `--set-env-vars` / `--update-secrets`로 넣는 편이 좋습니다.

## Environment

- `OPENAI_API_KEY`: OpenAI API 키
- `OPENAI_CHAT_MODEL`: 기본값 `gpt-5.4-mini`
- `MSSQL_*`: 기존 `ai-sheet-mcp`와 같은 DB 접속 정보
- `DB_ALLOWED_TABLES`: LLM이 참조 가능한 테이블 목록
- `DB_QUERY_ROW_LIMIT`: 조회 최대 행 수

## MCP

앱 실행 후 MCP endpoint는 기본적으로 `/mcp` 아래에 노출됩니다.

- `open_database_chat_app`: 위젯 UI를 엽니다.
- `ask_database_question`: DB 질의를 수행하고 답변을 반환합니다.

## GCP networking note

Cloud Run이나 GCE/VM에서 같은 VPC egress 경로와 Cloud NAT(static IP 포함)를 재사용하면, 새 앱이라고 해서 반드시 새 public IP를 다시 받을 필요는 없습니다.

보통 아래가 같으면 동일 static egress IP를 유지할 수 있습니다.

- 같은 VPC
- 같은 subnet 또는 같은 NAT가 커버하는 subnet
- 같은 Serverless VPC Access connector 또는 동일한 egress 경로
- 같은 Cloud NAT 설정

새 IP가 필요한 경우는 보통 아래입니다.

- 앱을 다른 프로젝트/VPC/subnet으로 분리할 때
- NAT를 분리 운영할 때
- 서비스별로 IP allowlist를 따로 가져가야 할 때
