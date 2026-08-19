import os

# 必须在导入 app.* 之前设置，使 engine 在测试环境使用 NullPool（TestClient 独立事件循环）
os.environ["ENVIRONMENT"] = "test"
