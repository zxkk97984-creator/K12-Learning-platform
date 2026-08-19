#!/bin/bash
# 复现 golden-path 对话：发「那它为什么会出错？」看 mock provider 回复
set -e
cd /home/zxk/Projects/K12-Learning-platform/backend

TOKEN=$(curl -s -X POST http://localhost:8002/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"xiaoming","password":"demo123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
CONV=$(curl -s -X POST http://localhost:8002/api/v1/conversations -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"title":"E2E复现"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['conversation_id'])")
echo "===发送「那它为什么会出错？」SSE==="
curl -s -N -X POST "http://localhost:8002/api/v1/conversations/$CONV/messages" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"content":"那它为什么会出错？"}' -o /tmp/sse_err.txt
echo "事件序列:"
grep '^event:' /tmp/sse_err.txt | sort | uniq -c
echo ""
echo "===text.done 全文==="
grep -A1 'text.done' /tmp/sse_err.txt | grep '^data:' | python3 -c "import sys,json; print(json.loads(sys.stdin.read().strip().split('data: ')[1])['content'])"
echo ""
echo "===是否含目标文案==="
grep -q "遇到错误时，可以先复现问题" /tmp/sse_err.txt && echo "含『遇到错误时，可以先复现问题』 ✓" || echo "不含 ✗"
