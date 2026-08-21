import os

# 必须在导入 app.* 之前设置，使 engine 在测试环境使用 NullPool（TestClient 独立事件循环）
os.environ["ENVIRONMENT"] = "test"
os.environ["AI_PROVIDER"] = "mock"
os.environ["AI_MODEL"] = "mock-model"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["VOICE_PROVIDER"] = "mock"
os.environ["REDIS_ENABLED"] = "false"
os.environ["JWT_SECRET"] = "test-only-32bytes-jwt-secret-0123456789"
